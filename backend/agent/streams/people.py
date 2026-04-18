"""
People stream — find individuals on LinkedIn / Reddit / native social
platforms (Naver, Quora-IN, Zhihu, etc.) who are expressing the pain
point our product solves, then reply / DM them in their local language.
"""

from __future__ import annotations

import asyncio
import json
import re

from agent.country import get_country_config
from agent.enrichment import enrich_lead_via_linkedin, looks_like_real_name
from agent.llm import think
from agent.memory import increment_channel_sent, save_leads, update_lead_status
from agent.prompts import (
    AGENT_SYSTEM_PROMPT,
    COLD_OUTREACH_PROMPT,
    ICP_SCORING_PROMPT,
    LOCAL_OUTREACH_PROMPT,
)
from agent.scrapers import scrape_platform
from agent import approval as _approval
from agent.tools import (
    post_linkedin_comment,
    post_native_comment,
    post_reddit_comment,
    post_tiktok_comment,
    post_youtube_comment,
    scrape_linkedin_posts,
    scrape_linkedin_profiles_by_icp,
    scrape_reddit_posts,
    scrape_tiktok_posts,
    scrape_youtube_videos,
    send_gmail,
    send_linkedin_dm,
    send_reddit_dm,
)

PEOPLE_LOOP_SECONDS = 30 * 60  # 30 min
DM_DELAY_SECONDS = 30
PREVIEW_HOLD_SECONDS = 5  # let the dashboard render the preview card first


def _push(campaign_id: str, **kwargs) -> None:
    from agent.loop import push_event  # local import to avoid cycle
    event = {"stream": "people", **kwargs}
    push_event(campaign_id, event)


async def _scrape_all_platforms(
    campaign_id: str,
    country: str,
    pain_keywords: list[str],
    icp_search_queries: dict | None = None,
) -> list[dict]:
    """Fan out across all channels configured for this country."""
    cfg = get_country_config(country)
    keyword = " OR ".join(f'"{k}"' for k in pain_keywords[:3]) or country
    leads: list[dict] = []

    # ── LinkedIn ─────────────────────────────────────────────────────────
    if "linkedin" in cfg["social"]:
        leads.extend(
            await asyncio.to_thread(
                scrape_linkedin_posts,
                keyword,
                country,
                15,
                campaign_id,
            )
        )

    # ── Reddit ───────────────────────────────────────────────────────────
    if "reddit" in cfg["social"]:
        subs = [
            s.removeprefix("reddit.com/r/")
            for s in cfg["people_sites"]
            if s.startswith("reddit.com/r/")
        ]
        leads.extend(
            await asyncio.to_thread(
                scrape_reddit_posts,
                keyword,
                subs or None,
                20,
                campaign_id,
            )
        )

    # ── TikTok ───────────────────────────────────────────────────────────
    if "tiktok" in cfg["social"]:
        leads.extend(
            await asyncio.to_thread(
                scrape_tiktok_posts,
                keyword,
                15,
                campaign_id,
            )
        )

    # ── YouTube ──────────────────────────────────────────────────────────
    if "youtube" in cfg["social"]:
        leads.extend(
            await asyncio.to_thread(
                scrape_youtube_videos,
                keyword,
                15,
                campaign_id,
            )
        )

    # ── Native social (Blind / Naver / Weibo / Xiaohongshu / Quora / Zhihu /
    # Qiita / Zenn / etc.) ───────────────────────────────────────────────
    native_sites = [
        s for s in cfg["people_sites"] if not s.startswith("reddit.com/")
    ][:3]

    for site in native_sites:
        leads.extend(
            await asyncio.to_thread(
                scrape_platform,
                site,
                keyword,
                cfg["search_country"],
                cfg["search_locale"],
                8,
                campaign_id,
            )
        )

    # ── Proactive ICP-role search ─────────────────────────────────────────
    # Find people by job title/role who would benefit from the product, even
    # before they post about the pain. Uses `icp_search_queries` generated
    # during company analysis.
    icp_queries: dict = icp_search_queries or {}
    if icp_queries:
        _push(
            campaign_id,
            type="think",
            action="Running proactive ICP-role search on LinkedIn",
            reasoning="Finding target personas by title/role — not just people posting about pain.",
            channel="apify",
        )
        li_icp_query = icp_queries.get("linkedin") or ""
        if li_icp_query:
            leads.extend(
                await asyncio.to_thread(
                    scrape_linkedin_profiles_by_icp,
                    li_icp_query,
                    country,
                    10,
                    campaign_id,
                )
            )
        # TikTok ICP query — only if TikTok is configured for this country
        tiktok_icp_query = icp_queries.get("tiktok") or ""
        if tiktok_icp_query and "tiktok" in cfg["social"]:
            leads.extend(
                await asyncio.to_thread(
                    scrape_tiktok_posts,
                    tiktok_icp_query,
                    10,
                    campaign_id,
                )
            )

    # Dedup by source_post_url
    seen: set[str] = set()
    unique: list[dict] = []
    for l in leads:
        url = l.get("source_post_url") or ""
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        unique.append(l)
    return unique


