"""
Opportunities stream — discover hackathons, conferences, accelerators,
press outlets, and tech communities in the target country, then submit a
local-language pitch via browser-use (contact form / press email / etc.).
"""

from __future__ import annotations

import asyncio
import json

from agent import approval as _approval
from agent.country import get_country_config
from agent.streams.people import _has_language_mixing
from agent.llm import think
from agent.memory import save_opportunities, update_opportunity_status
from agent.prompts import (
    AGENT_SYSTEM_PROMPT,
    OPPORTUNITY_CLASSIFICATION_PROMPT,
    OPPORTUNITY_PITCH_PROMPT,
)
from agent.tools import (
    crawl_contact_page,
    find_opportunity_listings,
    send_gmail,
    submit_contact_form,
)

OPPS_LOOP_SECONDS = 2 * 60 * 60  # 2 h
PITCH_DELAY_SECONDS = 60
PREVIEW_HOLD_SECONDS = 5


def _push(campaign_id: str, **kwargs) -> None:
    from agent.loop import push_event
    event = {"stream": "opportunities", **kwargs}
    push_event(campaign_id, event)


async def _discover(
    campaign_id: str,
    country: str,
    industry: str,
) -> list[dict]:
    cfg = get_country_config(country)
    queries = [q.format(industry=industry, country=country) for q in cfg["opportunity_queries"]]
    raw = await asyncio.to_thread(
        find_opportunity_listings,
        queries,
        cfg["search_country"],
        cfg["search_locale"],
        6,
        campaign_id,
    )
    return raw


async def _classify(
    campaign_id: str,
    raw: list[dict],
    goal: str,
    country: str,
    industry: str,
    limit: int = 10,
) -> list[dict]:
    if not raw:
        return []
    try:
        out_raw = await asyncio.to_thread(
            think,
            AGENT_SYSTEM_PROMPT,
            OPPORTUNITY_CLASSIFICATION_PROMPT.format(
                results=json.dumps(raw[:30], ensure_ascii=False),
                goal=goal,
                country=country,
                industry=industry,
                limit=limit,
            ),
            max_tokens=2000,
        )
        parsed = json.loads(out_raw)
        return parsed.get("opportunities", [])[:limit]
    except Exception as e:  # noqa: BLE001
        _push(
            campaign_id,
            type="wait",
            action=f"Classification LLM call failed: {e}",
            reasoning="Falling back to raw SERP results.",
            channel="llm",
        )
        return [
            {
                "type": "event",
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "summary": r.get("summary", ""),
                "score": 5,
            }
            for r in raw[:limit]
        ]


