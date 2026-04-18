"""
Tooling for GeoScale.

Two providers, all wrapped so failures surface to the SSE stream and DB
instead of being silently swallowed:

  Apify          — paid actors for LinkedIn / Reddit / native social /
                   Google SERP / website-content-crawler. This is the ONE
                   scraping provider — no Tavily, no Bing, no custom HTTP.
  Browser-Use    — real-world actions (DMs, comments, contact-form submits)

Every public function takes an optional `campaign_id` so that error events can
be pushed onto the live agent feed for that campaign.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from apify_client import ApifyClient
from apify_client.errors import ApifyApiError

try:
    from browser_use_sdk.v3 import AsyncBrowserUse
except Exception:  # pragma: no cover - SDK not installed yet during pip install step
    AsyncBrowserUse = None  # type: ignore[assignment]

_apify: ApifyClient | None = None


# ─── Cost guardrail (MAX_APIFY_SPEND_USD) ───────────────────────────────────
# Belt-and-suspenders for hackathon billing. We estimate spend from a small
# (actor → $/result) lookup and stop new signal/enrichment runs once the
# soft cap is hit. Per-cycle budgets in `streams/*.py` keep us well below
# the cap on a normal run; this is the catastrophic-loop kill switch.

# Per-result $ estimate per actor. Defaults to $0.005 when absent.
_APIFY_COST_PER_RESULT: dict[str, float] = {
    "harvestapi/linkedin-post-search": 0.008,
    "trudax/reddit-scraper-lite": 0.0009,
    "apify/google-search-scraper": 0.005,
    "apify/website-content-crawler": 0.0035,
    "hypebridge/blind-post-scraper": 0.03,
    "naver_crawling/naver-search-cafe-crawling": 0.10,
    "huggable_quote/naver-blog-cafe-scraper": 0.005,
    "oxygenated_quagmire/naver-kin-scraper": 0.005,
    "piotrv1001/weibo-scraper": 0.001,
    "easyapi/rednote-xiaohongshu-search-scraper": 0.005,
    "memo23/naukri-scraper": 0.001,
    "logiover/apna-co-jobs-scraper": 0.0045,
    "curious_coder/linkedin-jobs-scraper": 0.001,
    "complex_intricate_networks/india-startup-vc-intelligence-economic-times-capital-tracker": 0.01,
    "complex_intricate_networks/fundraising-and-startup-funding-scraper": 0.01,
    "oxygenated_quagmire/naver-news-scraper": 0.0005,
    "fortuitous_pirate/south-korea-dart-scraper": 0.0035,
    "harvestapi/linkedin-profile-search-by-name": 0.004,
    "harvestapi/linkedin-profile-scraper": 0.004,
    "harvestapi/linkedin-profile-reactions": 0.002,
    "harvestapi/linkedin-profile-comments": 0.002,
    "clockworks/tiktok-scraper": 0.004,
    "streamers/youtube-scraper": 0.003,
}

# Streams subject to the cap (pulled out so user-initiated UI calls are not
# blocked). Cheap streams ("system", "people") still keep running even after
# the cap — only the most expensive optional flows are halted.
_APIFY_CAPPED_STREAMS = {"signals"}

_apify_spend_usd: float = 0.0
_apify_cap_warned: bool = False


def _apify_default_cap() -> float:
    try:
        return float(os.getenv("MAX_APIFY_SPEND_USD", "25"))
    except ValueError:
        return 25.0


def _apify_cost_estimate(actor_id: str, item_count: int) -> float:
    rate = _APIFY_COST_PER_RESULT.get(actor_id, 0.005)
    # Most paid actors have a flat per-result fee; treat the actor-start fee
    # as a small fixed overhead.
    return round(rate * max(1, item_count) + 0.005, 4)


def get_apify_spend_usd() -> float:
    return round(_apify_spend_usd, 4)


# ─── Clients ────────────────────────────────────────────────────────────────


def _apify_client() -> ApifyClient:
    global _apify
    if _apify is None:
        _apify = ApifyClient(os.getenv("APIFY_API_KEY"))
    return _apify


# ─── Error / status surfacing ───────────────────────────────────────────────
# We import these helpers lazily inside functions to avoid an import cycle
# (tools.py is imported from agent/loop.py which sets up active_streams).


def _push_event(campaign_id: str | None, event: dict) -> None:
    if not campaign_id:
        return
    from agent.loop import push_event  # local import to break cycle
    push_event(campaign_id, event)


def _log(
    campaign_id: str | None,
    action_type: str,
    action: str,
    reasoning: str,
    channel: str | None = None,
    stream: str = "system",
) -> None:
    if not campaign_id:
        return
    from agent.memory import log_action
    log_action(campaign_id, action_type, action, reasoning, channel, stream=stream)


def _push_error(
    campaign_id: str | None,
    provider: str,
    detail: str,
    actor_id: str | None = None,
    stream: str = "system",
) -> None:
    msg = f"{provider} error" + (f" ({actor_id})" if actor_id else "")
    _push_event(
        campaign_id,
        {
            "type": "error",
            "stream": stream,
            "action": f"{msg}: {detail[:240]}",
            "reasoning": detail[:600],
            "channel": provider,
        },
    )


def _push_tool_event(
    campaign_id: str | None,
    provider: str,
    description: str,
    stream: str = "system",
) -> None:
    """Lightweight 'I'm calling X' breadcrumb for the live action footer."""
    _push_event(
        campaign_id,
        {
            "type": "scan",
            "stream": stream,
            "action": description,
            "reasoning": f"{provider} call in progress",
            "channel": provider,
        },
    )


