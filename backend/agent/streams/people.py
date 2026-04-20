"""
People streams — 5 fully independent agents, each running its own eternal loop:

  run_linkedin_agent   → harvestapi/linkedin-post-search + Google SERP fallback
  run_reddit_agent     → trudax/reddit-scraper-lite + Browser-Use comment/DM
  run_instagram_agent  → apify/instagram-hashtag-scraper + Browser-Use comment
  run_youtube_agent    → h7sDV53CddomktSi5 + Browser-Use comment
  run_gmail_agent      → Google SERP discovery → draft leads (no Browser-Use send)

Every social agent follows the same pipeline:
  scrape → score (ICP fit) → draft reply (LLM) → reach out (Browser-Use) → sleep → repeat

All agents launch simultaneously from second 1. Each is fully independent — one crash
or slow Apify run does not block or cancel any other agent.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Callable

from agent.country import get_country_config
from agent.enrichment import enrich_lead_via_linkedin, looks_like_real_name
from agent.llm import think
from agent.memory import increment_channel_sent, save_leads, store_lead_draft, update_lead_status
from agent.prompts import (
    AGENT_SYSTEM_PROMPT,
    COLD_OUTREACH_PROMPT,
    ICP_SCORING_PROMPT,
    LOCAL_OUTREACH_PROMPT,
    get_platform_style,
)
from agent import approval as _approval
from agent.scrapers import scrape_platform
from agent.tools import (
    google_search,
    post_instagram_comment,
    post_linkedin_comment,
    post_native_comment,
    post_reddit_comment,
    post_youtube_comment,
    scrape_instagram_posts,
    scrape_linkedin_posts,
    scrape_reddit_posts,
    scrape_youtube_videos,
    send_gmail,
    send_linkedin_dm,
    send_reddit_dm,
)

PEOPLE_LOOP_SECONDS = 10 * 60   # 10 min cadence — continuous discovery
GMAIL_LOOP_SECONDS  = 4 * 60 * 60  # 4h cadence for Gmail (avoid rate limits)
DM_DELAY_SECONDS    = 10
PREVIEW_HOLD_SECONDS = 5  # let the dashboard render the preview card first
GMAIL_MAX_PER_CYCLE  = 5  # contacts per Gmail cycle


def _push(campaign_id: str, **kwargs) -> None:
    from agent.loop import push_event  # local import to avoid cycle
    event = {"stream": "people", **kwargs}
    push_event(campaign_id, event)


# ─── Language utilities ──────────────────────────────────────────────────────

# Languages that use a non-Latin script — any stray Latin words in their output
# indicate the model mixed languages (e.g. French "interessant" inside Korean).
_NON_LATIN_LANGUAGES = {
    "ko", "ja", "zh", "zh-TW", "zh-CN", "ar", "th", "hi", "ru", "uk",
    "el", "he", "fa", "bn", "ta", "te", "ml", "si", "km", "lo", "my",
}


def _has_language_mixing(body: str, language_code: str) -> bool:
    """Return True when the body appears to mix in foreign-language words."""
    lang = (language_code or "").lower().split("-")[0]
    if lang not in _NON_LATIN_LANGUAGES:
        return False
    # Any Latin alphabet word (3+ chars) inside a non-Latin-script message is mixing.
    # Threshold is 1, not 2 — a single "interessant" or "sehr" is already wrong.
    latin_words = re.findall(r"[A-Za-z]{3,}", body)
    if len(latin_words) >= 1:
        return True
    # For Korean: CJK ideographs and Japanese kana are foreign script
    if lang == "ko":
        cjk_count = sum(
            1 for c in body
            if (
                "\u3040" <= c <= "\u30FF"  # Hiragana + Katakana
                or "\u4E00" <= c <= "\u9FFF"  # CJK Unified Ideographs
                or "\u3400" <= c <= "\u4DBF"  # CJK Extension A
            )
        )
        if cjk_count >= 2:
            return True
    return False


def _describe_mixing(body: str, language_code: str) -> str:
    """Return a short human-readable description of the foreign content found."""
    lang = (language_code or "").lower().split("-")[0]
    parts: list[str] = []
    latin_words = re.findall(r"[A-Za-z]{3,}", body)
    if len(latin_words) >= 1:
        parts.append(f"foreign Latin/English words: {', '.join(latin_words[:6])}")
    if lang == "ko":
        cjk_chars = [
            c for c in body
            if (
                "\u3040" <= c <= "\u30FF"
                or "\u4E00" <= c <= "\u9FFF"
                or "\u3400" <= c <= "\u4DBF"
            )
        ]
        if len(cjk_chars) >= 2:
            parts.append(f"Chinese/Japanese characters: {''.join(cjk_chars[:10])}")
    return "; ".join(parts) if parts else "mixed foreign content"


def _post_is_latin_script(text: str) -> bool:
    """Return True if the post is primarily written in a Latin-script language."""
    if not text or not text.strip():
        return False
    non_latin = sum(
        1 for c in text
        if (
            "\u0400" <= c <= "\u04FF"
            or "\u0600" <= c <= "\u06FF"
            or "\u0900" <= c <= "\u097F"
            or "\u3040" <= c <= "\u30FF"
            or "\u4E00" <= c <= "\u9FFF"
            or "\uAC00" <= c <= "\uD7A3"
            or "\u0E00" <= c <= "\u0E7F"
            or "\u1100" <= c <= "\u11FF"
        )
    )
    letter_count = sum(1 for c in text if c.isalpha())
    if letter_count == 0:
        return False
    return (non_latin / letter_count) < 0.2


def _resolve_reply_language(post_text: str, cfg: dict) -> tuple[str, str]:
    """Return (language_code, language_name) for the reply.

    For non-English campaigns we always reply in the campaign language.
    A Korean campaign targets Korean professionals — even if they happen to
    post in English on Reddit/LinkedIn, the outreach should be in Korean so
    it feels like local-market communication rather than a global blast.
    """
    return cfg["language"], cfg["language_name"]


# ─── Shared pipeline helpers ─────────────────────────────────────────────────


async def _score_and_persist(
    campaign_id: str,
    raw_leads: list[dict],
    icp_description: str,
) -> list[dict]:
    async def _score_one(lead: dict) -> dict:
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
        return lead

    scored = list(await asyncio.gather(*[_score_one(l) for l in raw_leads[:50]]))
    scored.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Drop leads that score below 5 — they are irrelevant to the ICP and
    # would pollute the dashboard and outreach queue.
    qualified = [l for l in scored if l.get("score", 0) >= 5]
    top = qualified[:30]

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

        async def _enrich_one(lead: dict) -> None:
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

        await asyncio.gather(*[_enrich_one(l) for l in enrich_targets])

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
        # Signal the frontend to refresh the leads panel immediately rather
        # than waiting for the next 10-second poll.
        platform_label = top[0].get("platform", "unknown") if top else "unknown"
        _push(
            campaign_id,
            type="leads_updated",
            action=f"{platform_label}: {len(top)} new leads saved",
            reasoning="",
            channel=platform_label,
        )
    return top


async def _draft_reply(
    campaign_id: str,
    lead: dict,
    country: str,
    pain_point: str,
    product_summary: str,
) -> dict:
    cfg = get_country_config(country)
    platform = lead.get("platform", "linkedin")
    # Gmail contacts are cold outreach — source_comment_text is a SERP snippet
    # about the person, not a post they wrote.  Treating it as "their post"
    # causes _resolve_reply_language to detect Latin script and switch to English
    # even when the campaign targets a non-Latin-script country (e.g. Korea).
    # Always use the cold outreach path for Gmail leads.
    post_text = "" if platform == "gmail" else (lead.get("source_comment_text") or "").strip()
    template_seed = "(no template seed — improvise)"

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
            platform_style_rules=get_platform_style(platform),
            correction_note="",
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
            body = result.get("body", "")
            if not _has_language_mixing(body, cfg["language"]):
                return result
            mixed = _describe_mixing(body, cfg["language"])
            cold_kwargs["correction_note"] = (
                f"\n⚠ CORRECTION REQUIRED: Your previous attempt contained foreign-language "
                f"content ({mixed}). You MUST rewrite the body using ONLY {cfg['language_name']}. "
                f"Do NOT include any Latin letters, English words, French words, Chinese characters, "
                f"or Japanese characters. Every single word must be pure {cfg['language_name']}."
            )
        raise ValueError(
            f"Language mixing could not be eliminated after 3 attempts ({mixed}). Skipping lead."
        )

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
        platform_style_rules=get_platform_style(platform),
        correction_note="",
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

        body = result.get("body", "")
        if not _has_language_mixing(body, reply_lang):
            return result
        mixed = _describe_mixing(body, reply_lang)
        prompt_kwargs["correction_note"] = (
            f"\n⚠ CORRECTION REQUIRED: Your previous attempt contained foreign-language "
            f"content ({mixed}). You MUST rewrite the body using ONLY {reply_lang_name}. "
            f"Do NOT include any Latin letters, English words, French words, Chinese characters, "
            f"or Japanese characters. Every single word must be pure {reply_lang_name}."
        )

    raise ValueError(
        f"Language mixing could not be eliminated after 3 attempts ({mixed}). Skipping lead."
    )


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

    if platform == "linkedin":
        target_url = post_url or profile_url
        verb = "comment on" if post_url else "DM"
    elif platform == "reddit":
        target_url = post_url or username
        verb = "comment on" if post_url else "DM"
    elif platform in ("youtube", "instagram"):
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
    elif platform == "youtube":
        result = await post_youtube_comment(post_url, body, campaign_id=campaign_id)
    elif platform == "instagram":
        result = await post_instagram_comment(post_url, body, campaign_id=campaign_id)
    else:
        result = await post_native_comment(post_url, body, platform, campaign_id=campaign_id)

    if not result.get("success"):
        err = (result.get("error") or "unknown browser-use error")[:200]
        # Don't spam the feed for credits-exhausted — a single error was
        # already emitted by browser_use_task; just silently skip here.
        if "credits exhausted" not in err.lower():
            _push(
                campaign_id,
                type="error",
                action=f"Outreach FAILED → {lead.get('name', '')} ({platform}): {err[:120]}",
                reasoning=err,
                channel=platform,
            )
        return

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


async def _reach_out_platform_group(
    campaign_id: str,
    leads_and_replies: list[tuple[dict, dict]],
    is_running: Callable,
) -> None:
    """Send outreach for one platform's leads sequentially, with delay between each."""
    for lead, reply in leads_and_replies:
        if not is_running():
            return
        await _reach_out(campaign_id, lead, reply)
        await asyncio.sleep(DM_DELAY_SECONDS)