async def _score_and_persist(
    campaign_id: str,
    raw_leads: list[dict],
    icp_description: str,
) -> list[dict]:
    scored: list[dict] = []
    for lead in raw_leads[:20]:
        try:
            raw = await asyncio.to_thread(
                think,
                AGENT_SYSTEM_PROMPT,
                ICP_SCORING_PROMPT.format(
                    icp_description=icp_description,
                    lead_data=json.dumps(lead, ensure_ascii=False),
                ),
            )
            score_data = json.loads(raw)
            lead["score"] = int(score_data.get("score", 5))
        except Exception:
            lead["score"] = 5
        scored.append(lead)

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = scored[:10]

    # Enrich top-5 leads that have a real-looking name but no LinkedIn URL.
    # This is the bridge from a Reddit/Naver/Blind handle to a contactable
    # LinkedIn profile (and optionally an email). Bounded by `top[:5]` to
    # cap Apify spend per cycle.
    enrich_targets = [
        l for l in top[:5]
        if not l.get("linkedin_url") and looks_like_real_name(l.get("name"))
    ]
    if enrich_targets:
        _push(
            campaign_id,
            type="think",
            action=f"Enriching {len(enrich_targets)} top leads via LinkedIn search",
            reasoning="Resolving handles → real LinkedIn profiles for DM.",
            channel="apify",
        )
        for lead in enrich_targets:
            enriched = await asyncio.to_thread(
                enrich_lead_via_linkedin,
                lead.get("name", ""),
                lead.get("company") or None,
                None,
                False,
                campaign_id,
            )
            if enriched.get("linkedin_url"):
                lead["linkedin_url"] = enriched["linkedin_url"]
                if not lead.get("title") and enriched.get("headline"):
                    lead["title"] = enriched["headline"][:160]
                if not lead.get("company") and enriched.get("company"):
                    lead["company"] = enriched["company"][:120]
                if enriched.get("email"):
                    lead["email"] = enriched["email"]

    if top:
        save_leads(
            campaign_id,
            [
                {
                    "name": l.get("name", "")[:120] or "unknown",
                    "title": l.get("title", "")[:160],
                    "company": l.get("company", "")[:120],
                    "linkedin_url": l.get("linkedin_url", "") or "",
                    "email": (l.get("email") or None),
                    "score": l.get("score", 5),
                    "status": "identified",
                    "platform": l.get("platform", "linkedin"),
                    "source_post_url": l.get("source_post_url", "") or None,
                    "source_comment_text": l.get("source_comment_text", "") or None,
                }
                for l in top
            ],
        )
    return top


# Languages that use a non-Latin script — any stray Latin words in their output
# indicate the model mixed languages (e.g. French "interessant" inside Korean).
_NON_LATIN_LANGUAGES = {
    "ko", "ja", "zh", "zh-TW", "zh-CN", "ar", "th", "hi", "ru", "uk",
    "el", "he", "fa", "bn", "ta", "te", "ml", "si", "km", "lo", "my",
}