# ─── APIFY — Company analysis (replaces Tavily entirely) ───────────────────


def analyze_company(company_url: str, campaign_id: str | None = None) -> dict:
    """Read a company's public web presence so the agent can derive ICP / pain.

    Two Apify calls only, NO Tavily:
      1. `apify/website-content-crawler`  → home page + 3 deep pages of text
      2. `apify/google-search-scraper`    → 1 page of `"<domain>" customers OR pricing`

    The return shape stays compatible with the previous Tavily-based
    `analyze_company`, exposing a `site_signals` list of {title, summary, url}
    dicts that the company-analysis prompt already consumes.
    """
    url = company_url if "://" in company_url else f"https://{company_url}"
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path.split("/")[0]

    site_signals: list[dict] = []

    # ── 1. Crawl the homepage (cheap, ~$0.014 for 4 pages) ────────────────
    crawl_items = _apify_run(
        "apify/website-content-crawler",
        {
            "startUrls": [{"url": url}],
            "maxCrawlPages": 4,
            "maxCrawlDepth": 1,
            "crawlerType": "playwright:firefox",
            "proxyConfiguration": {"useApifyProxy": True},
        },
        campaign_id=campaign_id,
        stream="system",
        timeout_secs=120,
        max_items=4,
    )
    for it in crawl_items:
        text = (it.get("text") or it.get("markdown") or "")[:600]
        if not text:
            continue
        site_signals.append(
            {
                "title": (it.get("title") or it.get("metadata", {}).get("title") or "")[:200],
                "summary": text,
                "url": it.get("url") or url,
            }
        )

    # ── 2. One SERP for "what they sell / who buys" (cheap, ~$0.005) ──────
    serp = google_search(
        f'"{domain}" (customers OR pricing OR product)',
        country_code="us",
        locale="en",
        max_results=5,
        campaign_id=campaign_id,
        stream="system",
    )
    site_signals.extend(serp)

    return {"site_signals": site_signals, "domain": domain}


# ─── APIFY — Generic run helper ────────────────────────────────────────────


def _apify_run(
    actor_id: str,
    run_input: dict,
    campaign_id: str | None = None,
    stream: str = "system",
    timeout_secs: int = 180,
    max_items: int = 50,
) -> list[dict]:
    """
    Run an Apify actor and return dataset items.

    Surfaces every failure mode (auth error, actor not found, run timeout,
    paywall) into the SSE stream so we never silently get an empty list.
    """
    apify = _apify_client()

    global _apify_spend_usd, _apify_cap_warned
    cap = _apify_default_cap()
    if cap > 0 and _apify_spend_usd >= cap and stream in _APIFY_CAPPED_STREAMS:
        if not _apify_cap_warned:
            _push_error(
                campaign_id,
                "apify",
                f"MAX_APIFY_SPEND_USD={cap} reached (≈${_apify_spend_usd:.2f}). "
                "Pausing signals/enrichment runs. Increase the env var to resume.",
                actor_id=actor_id,
                stream=stream,
            )
            _apify_cap_warned = True
        return []

    _push_tool_event(
        campaign_id, "apify", f"Apify start → {actor_id}", stream=stream,
    )

    try:
        run = apify.actor(actor_id).call(
            run_input=run_input,
            timeout_secs=timeout_secs,
        )
    except ApifyApiError as e:
        _push_error(campaign_id, "apify", str(e), actor_id=actor_id, stream=stream)
        return []
    except Exception as e:  # noqa: BLE001
        _push_error(
            campaign_id, "apify",
            f"unexpected: {type(e).__name__}: {e}",
            actor_id=actor_id, stream=stream,
        )
        return []

    if not run or not run.get("defaultDatasetId"):
        _push_error(
            campaign_id, "apify",
            "actor returned no dataset id",
            actor_id=actor_id, stream=stream,
        )
        return []

    status = run.get("status")
    if status not in (None, "SUCCEEDED"):
        _push_error(
            campaign_id, "apify",
            f"actor finished with status={status}",
            actor_id=actor_id, stream=stream,
        )

    items: list[dict] = []
    try:
        for item in apify.dataset(run["defaultDatasetId"]).iterate_items():
            items.append(item)
            if len(items) >= max_items:
                break
    except Exception as e:  # noqa: BLE001
        _push_error(
            campaign_id, "apify",
            f"dataset read failed: {e}",
            actor_id=actor_id, stream=stream,
        )
        return items

    est_cost = _apify_cost_estimate(actor_id, len(items))
    _apify_spend_usd += est_cost

    _push_event(
        campaign_id,
        {
            "type": "scan",
            "stream": stream,
            "action": (
                f"Apify done → {actor_id} ({len(items)} items, est ${est_cost:.3f})"
            ),
            "reasoning": (
                f"Run succeeded. Total Apify spend this session: ≈${_apify_spend_usd:.2f}."
            ),
            "channel": "apify",
        },
    )
    return items


