"""
Signals stream — buying-intent feed.

Every 4h:
  1. Pull funding + hiring signals from the country's configured Apify actors.
  2. For each new signal, resolve the company → top-1 likely-buyer LinkedIn
     profile via `enrichment.enrich_lead_via_linkedin`.
  3. Draft a signal-aware DM via `SIGNAL_OUTREACH_PROMPT` (the first sentence
     references the specific signal — congrats on raise / saw the open req).
  4. Send the DM via `send_linkedin_dm` (browser-use), bounded to a small
     batch per cycle to keep cost under control.
"""

from __future__ import annotations

import asyncio
import json

from agent import approval as _approval
from agent.streams.people import _has_language_mixing, _post_is_latin_script, _resolve_reply_language

from agent.country import get_country_config
from agent.enrichment import enrich_lead_via_linkedin, looks_like_real_name
from agent.llm import think
from agent.memory import (
    increment_channel_sent,
    save_leads,
    save_signals,
    update_signal_status,
)
from agent.prompts import AGENT_SYSTEM_PROMPT, SIGNAL_OUTREACH_PROMPT
from agent.signals import scrape_funding_signals, scrape_hiring_signals
from agent.tools import send_linkedin_dm

SIGNALS_LOOP_SECONDS = 4 * 60 * 60  # 4h cadence
SIGNAL_DM_DELAY_SECONDS = 60
PREVIEW_HOLD_SECONDS = 5        # time the preview card sits before browser-use fires
MAX_SIGNALS_PER_CYCLE = 8       # signals to persist per cycle
MAX_DMS_PER_CYCLE = 3           # signals we actually DM per cycle


def _push(campaign_id: str, **kwargs) -> None:
    from agent.loop import push_event  # local import to avoid cycle

    event = {"stream": "signals", **kwargs}
    push_event(campaign_id, event)


async def _harvest_signals(
    campaign_id: str,
    country: str,
    industry: str,
    pain_keywords: list[str],
) -> list[dict]:
    """Run both signal categories in parallel."""
    funding_task = asyncio.to_thread(
        scrape_funding_signals,
        country,
        industry,
        12,
        campaign_id,
    )
    hiring_task = asyncio.to_thread(
        scrape_hiring_signals,
        country,
        pain_keywords or [industry],
        None,
        10,
        campaign_id,
    )
    funding, hiring = await asyncio.gather(
        funding_task, hiring_task, return_exceptions=True
    )

    out: list[dict] = []
    if isinstance(funding, list):
        out.extend(funding)
    elif isinstance(funding, Exception):
        _push(
            campaign_id,
            type="wait",
            action=f"Funding signal scrape failed: {funding}",
            reasoning="Skipping funding for this cycle.",
            channel="apify",
        )
    if isinstance(hiring, list):
        out.extend(hiring)
    elif isinstance(hiring, Exception):
        _push(
            campaign_id,
            type="wait",
            action=f"Hiring signal scrape failed: {hiring}",
            reasoning="Skipping hiring for this cycle.",
            channel="apify",
        )

    return out