async def _pitch_one(
    campaign_id: str,
    opp: dict,
    country: str,
    product_summary: str,
    relevance: str,
) -> None:
    cfg = get_country_config(country)
    url = opp.get("url", "")
    if not url:
        return

    contact = await asyncio.to_thread(crawl_contact_page, url, campaign_id)

    prompt_kwargs = dict(
        language=cfg["language"],
        language_name=cfg["language_name"],
        country=country,
        opp_type=opp.get("type", "event"),
        opp_title=opp.get("title", ""),
        page_excerpt=contact.get("page_excerpt", "")[:1000],
        product_summary=product_summary,
        relevance=relevance,
        cultural_context=cfg["cultural_context"],
    )

    pitch: dict = {}
    for _attempt in range(3):
        try:
            raw = await asyncio.to_thread(
                think,
                AGENT_SYSTEM_PROMPT,
                OPPORTUNITY_PITCH_PROMPT.format(**prompt_kwargs),
                max_tokens=1200,
            )
            pitch = json.loads(raw)
        except Exception as e:  # noqa: BLE001
            _push(
                campaign_id,
                type="wait",
                action=f"Pitch draft failed for {opp.get('title','')}: {e}",
                reasoning="Skipping this opportunity this cycle.",
                channel="llm",
            )
            return

        if not _has_language_mixing(pitch.get("body", ""), cfg["language"]):
            break
        # Mixed-language output — retry with a stricter purity reminder.
        prompt_kwargs["relevance"] = (
            "(IMPORTANT: write in pure "
            + cfg["language_name"]
            + " only — no words from any other language)\n"
            + relevance
        )

    body = pitch.get("body", "")
    subject = pitch.get("subject", "") or "Partnership inquiry"
    if not body:
        return

    contact_email = contact.get("contact_email") or None
    contact_url = contact.get("contact_url") or url

    # Preview: surface what we're about to send BEFORE opening the browser.
    # When require_human_approval is on, wait for explicit human approval.
    require_approval = await asyncio.to_thread(
        _approval.get_require_approval, campaign_id
    )
    approval_id = _approval.register() if require_approval else None

    _push(
        campaign_id,
        type="preview",
        action=f"Sending pitch → {opp.get('type','')}: {opp.get('title','')[:80]}",
        reasoning=(pitch.get("english_gloss") or "")[:300],
        channel="browser-use",
        preview={
            "target_name": opp.get("title", "")[:120],
            "target_url": contact_email or contact_url,
            "platform": opp.get("type", "event"),
            "subject": subject,
            "body_local": body,
            "english_gloss": pitch.get("english_gloss") or "",
            "approval_id": approval_id,
        },
    )

    if require_approval and approval_id:
        approved = await _approval.wait(approval_id)
        if not approved:
            _push(
                campaign_id,
                type="wait",
                action=f"Pitch skipped → '{opp.get('title','')[:60]}': rejected by human",
                reasoning="Human validation rejected or timed out for this action.",
                channel="browser-use",
            )
            return
    else:
        await asyncio.sleep(PREVIEW_HOLD_SECONDS)

    # ── Actually send the pitch ───────────────────────────────────────────
    # Prefer email if we found one; fall back to contact form.
    sent = False
    if contact_email:
        result = await send_gmail(
            contact_email,
            subject,
            body,
            campaign_id=campaign_id,
        )
        sent = result.get("success", False)
        if not sent:
            _push(
                campaign_id,
                type="wait",
                action=f"Email send failed for '{opp.get('title','')[:60]}': {str(result.get('error',''))[:160]}",
                reasoning="Browser Use could not send the Gmail. Check profile auth.",
                channel="browser-use",
            )
    else:
        result = await submit_contact_form(
            contact_url,
            body,
            campaign_id=campaign_id,
        )
        sent = result.get("success", False)
        if not sent:
            _push(
                campaign_id,
                type="wait",
                action=f"Contact form failed for '{opp.get('title','')[:60]}': {str(result.get('error',''))[:160]}",
                reasoning="Browser Use could not submit the contact form. Check profile auth.",
                channel="browser-use",
            )

    if sent:
        # Only record pitch_text (which triggers the "PITCH SENT" UI label)
        # when the message was actually delivered.
        update_opportunity_status(
            campaign_id,
            url,
            "contacted",
            pitch_text=body,
            contact_url=contact_url,
            contact_email=contact_email,
        )
        _push(
            campaign_id,
            type="act",
            action=f"Pitch sent ✓ → {opp.get('title','')[:80]}",
            reasoning=f"Delivered via {'email ' + contact_email if contact_email else 'contact form ' + contact_url[:60]}",
            channel="browser-use",
        )


async def run_opportunities_stream(
    campaign_id: str,
    country: str,
    goal: str,
    industry: str,
    product_summary: str,
    is_running,
) -> None:
    """Long-running coroutine. Stops when is_running() returns False."""
    _push(
        campaign_id,
        type="scan",
        action=f"Opportunities stream online for {country}",
        reasoning=f"Hunting hackathons / conferences / press / accelerators in {industry}.",
        channel="apify",
    )

    while True:
        if not is_running():
            return
        try:
            raw = await _discover(campaign_id, country, industry)
            _push(
                campaign_id,
                type="think",
                action=f"Found {len(raw)} candidate opportunities. Classifying.",
                reasoning="LLM classification into hackathon / event / press / accelerator / community.",
                channel="llm",
            )
            opps = await _classify(campaign_id, raw, goal, country, industry, limit=8)

            if opps:
                save_opportunities(
                    campaign_id,
                    [
                        {
                            "type": o.get("type", "event"),
                            "title": (o.get("title") or "")[:200],
                            "description": (o.get("summary") or "")[:600],
                            "url": o.get("url", ""),
                            "contact_url": None,
                            "contact_email": None,
                            "score": int(o.get("score", 5) or 5),
                            "status": "identified",
                        }
                        for o in opps
                        if o.get("url")
                    ],
                )

            relevance = f"Our product helps with: {product_summary}"
            for opp in opps[:3]:
                if not is_running():
                    return
                await _pitch_one(
                    campaign_id, opp, country, product_summary, relevance
                )
                await asyncio.sleep(PITCH_DELAY_SECONDS)

        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            _push(
                campaign_id,
                type="wait",
                action=f"Opportunities stream hit error: {e}",
                reasoning="Will retry next cycle.",
                channel=None,
            )

        for _ in range(OPPS_LOOP_SECONDS // 60):
            if not is_running():
                return
            await asyncio.sleep(60)