# ─── Generic platform agent factory ─────────────────────────────────────────


async def _run_platform_agent(
    platform: str,
    campaign_id: str,
    country: str,
    config: dict,
    is_running: Callable,
    scrape_fn: Callable,         # async scraping function (e.g. scrape_linkedin_posts)
    scrape_kwargs_fn: Callable,  # called each cycle to build kwargs from latest config
    loop_seconds: int = PEOPLE_LOOP_SECONDS,
) -> None:
    """
    Full pipeline for a single platform: scrape → score → draft → reach out → sleep.

    `scrape_fn`         — the async Apify wrapper (e.g. scrape_linkedin_posts).
                          Uses ApifyClientAsync — no thread blocking.
    `scrape_kwargs_fn`  — callable(config, country) → dict of kwargs for scrape_fn.
                          Called fresh every cycle so config upgrades propagate.

    Always waits for the LLM company analysis to finish before the FIRST scrape so
    real pain-point keywords (not just the company name) drive every search.
    """
    cfg = get_country_config(country)
    _push(
        campaign_id,
        type="scan",
        action=f"{platform.capitalize()} agent online for {country} — waiting for analysis",
        reasoning="Holding first scrape until LLM analysis populates real pain-point keywords.",
        channel="apify",
    )

    # Wait up to 3 minutes for the analysis to complete before first scrape.
    # The analysis typically finishes in 60-90 s. Polling every 5 s keeps it
    # responsive without burning CPU.
    _wait_elapsed = 0
    while not config.get("analysis_complete") and _wait_elapsed < 180:
        if not is_running():
            return
        await asyncio.sleep(5)
        _wait_elapsed += 5

    _push(
        campaign_id,
        type="scan",
        action=(
            f"{platform.capitalize()} agent starting first scrape for {country}"
            + (" — analysis ready" if config.get("analysis_complete") else " — analysis timed out, using defaults")
        ),
        reasoning=f"Pain keywords: {', '.join(config.get('pain_keywords', [])[:3])}",
        channel="apify",
    )

    while True:
        if not is_running():
            return

        try:
            kwargs = scrape_kwargs_fn(config, country, cfg)
            # scrape_fn is async (uses ApifyClientAsync) — call directly
            raw = await scrape_fn(**kwargs)
            # Guard: if a stale .pyc or other mis-wiring returns a coroutine
            # instead of a list, coerce to empty so we skip gracefully.
            if not isinstance(raw, list):
                raw = []

            # For non-Latin-script campaigns (Korean, Japanese, Chinese, etc.)
            # drop posts whose text is entirely Latin/English — they are content
            # from the wrong geographic/linguistic audience.
            campaign_lang_base = cfg.get("language", "en").lower().split("-")[0]
            if campaign_lang_base in _NON_LATIN_LANGUAGES:
                before = len(raw)
                raw = [
                    p for p in raw
                    if not p.get("source_comment_text", "").strip()
                    or not _post_is_latin_script(p.get("source_comment_text", ""))
                ]
                dropped = before - len(raw)
                if dropped:
                    _push(
                        campaign_id,
                        type="think",
                        action=(
                            f"{platform.capitalize()}: filtered out {dropped} English/Latin posts "
                            f"— keeping only {cfg['language_name']}-language content"
                        ),
                        reasoning=(
                            f"Campaign targets {country} ({cfg['language_name']}). "
                            "Posts in English/Latin script are from the wrong audience."
                        ),
                        channel="apify",
                    )

            if raw:
                _push(
                    campaign_id,
                    type="think",
                    action=f"{platform.capitalize()}: {len(raw)} posts found — scoring ICP fit",
                    reasoning="Filtering for leads that match the ICP.",
                    channel="llm",
                )
                top = await _score_and_persist(campaign_id, raw, config["icp_description"])
                batch = top[:15]

                replies = await asyncio.gather(
                    *[
                        _draft_reply(
                            campaign_id, lead, country,
                            config["pain_point"], config["product_summary"],
                        )
                        for lead in batch
                    ],
                    return_exceptions=True,
                )

                # Persist drafts immediately so the UI shows them.
                for lead, reply in zip(batch, replies):
                    if not isinstance(reply, Exception) and reply.get("body"):
                        await asyncio.to_thread(
                            store_lead_draft,
                            campaign_id,
                            lead.get("source_post_url"),
                            lead.get("name"),
                            reply["body"],
                            reply.get("language"),
                        )

                valid = [
                    (lead, reply)
                    for lead, reply in zip(batch, replies)
                    if not isinstance(reply, Exception) and reply.get("body")
                ]
                if valid:
                    _push(
                        campaign_id,
                        type="think",
                        action=f"{platform.capitalize()}: sending outreach to {len(valid)} leads",
                        reasoning=f"Browser-Use firing for {platform}.",
                        channel=None,
                    )
                    await _reach_out_platform_group(campaign_id, valid, is_running)
            else:
                _push(
                    campaign_id,
                    type="wait",
                    action=f"{platform.capitalize()}: no posts found this cycle",
                    reasoning="Will retry next cycle.",
                    channel="apify",
                )

        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            _push(
                campaign_id,
                type="wait",
                action=f"{platform.capitalize()} agent error: {e}",
                reasoning="Will retry next cycle.",
                channel=None,
            )

        for _ in range(loop_seconds // 30):
            if not is_running():
                return
            await asyncio.sleep(30)


# ─── 5 independent social platform agents ───────────────────────────────────


async def run_linkedin_agent(
    campaign_id: str,
    country: str,
    config: dict,
    is_running: Callable,
) -> None:
    """LinkedIn agent: harvestapi/linkedin-post-search → Browser-Use DM/comment."""
    def _kwargs(cfg_ref: dict, cntry: str, country_cfg: dict) -> dict:
        campaign_lang = country_cfg["language"].lower().split("-")[0]
        is_english = (campaign_lang == "en")
        pain_keywords = cfg_ref["pain_keywords"]
        pain_keywords_local = cfg_ref.get("pain_keywords_local") or []
        country_code = country_cfg["search_country"]
        search_locale = country_cfg.get("search_locale", "en")

        # LinkedIn is globally English-dominant: Korean/Japanese users post in
        # English even when targeting their home market, so English keywords find
        # the most posts.  For non-English campaigns we also inject the local-
        # language keywords as a second query so purely-native posts are surfaced
        # too.  The scraper accepts a list and searches each query independently.
        en_query = " OR ".join(f'"{k}"' for k in pain_keywords[:3]) or cntry
        if is_english or not pain_keywords_local:
            keywords: str | list[str] = en_query
        else:
            local_query = " OR ".join(f'"{k}"' for k in pain_keywords_local[:3])
            keywords = [en_query, local_query]

        return dict(
            keyword=keywords,
            country=cntry,
            max_results=20,
            campaign_id=campaign_id,
            country_code=country_code,
            locale=search_locale,
            timeout_secs=120,
        )

    await _run_platform_agent(
        "linkedin", campaign_id, country, config, is_running,
        scrape_fn=scrape_linkedin_posts,
        scrape_kwargs_fn=_kwargs,
    )


async def run_reddit_agent(
    campaign_id: str,
    country: str,
    config: dict,
    is_running: Callable,
) -> None:
    """Reddit agent: trudax/reddit-scraper-lite → Browser-Use comment/DM."""
    def _kwargs(cfg_ref: dict, cntry: str, country_cfg: dict) -> dict:
        pain_keywords = cfg_ref["pain_keywords"]
        # Reddit is English-dominant worldwide — Korean/Japanese users discuss
        # tech topics in English even in country-specific subreddits (r/korea,
        # r/seoul).  Always search with English keywords; the country name
        # appended by the scraper provides geo relevance.
        keyword = " OR ".join(f'"{k}"' for k in pain_keywords[:3]) or cntry
        subs = [
            s.removeprefix("reddit.com/r/")
            for s in country_cfg.get("people_sites", [])
            if s.startswith("reddit.com/r/")
        ]
        country_code = country_cfg["search_country"]
        return dict(
            keyword=keyword,
            subreddits=subs or None,
            country=cntry,
            max_results=20,
            campaign_id=campaign_id,
            country_code=country_code,
            locale="en",
            timeout_secs=150,
        )

    await _run_platform_agent(
        "reddit", campaign_id, country, config, is_running,
        scrape_fn=scrape_reddit_posts,
        scrape_kwargs_fn=_kwargs,
    )


async def run_instagram_agent(
    campaign_id: str,
    country: str,
    config: dict,
    is_running: Callable,
) -> None:
    """Instagram agent: apify/instagram-hashtag-scraper → Browser-Use comment."""
    def _kwargs(cfg_ref: dict, cntry: str, country_cfg: dict) -> dict:
        campaign_lang = country_cfg["language"].lower().split("-")[0]
        is_english = (campaign_lang == "en")
        pain_keywords = cfg_ref["pain_keywords"]
        pain_keywords_local = cfg_ref.get("pain_keywords_local") or pain_keywords
        plain_keyword = " ".join(pain_keywords[:3]) or cntry
        plain_local = " ".join(pain_keywords_local[:3]) or cntry
        ig_plain = plain_local if not is_english else plain_keyword
        local_name = country_cfg.get("local_name", "")
        country_code = country_cfg["search_country"]
        return dict(
            keyword=ig_plain,
            country=cntry,
            max_results=15,
            campaign_id=campaign_id,
            local_country_name=local_name or None,
            country_code=country_code,
            timeout_secs=90,
            english_keyword=plain_keyword if not is_english else None,
        )

    await _run_platform_agent(
        "instagram", campaign_id, country, config, is_running,
        scrape_fn=scrape_instagram_posts,
        scrape_kwargs_fn=_kwargs,
    )


async def run_youtube_agent(
    campaign_id: str,
    country: str,
    config: dict,
    is_running: Callable,
) -> None:
    """YouTube agent: h7sDV53CddomktSi5 → Browser-Use comment."""
    def _kwargs(cfg_ref: dict, cntry: str, country_cfg: dict) -> dict:
        campaign_lang = country_cfg["language"].lower().split("-")[0]
        is_english = (campaign_lang == "en")
        pain_keywords = cfg_ref["pain_keywords"]
        pain_keywords_local = cfg_ref.get("pain_keywords_local") or pain_keywords
        plain_keyword = " ".join(pain_keywords[:3]) or cntry
        plain_local = " ".join(pain_keywords_local[:3]) or cntry
        local_name = country_cfg.get("local_name", "")
        # For non-English campaigns the actor's geo/lang params handle
        # country targeting, so we use only the local-language keywords.
        # For English campaigns we still append the country name so YouTube
        # understands the geographic context from the query alone.
        if is_english:
            base_geo = plain_keyword
            if cntry:
                base_geo = f"{base_geo} {cntry}"
            yt_keyword = base_geo
        else:
            base_geo = plain_local
            if local_name and local_name not in base_geo:
                yt_keyword = f"{local_name} {base_geo}"
            else:
                yt_keyword = base_geo
        return dict(
            keyword=yt_keyword,
            max_results=20,
            campaign_id=campaign_id,
            gl=country_cfg.get("youtube_gl"),
            hl=country_cfg.get("youtube_hl"),
            timeout_secs=90,
        )

    await _run_platform_agent(
        "youtube", campaign_id, country, config, is_running,
        scrape_fn=scrape_youtube_videos,
        scrape_kwargs_fn=_kwargs,
    )


# ─── Gmail / Google agent ────────────────────────────────────────────────────


async def run_gmail_agent(
    campaign_id: str,
    country: str,
    config: dict,
    is_running: Callable,
) -> None:
    """
    Google/Gmail opportunity-discovery agent — independent loop:

      1. Google `site:linkedin.com/in [ICP role] [country]` → profile URLs
      2. Build lead records from SERP results (no expensive email enrichment)
      3. Draft cold outreach via LLM
      4. Store drafts in DB with status="identified" (ready for human review)
      5. Sleep 4 h between cycles

    The Browser-Use send_gmail path is intentionally skipped — it requires a
    live logged-in Gmail session in the cloud browser which is too fragile.
    The drafted messages appear in the leads panel so the user can send them
    manually or re-enable Browser-Use when the profile is configured.
    """
    _push(
        campaign_id,
        type="scan",
        action=f"Gmail/Google agent online for {country} — searching for ICP contacts via Google",
        reasoning=(
            "Uses Google site:linkedin.com/in to discover ICP profiles, "
            "drafts cold outreach messages, and queues them for review."
        ),
        channel="apify",
    )

    while True:
        if not is_running():
            return

        try:
            icp_description = config["icp_description"]
            pain_point = config["pain_point"]
            product_summary = config["product_summary"]
            icp_queries = config.get("icp_search_queries") or {}
            pain_keywords = config.get("pain_keywords") or []
            pain_keywords_local = config.get("pain_keywords_local") or []

            cfg = get_country_config(country)
            campaign_lang = cfg["language"].lower().split("-")[0]
            local_name = cfg.get("local_name", "")

            li_icp_query = icp_queries.get("linkedin") or ""
            if not li_icp_query:
                # For non-English campaigns prefer local-language keywords so
                # Google surfaces Korean/Japanese/etc. LinkedIn profiles rather
                # than only English-language ones indexed for expat audiences.
                if campaign_lang != "en" and pain_keywords_local:
                    li_icp_query = " ".join(pain_keywords_local[:2])
                elif pain_keywords:
                    li_icp_query = " ".join(pain_keywords[:2])
                else:
                    li_icp_query = icp_description[:60] if icp_description else ""

            # Use the local country name (e.g. "한국") for non-English campaigns
            # so Google geo-targets results toward native-language speakers.
            country_term = local_name if (campaign_lang != "en" and local_name) else country
            google_query = f"site:linkedin.com/in {li_icp_query} {country_term}".strip()

            _push(
                    campaign_id,
                    type="think",
                    action=f"Gmail agent: Google search → {google_query[:80]}",
                    reasoning="Finding ICP LinkedIn profiles to draft outreach for.",
                    channel="apify",
                )

            serp_results = await asyncio.to_thread(
                google_search,
                google_query,
                country_code=cfg["search_country"],
                locale=cfg["search_locale"],
                max_results=GMAIL_MAX_PER_CYCLE * 3,
                campaign_id=campaign_id,
                stream="people",
            )

            profile_urls = [
                r for r in serp_results
                if "linkedin.com/in/" in r.get("url", "")
            ][:GMAIL_MAX_PER_CYCLE * 2]

            # Fallback: broader query without ICP description if first pass found nothing
            if not profile_urls:
                fallback_query = f"site:linkedin.com/in {country_term}"
                _push(
                    campaign_id,
                    type="think",
                    action=f"Gmail agent: broad fallback search → {fallback_query[:80]}",
                    reasoning="Primary ICP query returned no LinkedIn profiles; retrying with country-only filter.",
                    channel="apify",
                )
                serp_results = await asyncio.to_thread(
                    google_search,
                    fallback_query,
                    country_code=cfg["search_country"],
                    locale=cfg["search_locale"],
                    max_results=GMAIL_MAX_PER_CYCLE * 3,
                    campaign_id=campaign_id,
                    stream="people",
                )
                profile_urls = [
                    r for r in serp_results
                    if "linkedin.com/in/" in r.get("url", "")
                ][:GMAIL_MAX_PER_CYCLE * 2]

            if not profile_urls:
                _push(
                    campaign_id,
                    type="wait",
                    action="Gmail agent: no LinkedIn profiles found this cycle",
                    reasoning="Will retry next cycle.",
                    channel="apify",
                )
            else:
                # Build lead records directly from SERP results (fast, no enrichment API)
                contacts = []
                for r in profile_urls[:GMAIL_MAX_PER_CYCLE]:
                    url = r.get("url", "")
                    try:
                        slug = url.rstrip("/").split("/in/")[-1].split("?")[0]
                        name = slug.replace("-", " ").title()[:60] or "LinkedIn Contact"
                    except Exception:
                        name = "LinkedIn Contact"
                    contacts.append({
                        "platform": "gmail",
                        "name": name,
                        "title": (r.get("title") or "")[:160],
                        "company": "",
                        "linkedin_url": url,
                        "email": None,
                        "source_post_url": url,
                        "source_comment_text": (r.get("summary") or r.get("title") or "")[:600],
                        "score": 7,
                    })

                _push(
                    campaign_id,
                    type="think",
                    action=f"Gmail agent: {len(contacts)} ICP contacts found — drafting outreach",
                    reasoning="Drafting personalised cold messages via LLM.",
                    channel="llm",
                )

                replies = await asyncio.gather(
                    *[
                        _draft_reply(campaign_id, contact, country, pain_point, product_summary)
                        for contact in contacts
                    ],
                    return_exceptions=True,
                )

                # Persist leads and their drafts — surface them in the UI immediately
                save_leads(
                    campaign_id,
                    [
                        {
                            "name": c.get("name", "")[:120] or "unknown",
                            "title": c.get("title", "")[:160],
                            "company": c.get("company", "")[:120],
                            "linkedin_url": c.get("linkedin_url", "") or "",
                            "email": c.get("email") or None,
                            "score": c.get("score", 7),
                            "status": "identified",
                            "platform": "gmail",
                            "source_post_url": c.get("source_post_url") or None,
                            "source_comment_text": c.get("source_comment_text") or None,
                        }
                        for c in contacts
                    ],
                )

                for contact, reply in zip(contacts, replies):
                    if isinstance(reply, Exception) or not reply.get("body"):
                        continue
                    await asyncio.to_thread(
                        store_lead_draft,
                        campaign_id,
                        contact.get("source_post_url") or contact.get("linkedin_url"),
                        contact.get("name"),
                        reply["body"],
                        reply.get("language"),
                    )

                drafted = sum(
                    1 for r in replies
                    if not isinstance(r, Exception) and r.get("body")
                )
                _push(
                    campaign_id,
                    type="act",
                    action=f"Gmail agent: {drafted} outreach drafts queued for {len(contacts)} contacts",
                    reasoning="Leads saved to DB with drafted messages ready for review.",
                    channel="gmail",
                )
                _push(
                    campaign_id,
                    type="leads_updated",
                    action=f"gmail: {len(contacts)} new leads",
                    reasoning="",
                    channel="gmail",
                )

        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            _push(
                campaign_id,
                type="wait",
                action=f"Gmail agent error: {e}",
                reasoning="Will retry next cycle.",
                channel=None,
            )

        # 4-hour sleep between Gmail cycles
        for _ in range(GMAIL_LOOP_SECONDS // 30):
            if not is_running():
                return
            await asyncio.sleep(30)


# ─── Native-platform agent (Naver, Blind, Weibo, Xiaohongshu, Zhihu…) ────────


async def run_native_agent(
    campaign_id: str,
    country: str,
    config: dict,
    is_running: Callable,
    native_sites: list[str],
) -> None:
    """Scrape country-specific platforms that aren't covered by the mainstream agents.

    For South Korea: Naver Cafe / Blog / Kin, Blind, okky.kr
    For China:       Weibo, Xiaohongshu (Rednote), Zhihu, V2EX
    For Japan:       Qiita, Zenn, note.com
    etc.

    Falls back to Google `site:` search for any platform not in PLATFORM_SCRAPERS.
    """
    cfg = get_country_config(country)
    _push(
        campaign_id,
        type="scan",
        action=f"Native agent online for {country} — {', '.join(s.split('.')[0] for s in native_sites[:3])}",
        reasoning=f"Scraping {len(native_sites)} country-native platforms.",
        channel="apify",
    )

    while True:
        if not is_running():
            return

        try:
            pain_keywords = config["pain_keywords"]
            pain_keywords_local = config.get("pain_keywords_local") or pain_keywords
            # Native sites always use the local-language keyword
            keyword = " ".join(pain_keywords_local[:3]) or country

            raw: list[dict] = []
            for site in native_sites[:3]:
                if not is_running():
                    return
                site_results = await asyncio.to_thread(
                    scrape_platform,
                    site,
                    keyword,
                    cfg["search_country"],
                    cfg["search_locale"],
                    8,
                    campaign_id,
                )
                raw.extend(site_results)

            if raw:
                _push(
                    campaign_id,
                    type="think",
                    action=f"Native: {len(raw)} posts found — scoring ICP fit",
                    reasoning="Filtering for leads that match the ICP.",
                    channel="llm",
                )
                top = await _score_and_persist(campaign_id, raw, config["icp_description"])
                batch = top[:10]

                replies = await asyncio.gather(
                    *[
                        _draft_reply(
                            campaign_id, lead, country,
                            config["pain_point"], config["product_summary"],
                        )
                        for lead in batch
                    ],
                    return_exceptions=True,
                )

                for lead, reply in zip(batch, replies):
                    if not isinstance(reply, Exception) and reply.get("body"):
                        await asyncio.to_thread(
                            store_lead_draft,
                            campaign_id,
                            lead.get("source_post_url"),
                            lead.get("name"),
                            reply["body"],
                            reply.get("language"),
                        )

                valid = [
                    (lead, reply)
                    for lead, reply in zip(batch, replies)
                    if not isinstance(reply, Exception) and reply.get("body")
                ]
                if valid:
                    _push(
                        campaign_id,
                        type="think",
                        action=f"Native: sending outreach to {len(valid)} leads",
                        reasoning="Browser-Use firing for native platforms.",
                        channel=None,
                    )
                    await _reach_out_platform_group(campaign_id, valid, is_running)
            else:
                _push(
                    campaign_id,
                    type="wait",
                    action="Native: no posts found this cycle",
                    reasoning="Will retry next cycle.",
                    channel="apify",
                )

        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            _push(
                campaign_id,
                type="wait",
                action=f"Native agent error: {e}",
                reasoning="Will retry next cycle.",
                channel=None,
            )

        for _ in range(PEOPLE_LOOP_SECONDS // 30):
            if not is_running():
                return
            await asyncio.sleep(30)


# ─── Top-level orchestrator ──────────────────────────────────────────────────


async def run_people_stream(
    campaign_id: str,
    country: str,
    config: dict,
    is_running: Callable,
) -> None:
    """Launch all platform agents simultaneously for the target country.

    Each agent runs its own eternal loop (scrape → score → outreach → sleep)
    completely independently — a slow Apify run on one platform never blocks
    the others.  Agents that are not relevant for the selected country are
    simply not started (e.g. Weibo/Xiaohongshu only start for China, Naver
    only starts for South Korea/Japan, etc.).
    """
    cfg = get_country_config(country)
    social = cfg.get("social", [])

    tasks: list[asyncio.Task] = []

    # LinkedIn — always on
    tasks.append(asyncio.create_task(
        run_linkedin_agent(campaign_id, country, config, is_running)
    ))

    # Reddit — when the country config lists reddit subreddits or reddit in social
    has_reddit = "reddit" in social or any(
        s.startswith("reddit.com/r/") for s in cfg.get("people_sites", [])
    )
    if has_reddit:
        tasks.append(asyncio.create_task(
            run_reddit_agent(campaign_id, country, config, is_running)
        ))

    if "instagram" in social:
        tasks.append(asyncio.create_task(
            run_instagram_agent(campaign_id, country, config, is_running)
        ))

    if "youtube" in social:
        tasks.append(asyncio.create_task(
            run_youtube_agent(campaign_id, country, config, is_running)
        ))

    # Native sites (country-specific platforms without a dedicated agent)
    native_sites = [
        s for s in cfg.get("people_sites", [])
        if not s.startswith("reddit.com/r/")
    ]
    if native_sites:
        tasks.append(asyncio.create_task(
            run_native_agent(campaign_id, country, config, is_running, native_sites)
        ))

    # Gmail — always on
    tasks.append(asyncio.create_task(
        run_gmail_agent(campaign_id, country, config, is_running)
    ))

    _push(
        campaign_id,
        type="scan",
        action=(
            f"People stream: {len(tasks)} agents launched for {country} "
            f"({', '.join(social[:4])}{'…' if len(social) > 4 else ''})"
        ),
        reasoning="Each platform runs its own independent scrape → score → outreach loop.",
        channel="apify",
    )

    # Run all agents concurrently; if any raises (shouldn't — they catch internally)
    # let the others continue.
    await asyncio.gather(*tasks, return_exceptions=True)