# ─── APIFY — People-stream scrapers ─────────────────────────────────────────


def scrape_linkedin_posts(
    keyword: str,
    country: str | None = None,  # kept for API compat; not directly used by actor
    max_results: int = 20,
    campaign_id: str | None = None,
) -> list[dict]:
    """
    Public LinkedIn posts mentioning a pain-point keyword.
    Actor: harvestapi/linkedin-post-search (paid, no cookies, reliable).
    """
    items = _apify_run(
        "harvestapi/linkedin-post-search",
        {
            "searchQueries": [keyword] if isinstance(keyword, str) else list(keyword),
            "maxPosts": max_results,
            "postedLimit": "month",
            "sortBy": "date",
            "profileScraperMode": "short",
        },
        campaign_id=campaign_id,
        stream="people",
        max_items=max_results,
    )

    out: list[dict] = []
    for item in items:
        author = item.get("author") or item.get("profile") or {}
        out.append(
            {
                "platform": "linkedin",
                "name": (
                    author.get("fullName")
                    or author.get("name")
                    or f"{author.get('firstName','')} {author.get('lastName','')}"
                ).strip()[:120] or "linkedin user",
                "title": (author.get("headline") or author.get("position") or "")[:160],
                "company": (author.get("company") or author.get("companyName") or "")[:120],
                "linkedin_url": author.get("profileUrl")
                    or author.get("publicProfileUrl")
                    or item.get("authorUrl")
                    or "",
                "source_post_url": item.get("postUrl")
                    or item.get("url")
                    or item.get("linkedinUrl")
                    or "",
                "source_comment_text": (
                    item.get("text") or item.get("content") or item.get("postText") or ""
                )[:600],
            }
        )
    return out


def scrape_reddit_posts(
    keyword: str,
    subreddits: list[str] | None = None,
    max_results: int = 30,
    campaign_id: str | None = None,
) -> list[dict]:
    """
    Reddit posts/comments matching a keyword.
    Actor: trudax/reddit-scraper-lite (paid, lite tier).
    """
    start_urls: list[dict] = []
    if subreddits:
        for sub in subreddits:
            sub_clean = sub.strip().lstrip("/").removeprefix("r/")
            start_urls.append(
                {"url": f"https://www.reddit.com/r/{sub_clean}/search/?q={keyword}&sort=new&restrict_sr=1"}
            )
    else:
        start_urls.append(
            {"url": f"https://www.reddit.com/search/?q={keyword}&sort=new"}
        )

    items = _apify_run(
        "trudax/reddit-scraper-lite",
        {
            "startUrls": start_urls,
            "maxItems": max_results,
            "maxPostCount": max_results,
            "searchPosts": True,
            "searchComments": False,
            "searchCommunities": False,
            "searchUsers": False,
            "skipComments": True,
            "skipUserPosts": True,
            "skipCommunity": True,
            "sort": "new",
            "time": "month",
            "proxy": {"useApifyProxy": True},
        },
        campaign_id=campaign_id,
        stream="people",
        max_items=max_results,
    )

    out: list[dict] = []
    for item in items:
        out.append(
            {
                "platform": "reddit",
                "name": item.get("username") or item.get("author") or "redditor",
                "title": (item.get("title") or "")[:160],
                "company": "",
                "linkedin_url": "",
                "source_post_url": item.get("url") or "",
                "source_comment_text": (
                    item.get("body") or item.get("text") or item.get("title") or ""
                )[:600],
            }
        )
    return out