def _has_language_mixing(body: str, language_code: str) -> bool:
    """Return True when the body appears to mix in foreign-language words.

    For non-Latin-script languages (Korean, Japanese, Chinese, etc.) we flag
    any message that contains 2+ sequences of 3+ consecutive Latin alphabetic
    characters — those are almost certainly stray words from another language
    (e.g. French "interessant" or Vietnamese "rất" spliced into a Korean reply).
    A single short Latin token is tolerated for unavoidable brand/product names.
    """
    lang = (language_code or "").lower().split("-")[0]
    if lang not in _NON_LATIN_LANGUAGES:
        return False
    latin_words = re.findall(r"[A-Za-z]{3,}", body)
    # Allow at most one Latin token (e.g. a brand name that truly can't be
    # transliterated); two or more almost always means code-switching.
    return len(latin_words) >= 2


def _post_is_latin_script(text: str) -> bool:
    """Return True if the post is primarily written in a Latin-script language.

    Counts characters from common non-Latin script Unicode blocks. If fewer
    than 20% of alphabetic characters are non-Latin the post is considered
    a Latin-script post (English, French, German, Spanish, etc.).
    """
    if not text or not text.strip():
        return False
    non_latin = sum(
        1 for c in text
        if (
            "\u0400" <= c <= "\u04FF"  # Cyrillic
            or "\u0600" <= c <= "\u06FF"  # Arabic
            or "\u0900" <= c <= "\u097F"  # Devanagari
            or "\u3040" <= c <= "\u30FF"  # Japanese kana
            or "\u4E00" <= c <= "\u9FFF"  # CJK unified ideographs
            or "\uAC00" <= c <= "\uD7A3"  # Korean Hangul syllables
            or "\u0E00" <= c <= "\u0E7F"  # Thai
            or "\u1100" <= c <= "\u11FF"  # Korean Hangul Jamo
        )
    )
    letter_count = sum(1 for c in text if c.isalpha())
    if letter_count == 0:
        return False
    return (non_latin / letter_count) < 0.2


def _resolve_reply_language(
    post_text: str,
    cfg: dict,
) -> tuple[str, str]:
    """Return (language_code, language_name) for the reply.

    If the source post is in a Latin-script language but the campaign language
    is non-Latin (e.g. English LinkedIn post for a Korean campaign), reply in
    English so the message matches what the person actually wrote. Otherwise
    use the campaign language.
    """
    campaign_lang = cfg["language"].lower().split("-")[0]
    if _post_is_latin_script(post_text) and campaign_lang in _NON_LATIN_LANGUAGES:
        return "en", "English"
    return cfg["language"], cfg["language_name"]


async def _draft_reply(
    campaign_id: str,
    lead: dict,
    country: str,
    pain_point: str,
    product_summary: str,
) -> dict:
    cfg = get_country_config(country)
    platform = lead.get("platform", "linkedin")
    post_text = (lead.get("source_comment_text") or "").strip()
    template_seed = "(no template seed — improvise)"

    # ── Cold outreach path: ICP-profile leads with no source post ─────────
    # When there is no post excerpt we have nothing to reference, so we use a
    # dedicated cold-outreach prompt rather than pretending to reply to a post.
    if not post_text:
        cold_kwargs = dict(
            language=cfg["language"],
            language_name=cfg["language_name"],
            country=country,
            platform=platform,
            recipient_name=lead.get("name") or "there",
            recipient_title=lead.get("title") or "professional",
            recipient_company=lead.get("company") or "your company",
            product_summary=product_summary,
            pain_point=pain_point,
            cultural_context=cfg["cultural_context"],
        )
        for _attempt in range(3):
            raw = await asyncio.to_thread(
                think,
                AGENT_SYSTEM_PROMPT,
                COLD_OUTREACH_PROMPT.format(**cold_kwargs),
            )
            try:
                result = json.loads(raw)
            except Exception:
                result = {"language": cfg["language"], "body": raw[:400], "english_gloss": ""}
            if not _has_language_mixing(result.get("body", ""), cfg["language"]):
                return result
            cold_kwargs["language_name"] = (
                "(IMPORTANT: pure " + cfg["language_name"] + " only)\n" + cfg["language_name"]
            )
        return result

    # ── Reply path: we have a source post to reference ────────────────────
    reply_lang, reply_lang_name = _resolve_reply_language(post_text, cfg)

    prompt_kwargs = dict(
        reply_language=reply_lang,
        post_language_name=reply_lang_name,
        campaign_language_name=cfg["language_name"],
        country=country,
        platform=platform,
        source_post_excerpt=post_text[:600],
        product_summary=product_summary,
        pain_point=pain_point,
        cultural_context=cfg["cultural_context"],
        template_seed=template_seed,
    )

    for _attempt in range(3):
        raw = await asyncio.to_thread(
            think,
            AGENT_SYSTEM_PROMPT,
            LOCAL_OUTREACH_PROMPT.format(**prompt_kwargs),
        )
        try:
            result = json.loads(raw)
        except Exception:
            result = {"language": reply_lang, "body": raw[:400], "english_gloss": ""}

        if not _has_language_mixing(result.get("body", ""), reply_lang):
            return result
        # Mixed-language output detected — retry with a stricter reminder.
        prompt_kwargs["template_seed"] = (
            "(IMPORTANT: write in pure "
            + reply_lang_name
            + " only — no words from any other language)\n"
            + template_seed
        )

    return result


