"""
Main agent loop.

Launches 5 fully independent platform agents simultaneously from second 1,
plus company analysis and a buying-signals stream:

  LinkedIn agent   — harvestapi/linkedin-post-search + Google SERP fallback
  Reddit agent     — trudax/reddit-scraper-lite → Browser-Use comment/DM
  Instagram agent  — apify/instagram-hashtag-scraper → Browser-Use comment
  YouTube agent    — api-ninja/youtube-search-scraper → Browser-Use comment
  Gmail agent      — Google SERP discovery → draft leads (no Browser-Use send)

All agents share a mutable config dict seeded with safe defaults on deploy.
Company analysis runs in the background and upgrades that config in-place,
so every agent automatically picks up the refined ICP and pain keywords on
its next cycle — no restart needed.

Crash isolation: each agent is wrapped in `_resilient` which restarts it
after a 60-second backoff. One crashed agent never touches the others.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from urllib.parse import urlparse

from agent.country import get_country_config
from agent.llm import think, translate_keywords
from agent.prompts import (
    AGENT_SYSTEM_PROMPT,
    COMPANY_ANALYSIS_PROMPT,
)
from agent.streams.people import (
    run_linkedin_agent,
    run_reddit_agent,
    run_instagram_agent,
    run_youtube_agent,
    run_gmail_agent,
    run_native_agent,
)
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

    try:
        from agent.memory import log_action  # local import to avoid cycle
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


def _extract_company_name(url: str) -> str:
    """Pull a short identifier from a URL to use as the initial scrape keyword."""
    u = url if "://" in url else f"https://{url}"
    netloc = urlparse(u).netloc or url.split("/")[0]
    stem = netloc.replace("www.", "").split(".")[0]
    return stem or netloc


# ─── Resilient agent wrapper ───────────────────────────────────────────────


async def _resilient(
    name: str,
    campaign_id: str,
    coro_fn,
    *args,
) -> None:
    """
    Run `coro_fn(*args)` forever, restarting it after a 60-second backoff
    whenever it raises an unhandled exception.

    A clean exit (is_running() returned False inside the coroutine) propagates
    normally. asyncio.CancelledError is always re-raised immediately.
    """
    while True:
        try:
            await coro_fn(*args)
            return  # clean exit — is_running() returned False
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            push_event(
                campaign_id,
                {
                    "type": "wait",
                    "stream": "system",
                    "action": f"{name} crashed — restarting in 60 s: {e}",
                    "reasoning": (
                        "Agent raised an unhandled exception. "
                        "Other agents are unaffected and continue running."
                    ),
                    "channel": None,
                },
            )
            await asyncio.sleep(60)


# ─── Background analysis task ──────────────────────────────────────────────


async def _run_analysis(
    campaign_id: str,
    company_url: str,
    country: str,
    cfg_ref: dict,         # shared mutable config — updated in-place when done
) -> None:
    """Crawl the company site + SERP + LLM concurrently with the stream first-cycle."""
    country_cfg = get_country_config(country)

    push_event(
        campaign_id,
        {
            "type": "scan",
            "stream": "system",
            "action": f"Analysing {company_url} — direct HTTP crawl + Google SERP in parallel…",
            "reasoning": (
                "Website crawl uses httpx (no Apify slot) so all 6 platform agents "
                "grab their Apify slots immediately. SERP runs via Apify."
            ),
            "channel": "apify",
        },
    )

    try:
        site = await asyncio.to_thread(analyze_company, company_url, campaign_id)
        n = len(site.get("site_signals", []))
        push_event(
            campaign_id,
            {
                "type": "think",
                "stream": "system",
                "action": f"Crawl complete — {n} signals. Running DigitalOcean LLM analysis…",
                "reasoning": "Deriving ICP, pain keywords, and GTM goal from page text + SERP.",
                "channel": "llm",
            },
        )
        raw = await asyncio.to_thread(
            think,
            AGENT_SYSTEM_PROMPT,
            COMPANY_ANALYSIS_PROMPT.format(
                company_url=company_url,
                country=country,
                language_name=country_cfg["language_name"],
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
                "reasoning": "All agents continue with initial keyword-based defaults.",
                "channel": "llm",
            },
        )
        return

    goal             = inferred.get("goal")             or cfg_ref["goal"]
    icp              = inferred.get("icp_description")  or cfg_ref["icp_description"]
    industry         = inferred.get("industry")         or cfg_ref["industry"]
    pain_point       = inferred.get("pain_point")       or cfg_ref["pain_point"]
    value_prop       = inferred.get("value_prop")       or "We help teams move faster."
    keywords         = inferred.get("pain_keywords")    or [pain_point]
    local_keywords   = inferred.get("pain_keywords_local") or keywords
    icp_queries      = inferred.get("icp_search_queries")  or {}

    # For non-English campaigns, always translate the English pain keywords into
    # the target language so every Apify search query is in the local language
    # and returns local-language content natively.  We translate `keywords`
    # (the authoritative English list) rather than whatever the analysis LLM
    # returned for `pain_keywords_local`, because the LLM sometimes silently
    # falls back to English for non-Latin-script languages.
    campaign_lang = country_cfg["language"].lower().split("-")[0]
    if campaign_lang != "en":
        try:
            translated = await asyncio.to_thread(
                translate_keywords,
                keywords,
                country_cfg["language_name"],
            )
            local_keywords = translated
        except Exception:
            pass

    cfg_ref.update({
        "goal":                goal,
        "icp_description":     icp,
        "industry":            industry,
        "pain_point":          pain_point,
        "pain_keywords":       keywords,
        "pain_keywords_local": local_keywords,
        "product_summary":     f"{value_prop} (We address: {pain_point}.)",
        "icp_search_queries":  icp_queries,
        "analysis_complete":   True,
    })

    _persist_campaign_meta(campaign_id, goal=goal)

    push_event(
        campaign_id,
        {
            "type": "think",
            "stream": "system",
            "action": f"Analysis done — all 6 agents upgrade on next cycle. Goal: {goal}",
            "reasoning": (
                f"ICP: {icp}. Industry: {industry}. "
                f"Pain: {pain_point}. Keywords: {', '.join(keywords[:5])}."
            ),
            "channel": "llm",
        },
    )


# ─── Main entry point ─────────────────────────────────────────────────────


async def run_agent(campaign_id: str, company_url: str, country: str) -> None:
    """
    Launch all 6 platform agents + analysis + signals simultaneously.

    Each platform agent is wrapped in `_resilient` so crashes auto-restart
    without affecting any other agent. Uses ALL_COMPLETED so the supervisor
    only exits when every task finishes (i.e. when is_running() returns False).
    """
    country_cfg = get_country_config(country)
    _persist_campaign_meta(campaign_id, language=country_cfg["language"])

    company_name = _extract_company_name(company_url)

    # Shared mutable config — seeded with safe defaults, upgraded by analysis.
    campaign_config: dict = {
        "goal":                f"Find pipeline + community presence in {country}",
        "icp_description":     "Operations leaders at growth-stage startups",
        "industry":            "B2B SaaS",
        "pain_point":          company_name,
        "pain_keywords":       [company_name],
        "pain_keywords_local": [company_name],
        "product_summary":     f"We help companies like {company_name} move faster.",
        "icp_search_queries":  {},
        "analysis_complete":   False,
    }

    # Country-native platforms (Naver, Blind, Weibo, Xiaohongshu, Zhihu, etc.)
    # These are any people_sites that are NOT Reddit subreddits.
    native_sites = [
        s for s in country_cfg.get("people_sites", [])
        if not s.startswith("reddit.com/r/")
    ]

    push_event(
        campaign_id,
        {
            "type": "scan",
            "stream": "system",
            "action": (
                f"Agent deployed for {country}. "
                f"Launching all agents simultaneously — analysis runs first so "
                f"real pain-point keywords drive every search from the start."
            ),
            "reasoning": (
                f"Platforms: LinkedIn · Reddit · Instagram · YouTube · Gmail"
                + (f" · Native ({', '.join(s.split('.')[0] for s in native_sites[:3])})" if native_sites else "")
                + f". Each agent waits for LLM analysis before its first scrape."
            ),
            "channel": "apify",
        },
    )

    def is_running() -> bool:
        return _campaign_running(campaign_id)

    # ── Analysis runs immediately so platform agents have real keywords ───
    # Website crawl uses httpx (no Apify slot), only 1 Google SERP call is
    # made. Platform agents wait up to 3 min for analysis_complete before
    # their first scrape, so there is no keyword-quality cold-start problem.
    async def _run_analysis_now() -> None:
        if is_running():
            await _run_analysis(campaign_id, company_url, country, campaign_config)

    async def _delayed_signals(delay: int = 300) -> None:
        await asyncio.sleep(delay)
        if is_running():
            await run_signals_stream(campaign_id, country, campaign_config, is_running)

    # ── Build all tasks ───────────────────────────────────────────────────
    # Each platform agent is wrapped in _resilient so unhandled crashes
    # auto-restart after 60 s without touching any sibling agent.
    all_tasks = [
        # Analysis runs immediately — platform agents wait for it before
        # their first scrape so real keywords are always used.
        asyncio.create_task(_run_analysis_now(), name="analysis"),
        asyncio.create_task(
            _resilient("LinkedIn agent", campaign_id, run_linkedin_agent,
                       campaign_id, country, campaign_config, is_running),
            name="linkedin",
        ),
        asyncio.create_task(
            _resilient("Reddit agent", campaign_id, run_reddit_agent,
                       campaign_id, country, campaign_config, is_running),
            name="reddit",
        ),
        asyncio.create_task(
            _resilient("Instagram agent", campaign_id, run_instagram_agent,
                       campaign_id, country, campaign_config, is_running),
            name="instagram",
        ),
        asyncio.create_task(
            _resilient("YouTube agent", campaign_id, run_youtube_agent,
                       campaign_id, country, campaign_config, is_running),
            name="youtube",
        ),
        asyncio.create_task(
            _resilient("Gmail agent", campaign_id, run_gmail_agent,
                       campaign_id, country, campaign_config, is_running),
            name="gmail",
        ),
        asyncio.create_task(_delayed_signals(), name="signals"),
    ]

    # Add native-platform agent only when the country has non-Reddit native sites.
    if native_sites:
        all_tasks.append(
            asyncio.create_task(
                _resilient("Native agent", campaign_id, run_native_agent,
                           campaign_id, country, campaign_config, is_running, native_sites),
                name="native",
            )
        )

    try:
        # ALL_COMPLETED: wait for every task to finish naturally (is_running()
        # returns False) rather than cancelling everything on the first crash.
        done, _ = await asyncio.wait(all_tasks, return_when=asyncio.ALL_COMPLETED)
        for t in done:
            exc = t.exception() if not t.cancelled() else None
            if exc:
                push_event(
                    campaign_id,
                    {
                        "type": "wait",
                        "stream": "system",
                        "action": f"Task '{t.get_name()}' exited with error: {exc}",
                        "reasoning": "Other agents continued independently.",
                        "channel": None,
                    },
                )
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