# ─── APIFY — TikTok scraper ──────────────────────────────────────────────────


def scrape_tiktok_posts(
    keyword: str,
    max_results: int = 15,
    campaign_id: str | None = None,
) -> list[dict]:
    """
    TikTok videos matching a keyword/hashtag query.
    Actor: clockworks/tiktok-scraper.

    The keyword is stripped of Boolean operators (OR / quotes) since TikTok
    search is hashtag/keyword-based, not boolean-query-based.
    """
    clean_keyword = keyword.replace('"', "").replace(" OR ", " ").strip()

    items = _apify_run(
        "clockworks/tiktok-scraper",
        {
            "searchQueries": [clean_keyword],
            "maxItems": max_results,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": False,
        },
        campaign_id=campaign_id,
        stream="people",
        max_items=max_results,
    )

    out: list[dict] = []
    for item in items:
        author = item.get("authorMeta") or {}
        out.append(
            {
                "platform": "tiktok",
                "name": (
                    author.get("name")
                    or author.get("nickName")
                    or author.get("uniqueId")
                    or "tiktok user"
                )[:120],
                "title": (item.get("text") or item.get("desc") or "")[:160],
                "company": "",
                "linkedin_url": "",
                "source_post_url": item.get("webVideoUrl") or item.get("videoUrl") or "",
                "source_comment_text": (
                    item.get("text") or item.get("desc") or ""
                )[:600],
            }
        )
    return out


# ─── APIFY — YouTube video search ──────────────────────────────────────────


def scrape_youtube_videos(
    keyword: str,
    max_results: int = 15,
    campaign_id: str | None = None,
) -> list[dict]:
    """
    YouTube videos matching a keyword query.
    Actor: streamers/youtube-scraper.

    Boolean operators are stripped since YouTube search is plain-text only.
    The video description is used as source_comment_text so the LLM can craft
    a reply referencing what the creator/community discussed.
    """
    from urllib.parse import quote_plus

    clean_keyword = keyword.replace('"', "").replace(" OR ", " ").strip()
    search_url = f"https://www.youtube.com/results?search_query={quote_plus(clean_keyword)}"

    items = _apify_run(
        "streamers/youtube-scraper",
        {
            "startUrls": [{"url": search_url}],
            "maxResults": max_results,
            "type": "video",
            "proxy": {"useApifyProxy": True},
        },
        campaign_id=campaign_id,
        stream="people",
        max_items=max_results,
    )

    out: list[dict] = []
    for item in items:
        video_url = (
            item.get("url")
            or item.get("videoUrl")
            or item.get("id") and f"https://www.youtube.com/watch?v={item['id']}"
            or ""
        )
        if not video_url:
            continue
        channel_name = (
            item.get("channelName")
            or item.get("channel")
            or item.get("ownerChannelName")
            or "YouTube user"
        )
        out.append(
            {
                "platform": "youtube",
                "name": str(channel_name)[:120],
                "title": (item.get("title") or "")[:160],
                "company": "",
                "linkedin_url": "",
                "source_post_url": video_url,
                "source_comment_text": (
                    item.get("description") or item.get("title") or ""
                )[:600],
            }
        )
    return out


# ─── APIFY — ICP-role LinkedIn profile discovery ─────────────────────────────


def scrape_linkedin_profiles_by_icp(
    icp_query: str,
    country: str | None = None,
    max_results: int = 10,
    campaign_id: str | None = None,
) -> list[dict]:
    """Find LinkedIn profiles matching an ICP role/title via Google site: search.

    Uses `site:linkedin.com/in` + role query to proactively find the target
    personas — people who *would* benefit from the product, not just people
    who have already posted about a pain.

    Returns lead-shaped dicts with `linkedin_url` set so `_reach_out` can DM
    them even though they have no `source_post_url`.
    """
    query = f"site:linkedin.com/in {icp_query}"
    if country:
        query += f' "{country}"'

    serp = google_search(
        query,
        max_results=max_results,
        campaign_id=campaign_id,
        stream="people",
    )

    out: list[dict] = []
    for r in serp:
        url = r.get("url", "")
        if "linkedin.com/in/" not in url:
            continue
        try:
            slug = url.rstrip("/").split("/in/")[-1].split("?")[0]
            # Drop the trailing alphanumeric ID segment LinkedIn sometimes adds
            parts = [p for p in slug.split("-") if p and not (len(p) <= 3 and p.isalnum())]
            name = " ".join(p.title() for p in parts[:3]) if parts else "LinkedIn User"
        except Exception:
            name = "LinkedIn User"

        out.append(
            {
                "platform": "linkedin",
                "name": name[:120],
                "title": (r.get("title") or "")[:160],
                "company": "",
                "linkedin_url": url,
                "source_post_url": "",
                "source_comment_text": (r.get("summary") or r.get("title") or "")[:600],
            }
        )
    return out