async def _reach_out(
    campaign_id: str,
    lead: dict,
    reply: dict,
) -> None:
    body = reply.get("body", "")
    if not body:
        return
    platform = lead.get("platform", "linkedin")
    post_url = lead.get("source_post_url", "")
    profile_url = lead.get("linkedin_url", "")
    username = lead.get("name", "")

    # Decide the target URL + verb up front so we can preview them.
    # For Reddit and TikTok we fall back to a DM/username when there is
    # no post URL so the lead is never silently dropped.
    if platform == "linkedin":
        target_url = post_url or profile_url
        verb = "comment on" if post_url else "DM"
    elif platform == "reddit":
        target_url = post_url or username  # DM fallback uses username
        verb = "comment on" if post_url else "DM"
    elif platform == "tiktok":
        target_url = post_url
        verb = "comment on"
    elif platform == "youtube":
        target_url = post_url
        verb = "comment on"
    else:
        target_url = post_url
        verb = f"comment on {platform}"

    if not target_url:
        _push(
            campaign_id,
            type="error",
            action=f"No contact target for {lead.get('name', '?')} ({platform}) — skipping",
            reasoning=(
                "Lead has no post URL, no LinkedIn profile URL, and no username. "
                "Cannot reach out without at least one contact point."
            ),
            channel=platform,
        )
        return

    # ── Preview event: surfaces the drafted message + target BEFORE we
    # fire the browser-use task. When require_human_approval is on we wait
    # for the human to click Approve/Reject instead of just sleeping.
    require_approval = await asyncio.to_thread(
        _approval.get_require_approval, campaign_id
    )
    approval_id = _approval.register() if require_approval else None

    _push(
        campaign_id,
        type="preview",
        action=f"About to {verb} → {lead.get('name', '?')} ({platform})",
        reasoning=(reply.get("english_gloss") or "")[:300],
        channel=platform,
        preview={
            "target_name": lead.get("name", ""),
            "target_url": target_url,
            "platform": platform,
            "body_local": body,
            "english_gloss": reply.get("english_gloss") or "",
            "approval_id": approval_id,
        },
    )

    if require_approval and approval_id:
        approved = await _approval.wait(approval_id)
        if not approved:
            _push(
                campaign_id,
                type="wait",
                action=f"Outreach skipped → {lead.get('name', '?')} ({platform}): rejected by human",
                reasoning="Human validation rejected or timed out for this action.",
                channel=platform,
            )
            return
    else:
        await asyncio.sleep(PREVIEW_HOLD_SECONDS)

    # ── Execute outreach — capture the result and surface failures visibly.
    result: dict = {"success": False, "error": "no outreach branch matched"}
    if platform == "linkedin":
        if post_url:
            result = await post_linkedin_comment(post_url, body, campaign_id=campaign_id)
        else:
            result = await send_linkedin_dm(profile_url, body, campaign_id=campaign_id)
    elif platform == "reddit":
        if post_url:
            result = await post_reddit_comment(post_url, body, campaign_id=campaign_id)
        else:
            result = await send_reddit_dm(username, body, campaign_id=campaign_id)
    elif platform == "tiktok":
        result = await post_tiktok_comment(post_url, body, campaign_id=campaign_id)
    elif platform == "youtube":
        result = await post_youtube_comment(post_url, body, campaign_id=campaign_id)
    else:
        result = await post_native_comment(post_url, body, platform, campaign_id=campaign_id)

    # ── Surface failure clearly; do NOT mark contacted on error.
    if not result.get("success"):
        err = (result.get("error") or "unknown browser-use error")[:200]
        _push(
            campaign_id,
            type="error",
            action=f"Outreach FAILED → {lead.get('name', '')} ({platform}): {err[:120]}",
            reasoning=err,
            channel=platform,
        )
        return

    # ── Success path
    increment_channel_sent(campaign_id, platform)
    update_lead_status(
        campaign_id, post_url or profile_url or username, "contacted", reply_text=body
    )

    _push(
        campaign_id,
        type="act",
        action=f"{platform} reply sent → {lead.get('name', '')} (score {lead.get('score', 0)}/10)",
        reasoning=(reply.get("english_gloss") or "")[:300],
        channel=platform,
    )

    # If the lead has an email (enriched via LinkedIn), also send a Gmail.
    email = lead.get("email")
    if email:
        subject = (
            reply.get("subject")
            or f"Re: {lead.get('source_comment_text', '')[:60] or 'Connecting with you'}"
        )
        _push(
            campaign_id,
            type="act",
            action=f"Sending Gmail to {lead.get('name', '')} <{email}>",
            reasoning="Lead has an email — following up via Gmail in addition to social.",
            channel="gmail",
        )
        gmail_result = await send_gmail(email, subject, body, campaign_id=campaign_id)
        if gmail_result.get("success"):
            increment_channel_sent(campaign_id, "gmail")
        else:
            gmail_err = (gmail_result.get("error") or "unknown error")[:200]
            _push(
                campaign_id,
                type="error",
                action=f"Gmail FAILED → {email}: {gmail_err[:120]}",
                reasoning=gmail_err,
                channel="gmail",
            )