def _dedupe_signals(signals: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for s in signals:
        key = (s.get("signal_url") or "").strip().lower() or (
            (s.get("company_name") or "").lower()
            + "|"
            + (s.get("signal_text") or "")[:80].lower()
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


async def _draft_signal_dm(
    campaign_id: str,
    country: str,
    signal: dict,
    recipient_name: str,
    recipient_role: str,
    product_summary: str,
    pain_point: str,
) -> dict:
    cfg = get_country_config(country)

    signal_text = signal.get("signal_text", "")

    # Reply in the language of the signal text, not just the campaign language.
    # A Korean-campaign signal whose LinkedIn post is in English should get
    # an English DM, not a Korean one.
    reply_lang, reply_lang_name = _resolve_reply_language(signal_text, cfg)

    prompt_kwargs = dict(
        reply_language=reply_lang,
        signal_language_name=reply_lang_name,
        campaign_language_name=cfg["language_name"],
        country=country,
        signal_type=signal.get("signal_type", "funding"),
        signal_text=signal_text,
        signal_url=signal.get("signal_url", ""),
        company_name=signal.get("company_name", ""),
        recipient_role=recipient_role or signal.get("suggested_role") or "Founder",
        product_summary=product_summary,
        pain_point=pain_point,
        cultural_context=cfg["cultural_context"],
    )

    result: dict = {"language": reply_lang, "body": "", "english_gloss": ""}
    for _attempt in range(3):
        try:
            raw = await asyncio.to_thread(
                think,
                AGENT_SYSTEM_PROMPT,
                SIGNAL_OUTREACH_PROMPT.format(**prompt_kwargs),
                max_tokens=900,
            )
            result = json.loads(raw)
        except Exception:
            break

        if not _has_language_mixing(result.get("body", ""), reply_lang):
            return result
        # Mixed-language output — retry with an explicit purity reminder injected
        # into the signal text so the model sees it prominently.
        prompt_kwargs["signal_text"] = (
            "(IMPORTANT: write in pure "
            + reply_lang_name
            + " only — no words from any other language)\n"
            + signal_text
        )

    return result


async def _resolve_and_dm(
    campaign_id: str,
    country: str,
    signal: dict,
    signal_id: int,
    product_summary: str,
    pain_point: str,
) -> None:
    """Turn one signal into one (or zero) DMs."""
    suggested_role = signal.get("suggested_role") or "Founder"
    company = signal.get("company_name") or ""

    # For engagement signals we already have a person + LinkedIn URL embedded
    # in `raw`. For funding/hiring we have to search LinkedIn for the role.
    raw = signal.get("raw") or {}
    linkedin_url = raw.get("linkedin_url") or ""
    name = raw.get("name") or ""

    if not linkedin_url:
        # Search for "<role> at <company>" — we use suggested_role as the
        # name field hack: the search-by-name actor is name-required, so
        # we DM the founder by name discovery only when we have a name.
        # If we have neither name nor URL, we still persist the signal but
        # cannot DM yet (a human can pick it up from the dashboard).
        if not name or not looks_like_real_name(name):
            _push(
                campaign_id,
                type="wait",
                action=f"Signal logged (no contact yet): {company} — {suggested_role}",
                reasoning="Surfaced for human follow-up; auto-DM needs a name.",
                channel="apify",
            )
            update_signal_status(signal_id, "new")
            return
        enriched = await asyncio.to_thread(
            enrich_lead_via_linkedin,
            name,
            company or None,
            None,
            False,
            campaign_id,
        )
        linkedin_url = enriched.get("linkedin_url") or ""
        if enriched.get("headline"):
            suggested_role = enriched["headline"][:80]

    if not linkedin_url:
        _push(
            campaign_id,
            type="wait",
            action=f"Could not resolve a LinkedIn profile for {company}.",
            reasoning="Signal kept for next cycle / human review.",
            channel="apify",
        )
        update_signal_status(signal_id, "new")
        return

    # Persist a Lead row so the signal feeds the regular leads dashboard.
    save_leads(
        campaign_id,
        [
            {
                "name": (name or company)[:120] or "signal lead",
                "title": suggested_role[:160],
                "company": company[:120],
                "linkedin_url": linkedin_url,
                "email": None,
                "score": 9,
                "status": "identified",
                "platform": "linkedin",
                "source_post_url": signal.get("signal_url") or None,
                "source_comment_text": (signal.get("signal_text") or "")[:600],
            }
        ],
    )

    reply = await _draft_signal_dm(
        campaign_id,
        country,
        signal,
        recipient_name=name or company,
        recipient_role=suggested_role,
        product_summary=product_summary,
        pain_point=pain_point,
    )
    body = (reply.get("body") or "").strip()
    if not body:
        update_signal_status(signal_id, "skipped", resolved_lead_url=linkedin_url)
        return

    # Preview: surface the drafted signal-aware DM + the LinkedIn target
    # BEFORE the browser-use task fires. When require_human_approval is on,
    # wait for explicit human approval instead of sleeping.
    require_approval = await asyncio.to_thread(
        _approval.get_require_approval, campaign_id
    )
    approval_id = _approval.register() if require_approval else None

    _push(
        campaign_id,
        type="preview",
        action=f"About to DM → {name or company} ({signal.get('signal_type','signal')})",
        reasoning=(reply.get("english_gloss") or signal.get("signal_text") or "")[:300],
        channel="linkedin",
        preview={
            "target_name": name or company,
            "target_url": linkedin_url,
            "platform": "linkedin",
            "body_local": body,
            "english_gloss": reply.get("english_gloss") or "",
            "signal_text": signal.get("signal_text") or "",
            "signal_type": signal.get("signal_type") or "",
            "approval_id": approval_id,
        },
    )

    if require_approval and approval_id:
        approved = await _approval.wait(approval_id)
        if not approved:
            _push(
                campaign_id,
                type="wait",
                action=f"DM skipped → {name or company}: rejected by human",
                reasoning="Human validation rejected or timed out for this action.",
                channel="linkedin",
            )
            return
    else:
        await asyncio.sleep(PREVIEW_HOLD_SECONDS)

    await send_linkedin_dm(linkedin_url, body, campaign_id=campaign_id)
    increment_channel_sent(campaign_id, "linkedin")
    update_signal_status(signal_id, "contacted", resolved_lead_url=linkedin_url)

    _push(
        campaign_id,
        type="act",
        action=(
            f"Signal DM sent → {company} ({signal.get('signal_type','signal')})"
        ),
        reasoning=(reply.get("english_gloss") or signal.get("signal_text") or "")[:300],
        channel="linkedin",
    )


async def run_signals_stream(
    campaign_id: str,
    country: str,
    industry: str,
    pain_keywords: list[str],
    pain_point: str,
    product_summary: str,
    is_running,
) -> None:
    """Long-running coroutine. Stops when is_running() returns False."""
    _push(
        campaign_id,
        type="scan",
        action=f"Signals stream online for {country}",
        reasoning=(
            "Watching funding rounds + hiring spikes + competitor engagement. "
            "Each match = one signal-aware DM."
        ),
        channel="apify",
    )

    while True:
        if not is_running():
            return
        try:
            harvested = await _harvest_signals(
                campaign_id, country, industry, pain_keywords
            )
            harvested = _dedupe_signals(harvested)[:MAX_SIGNALS_PER_CYCLE]

            _push(
                campaign_id,
                type="think",
                action=f"Detected {len(harvested)} new buying-intent signals.",
                reasoning="Persisting and resolving the top signals into DMs.",
                channel="apify",
            )

            inserted_ids = save_signals(campaign_id, harvested)
            # Re-zip ids back onto the signal dicts in insertion order. Skipped
            # duplicates won't have an id; we just process the ones that did.
            id_iter = iter(inserted_ids)
            scheduled: list[tuple[int, dict]] = []
            for sig in harvested:
                try:
                    sid = next(id_iter)
                except StopIteration:
                    break
                scheduled.append((sid, sig))

            for sid, sig in scheduled[:MAX_DMS_PER_CYCLE]:
                if not is_running():
                    return
                await _resolve_and_dm(
                    campaign_id,
                    country,
                    sig,
                    sid,
                    product_summary,
                    pain_point,
                )
                await asyncio.sleep(SIGNAL_DM_DELAY_SECONDS)

        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            _push(
                campaign_id,
                type="wait",
                action=f"Signals stream hit error: {e}",
                reasoning="Will retry next cycle.",
                channel=None,
            )

        for _ in range(SIGNALS_LOOP_SECONDS // 60):
            if not is_running():
                return
            await asyncio.sleep(60)