# ─── APIFY — Google SERP wrapper for country-native sites ───────────────────


def google_search(
    query: str,
    country_code: str = "us",
    locale: str = "en",
    max_results: int = 20,
    campaign_id: str | None = None,
    stream: str = "system",
) -> list[dict]:
    """
    Google SERP via the official Apify scraper. Used for:
      - country-native social (Naver Cafe, Zhihu, Quora-IN, Weibo) via site: filter
      - opportunity discovery (hackathons, press releases, events)
    """
    items = _apify_run(
        "apify/google-search-scraper",
        {
            "queries": query,
            "resultsPerPage": min(max_results, 50),
            "maxPagesPerQuery": 1,
            "countryCode": country_code,
            "languageCode": locale,
        },
        campaign_id=campaign_id,
        stream=stream,
        max_items=max_results,
    )

    results: list[dict] = []
    for page in items:
        for organic in (page.get("organicResults") or [])[:max_results]:
            results.append(
                {
                    "title": (organic.get("title") or "")[:200],
                    "summary": (organic.get("description") or "")[:400],
                    "url": organic.get("url") or "",
                }
            )
        if len(results) >= max_results:
            break
    return results[:max_results]


def scrape_native_social(
    site: str,
    keyword: str,
    country_code: str,
    locale: str,
    max_results: int = 10,
    campaign_id: str | None = None,
) -> list[dict]:
    """
    Country-native social platforms (Naver, Zhihu, Quora-IN, etc.) via Google `site:`.
    Returns lead-shaped dicts with a source_post_url so we can comment/reply.
    """
    serp = google_search(
        f'site:{site} {keyword}',
        country_code=country_code,
        locale=locale,
        max_results=max_results,
        campaign_id=campaign_id,
        stream="people",
    )

    platform = _platform_from_site(site)
    out: list[dict] = []
    for r in serp:
        out.append(
            {
                "platform": platform,
                "name": _author_from_url(r.get("url", "")) or platform,
                "title": (r.get("title") or "")[:160],
                "company": "",
                "linkedin_url": "",
                "source_post_url": r.get("url", ""),
                "source_comment_text": (r.get("summary") or r.get("title") or "")[:600],
            }
        )
    return out


# ─── APIFY — Opportunity discovery + contact-page resolution ───────────────


def find_opportunity_listings(
    queries: list[str],
    country_code: str,
    locale: str,
    max_per_query: int = 8,
    campaign_id: str | None = None,
) -> list[dict]:
    """Run the configured opportunity queries and return raw SERP results."""
    out: list[dict] = []
    for q in queries:
        out.extend(
            google_search(
                q,
                country_code=country_code,
                locale=locale,
                max_results=max_per_query,
                campaign_id=campaign_id,
                stream="opportunities",
            )
        )
    return out


def crawl_contact_page(
    url: str,
    campaign_id: str | None = None,
) -> dict:
    """
    Use the Apify website-content-crawler to read an opportunity's landing page
    and extract a contact email or contact form URL.
    """
    items = _apify_run(
        "apify/website-content-crawler",
        {
            "startUrls": [{"url": url}],
            "maxCrawlPages": 4,
            "maxCrawlDepth": 1,
            "crawlerType": "playwright:firefox",
            "proxyConfiguration": {"useApifyProxy": True},
        },
        campaign_id=campaign_id,
        stream="opportunities",
        timeout_secs=120,
        max_items=4,
    )

    text_blob = ""
    contact_url = ""
    for it in items:
        text_blob += "\n" + (it.get("text") or "")[:5000]
        u = it.get("url", "")
        if not contact_url and ("contact" in u.lower() or "apply" in u.lower()):
            contact_url = u

    email_match = re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text_blob
    )
    return {
        "contact_email": email_match.group(0) if email_match else "",
        "contact_url": contact_url or url,
        "page_excerpt": text_blob.strip()[:1200],
    }


# ─── BROWSER-USE — Real world actions ───────────────────────────────────────


_bu_client: "AsyncBrowserUse | None" = None


