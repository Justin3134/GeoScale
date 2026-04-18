"""
Main agent loop.

Step 0: Analyze the company website with Apify (website-content-crawler +
        google-search-scraper) + LLM to derive ICP, pain point, and a list
        of pain-keyword phrases for search.
Step 1: Spawn two parallel sub-streams (people + opportunities) which each
        run on their own cadence and post events to the same SSE buffer.

Each event has a `stream` tag — the dashboard splits them into the
people / opportunities / system panels.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from agent.country import get_country_config
from agent.llm import think
from agent.prompts import (
    AGENT_SYSTEM_PROMPT,
    COMPANY_ANALYSIS_PROMPT,
)
from agent.streams.opportunities import run_opportunities_stream
from agent.streams.people import run_people_stream
from agent.streams.signals import run_signals_stream
from agent.tools import analyze_company
from models.db import Campaign, SessionLocal

# In-memory ring buffer of events per campaign for SSE consumers.
MAX_BUFFERED_EVENTS = 800
active_streams: dict[str, list[dict]] = {}


def push_event(campaign_id: str, event: dict) -> None:
    """Push event to SSE stream + persist to DB so reconnects replay history."""
    event = {
        "stream": event.get("stream", "system"),
        **event,
        "time": datetime.utcnow().isoformat(),
    }
    bucket = active_streams.setdefault(campaign_id, [])
    bucket.append(event)
    overflow = len(bucket) - MAX_BUFFERED_EVENTS
    if overflow > 0:
        del bucket[:overflow]

    # Persist every event so the dashboard can rehydrate after reconnect.
    try:
        from agent.memory import log_action  # local import to avoid cycle
        # Stash the preview blob (drafted text + target) inside `outcome`
        # so the dashboard can reconstruct preview cards on a hard reload.
        outcome = None
        if event.get("preview"):
            try:
                outcome = json.dumps(event["preview"])[:4000]
            except (TypeError, ValueError):
                outcome = None
        log_action(
            campaign_id,
            event.get("type", "think"),
            event.get("action", "")[:1000],
            event.get("reasoning", "")[:1000],
            event.get("channel"),
            outcome=outcome,
            stream=event.get("stream", "system"),
            live_url=event.get("live_url"),
            session_ended=bool(event.get("session_ended", False)),
        )
    except Exception:
        pass


# ─── Helpers ───────────────────────────────────────────────────────────────


def _persist_campaign_meta(
    campaign_id: str,
    *,
    goal: str | None = None,
    language: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if c:
            if goal is not None:
                c.goal = goal
            if language is not None:
                c.language = language
            db.commit()
    finally:
        db.close()


def _campaign_running(campaign_id: str) -> bool:
    db = SessionLocal()
    try:
        c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        return bool(c and c.status == "running")
    finally:
        db.close()


# ─── Main entry point ─────────────────────────────────────────────────────


async def run_agent(campaign_id: str, company_url: str, country: str) -> None:
    """Long-running coroutine that orchestrates both streams for a campaign."""
    cfg = get_country_config(country)
    _persist_campaign_meta(campaign_id, language=cfg["language"])

    push_event(
        campaign_id,
        {
            "type": "scan",
            "stream": "system",
            "action": f"Agent deployed for {country}. Reading {company_url}…",
            "reasoning": (
                f"Will operate in {cfg['language_name']} on {', '.join(cfg['social'])}."
            ),
            "channel": "apify",
        },
    )

    # ── Step 0: company analysis ─────────────────────────────────────────
    try:
        site = await asyncio.to_thread(analyze_company, company_url, campaign_id)
        raw = await asyncio.to_thread(
            think,
            AGENT_SYSTEM_PROMPT,
            COMPANY_ANALYSIS_PROMPT.format(
                company_url=company_url,
                country=country,
                language_name=cfg["language_name"],
                site_signals=json.dumps(site.get("site_signals", [])[:6], ensure_ascii=False),
            ),
            max_tokens=1200,
        )
        inferred = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        push_event(
            campaign_id,
            {
                "type": "wait",
                "stream": "system",
                "action": f"Company analysis failed: {e}",
                "reasoning": "Falling back to defaults.",
                "channel": "llm",
            },
        )
        inferred = {}

    goal = inferred.get("goal") or f"Find pipeline + community presence in {country}"
    icp_description = (
        inferred.get("icp_description")
        or "Operations leaders at growth-stage startups"
    )
    industry = inferred.get("industry") or "B2B SaaS"
    pain_point = inferred.get("pain_point") or "operational efficiency"
    value_prop = inferred.get("value_prop") or "We help teams move faster."
    pain_keywords = inferred.get("pain_keywords") or [pain_point]
    product_summary = f"{value_prop} (We address: {pain_point}.)"
    icp_search_queries: dict = inferred.get("icp_search_queries") or {}

    _persist_campaign_meta(campaign_id, goal=goal)

    push_event(
        campaign_id,
        {
            "type": "think",
            "stream": "system",
            "action": f"Inferred goal: {goal}",
            "reasoning": (
                f"ICP: {icp_description}. Industry: {industry}. "
                f"Pain: {pain_point}. Keywords: {', '.join(pain_keywords[:5])}."
            ),
            "channel": "llm",
        },
    )

    # ── Step 1: spawn the three parallel streams ───────────────────────
    def is_running() -> bool:
        return _campaign_running(campaign_id)

    people_task = asyncio.create_task(
        run_people_stream(
            campaign_id,
            country,
            icp_description,
            pain_point,
            pain_keywords,
            product_summary,
            is_running,
            icp_search_queries=icp_search_queries,
        )
    )
    opps_task = asyncio.create_task(
        run_opportunities_stream(
            campaign_id,
            country,
            goal,
            industry,
            product_summary,
            is_running,
        )
    )
    signals_task = asyncio.create_task(
        run_signals_stream(
            campaign_id,
            country,
            industry,
            pain_keywords,
            pain_point,
            product_summary,
            is_running,
        )
    )

    push_event(
        campaign_id,
        {
            "type": "scan",
            "stream": "system",
            "action": (
                "Three streams spawned: People (30m) + Opportunities (2h) + Signals (4h)."
            ),
            "reasoning": (
                "Signals stream watches funding rounds + hiring spikes for buying intent. "
                "Independent cadences — any stream can fail without taking the others down."
            ),
            "channel": None,
        },
    )

    all_tasks = [people_task, opps_task, signals_task]

    try:
        done, pending = await asyncio.wait(
            all_tasks, return_when=asyncio.FIRST_EXCEPTION
        )
        for t in done:
            exc = t.exception()
            if exc:
                push_event(
                    campaign_id,
                    {
                        "type": "wait",
                        "stream": "system",
                        "action": f"Stream crashed: {exc}",
                        "reasoning": "Other streams continue; this one is dead until restart.",
                        "channel": None,
                    },
                )
        for t in pending:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
    except asyncio.CancelledError:
        for t in all_tasks:
            t.cancel()
        for t in all_tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        push_event(
            campaign_id,
            {
                "type": "wait",
                "stream": "system",
                "action": "Agent task cancelled.",
                "reasoning": "Server shutdown or campaign paused.",
                "channel": None,
            },
        )
        raise