async def run_people_stream(
    campaign_id: str,
    country: str,
    icp_description: str,
    pain_point: str,
    pain_keywords: list[str],
    product_summary: str,
    is_running,
    icp_search_queries: dict | None = None,
) -> None:
    """Long-running coroutine. Stops when is_running() returns False.

    First cycle fires immediately on spawn so the dashboard isn't dead air
    for 30 minutes after deploy. Subsequent cycles wait `PEOPLE_LOOP_SECONDS`.
    """
    _push(
        campaign_id,
        type="scan",
        action=f"People stream online for {country}",
        reasoning=f"Pain keywords: {', '.join(pain_keywords[:3])}.",
        channel="apify",
    )

    # First cycle now → no 30-min cold start.
    while True:
        if not is_running():
            return
        try:
            raw = await _scrape_all_platforms(
                campaign_id, country, pain_keywords, icp_search_queries
            )
            _push(
                campaign_id,
                type="think",
                action=f"Pulled {len(raw)} candidate posts across platforms.",
                reasoning="Scoring for ICP fit and de-duping.",
                channel="llm",
            )
            top = await _score_and_persist(campaign_id, raw, icp_description)
            for lead in top[:5]:
                if not is_running():
                    return
                reply = await _draft_reply(
                    campaign_id,
                    lead,
                    country,
                    pain_point,
                    product_summary,
                )
                if not is_running():
                    return
                await _reach_out(campaign_id, lead, reply)
                await asyncio.sleep(DM_DELAY_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            _push(
                campaign_id,
                type="wait",
                action=f"People stream hit error: {e}",
                reasoning="Will retry next cycle.",
                channel=None,
            )

        # Wait, but stay responsive to cancellation.
        for _ in range(PEOPLE_LOOP_SECONDS // 30):
            if not is_running():
                return
            await asyncio.sleep(30)