def _bu() -> "AsyncBrowserUse":
    global _bu_client
    if AsyncBrowserUse is None:
        raise RuntimeError(
            "browser-use-sdk not installed. Run `pip install -r requirements.txt`."
        )
    if not os.getenv("BROWSER_USE_API_KEY"):
        raise RuntimeError(
            "BROWSER_USE_API_KEY not set. Add it to backend/.env "
            "and restart the server so the agent can actually post DMs / comments."
        )
    if _bu_client is None:
        _bu_client = AsyncBrowserUse()
    return _bu_client


# "idle" = browser initialising, not yet running — NOT a terminal state.
# Lifecycle: created → idle → running → stopped / timed_out / error.
_BU_TERMINAL_STATUSES = {"stopped", "timed_out", "error"}


async def browser_use_task(
    task: str,
    campaign_id: str | None = None,
    stream: str = "system",
    description: str | None = None,
) -> dict[str, Any]:
    """Run a natural-language task in the cloud browser.

    Creates the session up-front so the live_url (iframe-embeddable) is
    surfaced to the dashboard the instant the browser opens — not after the
    task finishes. We then poll the session to completion.

    Always forwards the persistent Browser Use Cloud profile (cookies for
    LinkedIn, Reddit, etc.), the agreed agent model, and the residential
    proxy region — all sourced from env so they can be rotated without code
    changes.
    """
    profile_id = os.getenv("BROWSER_USE_PROFILE_ID") or None
    model = os.getenv("BROWSER_USE_MODEL") or None
    proxy = os.getenv("BROWSER_USE_PROXY_COUNTRY") or None

    breadcrumb = description or "browser-use: running task"
    if profile_id:
        breadcrumb += f" [profile={profile_id[:8]}…"
        if model:
            breadcrumb += f" model={model}"
        breadcrumb += "]"
    _push_tool_event(campaign_id, "browser-use", breadcrumb, stream=stream)

    create_kwargs: dict[str, Any] = {}
    if profile_id:
        create_kwargs["profile_id"] = profile_id
    if model:
        create_kwargs["model"] = model
    if proxy:
        create_kwargs["proxy_country_code"] = proxy

    try:
        bu = _bu()
    except Exception as e:  # noqa: BLE001
        # Most common cause: BROWSER_USE_API_KEY not set or SDK missing.
        # Surface this as an `error` event so it shows up red in the feed
        # instead of silently swallowing the outreach attempt.
        _push_error(campaign_id, "browser-use", str(e), stream=stream)
        return {"success": False, "error": str(e)}

    live_url: str | None = None
    try:
        session = await bu.sessions.create(task, **create_kwargs)
        session_id = str(session.id)
        live_url = getattr(session, "live_url", None)

        # Surface the live URL immediately so the dashboard iframe can
        # connect while the agent is still working.
        _push_event(
            campaign_id,
            {
                "type": "act",
                "stream": stream,
                "action": description or "browser-use: session live",
                "reasoning": "Watch the agent in real time.",
                "channel": "browser-use",
                "live_url": live_url,
            },
        )

        # Poll until the session reaches a terminal state.
        deadline = asyncio.get_event_loop().time() + 14400  # 4h cap
        out: str | None = None
        while asyncio.get_event_loop().time() < deadline:
            current = await bu.sessions.get(session_id)
            status = getattr(current.status, "value", str(current.status))
            if status in _BU_TERMINAL_STATUSES:
                out = getattr(current, "output", None)
                break
            await asyncio.sleep(2)
        else:
            raise TimeoutError(f"browser-use session {session_id} timed out")

        _push_event(
            campaign_id,
            {
                "type": "act",
                "stream": stream,
                "action": (description or "browser-use: task complete"),
                "reasoning": (out or "")[:400],
                "channel": "browser-use",
                "live_url": live_url,
                "session_ended": True,
            },
        )
        return {"success": True, "output": out, "live_url": live_url}
    except Exception as e:  # noqa: BLE001
        # If the session was already created and surfaced to the dashboard,
        # mark it as ended so the UI doesn't keep showing it as live.
        if live_url:
            _push_event(
                campaign_id,
                {
                    "type": "act",
                    "stream": stream,
                    "action": description or "browser-use: session failed",
                    "reasoning": str(e)[:400],
                    "channel": "browser-use",
                    "live_url": live_url,
                    "session_ended": True,
                },
            )
        _push_error(campaign_id, "browser-use", str(e), stream=stream)
        return {"success": False, "error": str(e)}


_AUTH_GUARD = (
    "The browser is already signed in via the saved Browser Use Cloud profile "
    "(cookies hydrate automatically). Do NOT attempt to log in, do NOT submit "
    "any login form, and do NOT enter an email, password, OTP, or 2FA code. "
    "If you hit a login wall, security checkpoint, CAPTCHA, or any step-up "
    "auth, abort immediately and return exactly: auth_required."
)


async def post_linkedin_comment(
    post_url: str,
    comment_text: str,
    campaign_id: str | None = None,
) -> dict:
    task = f"""
    Open LinkedIn post: {post_url}
    {_AUTH_GUARD}
    Locate the comment composer on the post.
    Type exactly this comment: {comment_text}
    Submit it.
    Verify the comment is visible in the thread before returning.
    Return: success with the posted comment URL, or auth_required, or the verbatim error.
    """.strip()
    return await browser_use_task(
        task, campaign_id=campaign_id, stream="people",
        description=f"LinkedIn comment → {post_url[:60]}",
    )


async def send_linkedin_dm(
    profile_url: str,
    message: str,
    campaign_id: str | None = None,
) -> dict:
    task = f"""
    Open LinkedIn profile: {profile_url}
    {_AUTH_GUARD}
    Click the Message button on the profile.
    Type exactly this message: {message}
    Send it.
    Confirm the message appears in the conversation thread before returning.
    Return: success, or auth_required, or the verbatim error.
    """.strip()
    return await browser_use_task(
        task, campaign_id=campaign_id, stream="people",
        description=f"LinkedIn DM → {profile_url[:60]}",
    )


async def post_reddit_comment(
    post_url: str,
    comment: str,
    campaign_id: str | None = None,
) -> dict:
    task = f"""
    Open Reddit post: {post_url}
    {_AUTH_GUARD}
    Locate the comment / reply box on the post.
    Type exactly this comment: {comment}
    Submit the comment.
    Verify it is visible in the thread before returning.
    Return: success with the posted comment URL, or auth_required, or the verbatim error.
    """.strip()
    return await browser_use_task(
        task, campaign_id=campaign_id, stream="people",
        description=f"Reddit comment → {post_url[:60]}",
    )


async def send_reddit_dm(
    username: str,
    message: str,
    campaign_id: str | None = None,
) -> dict:
    """Send a Reddit DM via the compose page — fallback when no post_url."""
    clean = username.lstrip("/").removeprefix("u/").strip()
    task = f"""
    Open https://www.reddit.com/message/compose/?to={clean}
    {_AUTH_GUARD}
    Fill in the Subject field with: Connecting with you
    Fill in the Message field with exactly: {message}
    Click the Send button.
    Confirm the message was sent (look for a confirmation banner or empty compose box) before returning.
    Return: success, or auth_required, or the verbatim error.
    """.strip()
    return await browser_use_task(
        task, campaign_id=campaign_id, stream="people",
        description=f"Reddit DM → u/{clean[:60]}",
    )


async def post_tiktok_comment(
    video_url: str,
    comment: str,
    campaign_id: str | None = None,
) -> dict:
    """Comment on a TikTok video via Browser Use."""
    task = f"""
    Open TikTok video: {video_url}
    {_AUTH_GUARD}
    Locate the comment input box on the video page (usually labelled "Add comment…").
    Click it to activate it.
    Type exactly this comment: {comment}
    Submit the comment (press Enter or click the Post button).
    Verify the comment is visible in the thread before returning.
    Return: success with the video URL, or auth_required, or the verbatim error.
    """.strip()
    return await browser_use_task(
        task, campaign_id=campaign_id, stream="people",
        description=f"TikTok comment → {video_url[:60]}",
    )


async def post_youtube_comment(
    video_url: str,
    comment: str,
    campaign_id: str | None = None,
) -> dict:
    task = f"""
    Open YouTube video: {video_url}
    {_AUTH_GUARD}
    Scroll down to the comment section below the video.
    Click on the "Add a comment…" input field to focus it.
    Type exactly this comment: {comment}
    Click the "Comment" button to submit it.
    Verify the comment appears in the thread before returning.
    Return: success with the posted comment URL, or auth_required, or the verbatim error.
    """.strip()
    return await browser_use_task(
        task, campaign_id=campaign_id, stream="people",
        description=f"YouTube comment → {video_url[:60]}",
    )


async def post_native_comment(
    post_url: str,
    comment: str,
    platform: str,
    campaign_id: str | None = None,
) -> dict:
    """Generic browser-use comment for non-English platforms (Naver, Quora, Zhihu...)."""
    task = f"""
    Open {platform} post: {post_url}
    {_AUTH_GUARD}
    Locate the comment / reply box.
    Type exactly this comment: {comment}
    Submit the comment.
    Verify it was posted before returning.
    Return: success, or auth_required, or the verbatim error.
    """.strip()
    return await browser_use_task(
        task, campaign_id=campaign_id, stream="people",
        description=f"{platform} reply → {post_url[:60]}",
    )


async def send_gmail(
    to_email: str,
    subject: str,
    body: str,
    campaign_id: str | None = None,
) -> dict:
    """Open Gmail (already signed in via Browser Use profile) and send an email."""
    task = f"""
    Open https://mail.google.com/mail/u/0/#compose
    {_AUTH_GUARD}
    A compose window should open automatically. If it does not, click the Compose button.
    Fill in the To field with: {to_email}
    Fill in the Subject field with: {subject}
    Fill in the body with exactly: {body}
    Click the Send button.
    Confirm "Message sent" or equivalent confirmation appears before returning.
    Return: success, or auth_required, or the verbatim error.
    """.strip()
    return await browser_use_task(
        task, campaign_id=campaign_id, stream="people",
        description=f"Gmail → {to_email[:60]}",
    )


async def submit_contact_form(
    contact_url: str,
    pitch: str,
    campaign_id: str | None = None,
    sender_email: str | None = None,
) -> dict:
    """Open a contact / call-for-speakers / press page and submit a pitch."""
    sender = sender_email or os.getenv("CONTACT_FROM_EMAIL", "outreach@example.com")
    task = f"""
    Open {contact_url}.
    Find the contact form, sponsorship form, or "call for speakers" form.
    If the page is a press-release contact page, find the listed email and stop —
    return that email so the caller can send manually.
    Otherwise, fill the form. Use sender email: {sender}. Subject: Partnership inquiry.
    Body: {pitch}
    Submit the form. Confirm success or capture the error message verbatim.
    """.strip()
    return await browser_use_task(
        task, campaign_id=campaign_id, stream="opportunities",
        description=f"contact form → {contact_url[:60]}",
    )


# ─── helpers ────────────────────────────────────────────────────────────────


def _platform_from_site(site: str) -> str:
    s = site.lower()
    if "naver" in s:
        return "naver"
    if "quora" in s:
        return "quora"
    if "zhihu" in s:
        return "zhihu"
    if "weibo" in s:
        return "weibo"
    if "xiaohongshu" in s:
        return "xiaohongshu"
    if "reddit" in s:
        return "reddit"
    if "qiita" in s or "zenn" in s or "note.com" in s:
        return s.split(".")[0]
    return s.split(".")[0]


def _author_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        path = urlparse(url).path.strip("/")
        return path.split("/")[0][:40] if path else ""
    except Exception:
        return ""


# Kept for backward compatibility with any old imports.
def find_linkedin_leads(search_query: str, max_results: int = 20) -> list[dict]:
    return scrape_linkedin_posts(search_query, max_results=max_results)


def healthcheck_apify() -> dict:
    """Verify the API key works AND that one actor in each category is alive.

    Per-category checks (cheap — fetches actor metadata only, no run):
      - platform   : `hypebridge/blind-post-scraper`
      - signal     : `complex_intricate_networks/fundraising-and-startup-funding-scraper`
      - enrichment : `harvestapi/linkedin-profile-search-by-name`

    A failed metadata fetch → that whole category is flagged so the demo can
    fall back to the Google `site:` shim instead of crashing on stage.
    """
    apify = _apify_client()
    try:
        u = apify.user("me").get()
        username = (u or {}).get("username") or "unknown"
    except ApifyApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    categories = {
        "platform": "hypebridge/blind-post-scraper",
        "signal": "complex_intricate_networks/fundraising-and-startup-funding-scraper",
        "enrichment": "harvestapi/linkedin-profile-search-by-name",
    }
    cat_status: dict[str, dict] = {}
    all_ok = True
    for cat, actor_id in categories.items():
        try:
            info = apify.actor(actor_id).get()
            cat_status[cat] = {
                "ok": bool(info),
                "actor": actor_id,
                "name": (info or {}).get("name") or "",
            }
            if not info:
                all_ok = False
        except Exception as e:  # noqa: BLE001
            all_ok = False
            cat_status[cat] = {
                "ok": False,
                "actor": actor_id,
                "error": f"{type(e).__name__}: {e}",
            }

    return {
        "ok": all_ok,
        "username": username,
        "categories": cat_status,
        "spend_estimate_usd": get_apify_spend_usd(),
        "spend_cap_usd": _apify_default_cap(),
    }
