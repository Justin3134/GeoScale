"""
Buying-intent signal feed.

A "signal" is a company-level event that strongly implies budget + urgency to
buy. We surface three kinds:

  • Funding signals  — recent raise → fresh budget, pressure to deploy
  • Hiring signals   — open req for {role} → need a tool for that role TODAY
  • Engagement       — people who liked / commented on a competitor's post

Each public function returns a normalized list of CompanySignal-shaped dicts:

    {
      "company_name":  str,
      "signal_type":   "funding" | "hiring" | "engagement",
      "signal_text":   str,        # one-line natural-language description
      "signal_url":    str,        # source URL for citation in DM
      "suggested_role": str,       # who at the company we should DM
      "raw":           dict,       # original Apify item, for debugging
    }

Cost notes (hackathon budget):
  Funding actors are cheap (~$0.01/result).
  Hiring actors are cheaper (~$0.001/job).
  Competitor engagement is $0.002/reaction or $0.002/comment.
  Always pass a tight `max_results` cap.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote_plus

from agent.country import get_country_config
from agent.tools import _apify_run

# ─── Helpers ──────────────────────────────────────────────────────────────


def _safe(d: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = d.get(k)
        if v:
            return str(v)
    return default


def _signal(
    company_name: str,
    signal_type: str,
    signal_text: str,
    signal_url: str,
    suggested_role: str,
    raw: dict,
) -> dict:
    return {
        "company_name": (company_name or "").strip()[:160],
        "signal_type": signal_type,
        "signal_text": (signal_text or "").strip()[:400],
        "signal_url": signal_url or "",
        "suggested_role": (suggested_role or "Founder").strip()[:80],
        "raw": raw,
    }


# ─── Funding signals ──────────────────────────────────────────────────────


def _funding_from_india_et(item: dict) -> dict | None:
    """Normalize one Economic Times capital-tracker row."""
    company = _safe(item, "company", "companyName", "startup", "entity")
    if not company:
        return None
    amount = _safe(item, "amount", "fundingAmount", "raised", "value")
    stage = _safe(item, "round", "stage", "fundingStage", default="funding round")
    investors = _safe(item, "leadInvestor", "investors", "investor")
    text = f"{company} raised {amount} {stage}".strip()
    if investors:
        text += f" (lead: {investors})"
    return _signal(
        company_name=company,
        signal_type="funding",
        signal_text=text,
        signal_url=_safe(item, "url", "articleUrl", "link", "source"),
        suggested_role="Founder",
        raw=item,
    )


def _funding_from_universal(item: dict) -> dict | None:
    company = _safe(item, "company", "companyName", "startup")
    if not company:
        return None
    amount = _safe(item, "amount", "fundingAmount", "raised")
    round_ = _safe(item, "round", "fundingRound", "stage", default="funding round")
    headline = _safe(item, "headline", "title")
    text = f"{company} raised {amount} {round_}".strip()
    if headline and headline.lower() != text.lower():
        text = f"{text} — {headline}"
    return _signal(
        company_name=company,
        signal_type="funding",
        signal_text=text,
        signal_url=_safe(item, "url", "articleUrl", "link"),
        suggested_role="Founder",
        raw=item,
    )


def _funding_from_naver_news(item: dict, query: str) -> dict | None:
    """Naver News articles — extract company by hoping the title leads with it."""
    title = _safe(item, "title", "headline")
    if not title:
        return None
    blob = (title + " " + _safe(item, "description", "body", "summary")).lower()
    if not any(w in blob for w in ("투자", "유치", "시리즈", "raise", "series", "funding")):
        return None
    # The first 1-2 tokens of a Naver funding headline are usually the company.
    company = title.split(",")[0].split("는")[0].split("이")[0].strip().split(" ")[0:2]
    company_name = " ".join(company)[:120] or "Korean startup"
    return _signal(
        company_name=company_name,
        signal_type="funding",
        signal_text=title[:400],
        signal_url=_safe(item, "url", "originalLink", "link"),
        suggested_role="대표 (CEO)",
        raw=item,
    )


def _funding_from_dart(item: dict) -> dict | None:
    """South Korea DART filings — surface only equity-capital-related types."""
    name = _safe(item, "report_nm", "reportName", "title", "report")
    company = _safe(item, "corp_name", "corpName", "company", "corporationName")
    if not company:
        return None
    if not any(
        w in name for w in ("증자", "유상", "발행", "신주", "투자", "Capital", "Issue")
    ):
        return None
    receipt = _safe(item, "rcept_dt", "receiptDate", "date")
    text = f"{company} filed: {name} ({receipt})".strip()
    receipt_no = _safe(item, "rcept_no", "receiptNo")
    url = (
        _safe(item, "url", "filingUrl")
        or (
            f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}"
            if receipt_no
            else ""
        )
    )
    return _signal(
        company_name=company,
        signal_type="funding",
        signal_text=text,
        signal_url=url,
        suggested_role="대표 (CEO)",
        raw=item,
    )


def scrape_funding_signals(
    country: str,
    industry: str | None = None,
    max_per_actor: int = 25,
    campaign_id: str | None = None,
) -> list[dict]:
    """Run the country's configured funding-signal actors and normalize."""
    cfg = get_country_config(country)
    actor_ids: list[str] = (cfg.get("signals") or {}).get("funding", [])
    if not actor_ids:
        return []

    out: list[dict] = []
    for actor_id in actor_ids:
        if actor_id == "complex_intricate_networks/india-startup-vc-intelligence-economic-times-capital-tracker":
            items = _apify_run(
                actor_id,
                {
                    "scrapeDuration": "1 week",
                    "forceRefresh": False,
                    "maxRequestsPerCrawl": max_per_actor * 2,
                },
                campaign_id=campaign_id,
                stream="signals",
                max_items=max_per_actor,
                timeout_secs=240,
            )
            for it in items:
                norm = _funding_from_india_et(it)
                if norm:
                    out.append(norm)

        elif actor_id == "complex_intricate_networks/fundraising-and-startup-funding-scraper":
            items = _apify_run(
                actor_id,
                {"dateFilter": "7", "maxRequestsPerCrawl": max_per_actor * 2},
                campaign_id=campaign_id,
                stream="signals",
                max_items=max_per_actor,
                timeout_secs=240,
            )
            for it in items:
                norm = _funding_from_universal(it)
                if norm:
                    out.append(norm)

        elif actor_id == "oxygenated_quagmire/naver-news-scraper":
            keyword = (industry or "스타트업") + " 투자 유치"
            items = _apify_run(
                actor_id,
                {
                    "mode": "search",
                    "keyword": keyword,
                    "sort": "newest",
                    "period": "1w",
                    "maxResults": max_per_actor * 2,
                },
                campaign_id=campaign_id,
                stream="signals",
                max_items=max_per_actor * 2,
                timeout_secs=180,
            )
            for it in items:
                norm = _funding_from_naver_news(it, keyword)
                if norm:
                    out.append(norm)

        elif actor_id == "fortuitous_pirate/south-korea-dart-scraper":
            opendart_key = os.getenv("OPENDART_API_KEY")
            if not opendart_key:
                # Surface a one-line note so the demo doesn't silently miss DART.
                continue
            items = _apify_run(
                actor_id,
                {
                    "apiKey": opendart_key,
                    "disclosureType": "F",  # Securities (issues, raises)
                    "maxItems": max_per_actor,
                    "includeFinancials": False,
                },
                campaign_id=campaign_id,
                stream="signals",
                max_items=max_per_actor,
                timeout_secs=180,
            )
            for it in items:
                norm = _funding_from_dart(it)
                if norm:
                    out.append(norm)
        # Unknown actor id → skip silently; the per-country config can register
        # new ones without code changes once a normalizer exists.

    return out


# ─── Hiring signals ───────────────────────────────────────────────────────


_LINKEDIN_GEO_BY_CC = {
    # rough city-level GEO IDs that LinkedIn uses for the public jobs page
    "in": "102713980",  # India
    "kr": "105149562",  # South Korea
    "cn": "102890883",  # China
    "us": "103644278",
    "sg": "102454443",
    "de": "101282230",
    "jp": "101355337",
    "br": "106057199",
}


def _build_linkedin_jobs_url(role_keyword: str, country_code: str) -> str:
    geo = _LINKEDIN_GEO_BY_CC.get((country_code or "us").lower(), "103644278")
    return (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={quote_plus(role_keyword)}&geoId={geo}&f_TPR=r604800"  # past week
    )


def _hiring_from_linkedin(item: dict, role_keyword: str) -> dict | None:
    company_block = item.get("companyDetails") or item.get("company") or {}
    if isinstance(company_block, dict):
        company = _safe(
            company_block, "name", "companyName", "title",
            default=_safe(item, "companyName", "companyTitle"),
        )
    else:
        company = str(company_block) or _safe(item, "companyName", "companyTitle")
    if not company:
        return None
    title = _safe(item, "title", "jobTitle", "position")
    location = _safe(item, "location", "locationName", "place")
    text = f"{company} is hiring: {title} ({location})".strip(" :()")
    return _signal(
        company_name=company,
        signal_type="hiring",
        signal_text=text,
        signal_url=_safe(item, "link", "jobUrl", "url"),
        suggested_role=_role_above(title) or _role_above(role_keyword) or "Founder",
        raw=item,
    )


def _hiring_from_naukri(item: dict, role_keyword: str) -> dict | None:
    company = _safe(item, "companyName", "company", "employerName")
    if not company:
        return None
    title = _safe(item, "title", "jobTitle", "designation")
    location = _safe(item, "location", "city", "jobLocation")
    text = f"{company} is hiring: {title} ({location})".strip(" :()")
    return _signal(
        company_name=company,
        signal_type="hiring",
        signal_text=text,
        signal_url=_safe(item, "url", "jobUrl", "applyUrl", "link"),
        suggested_role=_role_above(title) or _role_above(role_keyword) or "Head of HR",
        raw=item,
    )


def _hiring_from_apna(item: dict, role_keyword: str) -> dict | None:
    company = _safe(item, "company", "companyName", "employer")
    if not company:
        return None
    title = _safe(item, "title", "jobTitle")
    location = _safe(item, "city", "location")
    text = f"{company} is hiring: {title} ({location})".strip(" :()")
    return _signal(
        company_name=company,
        signal_type="hiring",
        signal_text=text,
        signal_url=_safe(item, "url", "detailUrl", "applyUrl"),
        suggested_role=_role_above(title) or "Head of People",
        raw=item,
    )


def _role_above(role: str) -> str:
    """Heuristic: who likely owns the budget for a candidate of this role.

    e.g. job posting for "HR Manager" → DM the "Head of HR" or "VP People".
    """
    if not role:
        return ""
    r = role.lower()
    if any(w in r for w in ("hr", "people", "talent", "recruit")):
        return "Head of People"
    if any(w in r for w in ("sales", "account exec", "bd ")):
        return "VP Sales"
    if any(w in r for w in ("market", "growth", "demand")):
        return "Head of Marketing"
    if any(w in r for w in ("data", "analyst", "ml", "ai")):
        return "Head of Data"
    if any(w in r for w in ("engineer", "developer", "swe", "backend", "frontend", "devops")):
        return "VP Engineering"
    if any(w in r for w in ("design", "product")):
        return "Head of Product"
    if any(w in r for w in ("finance", "account")):
        return "CFO"
    return "Founder"


def scrape_hiring_signals(
    country: str,
    role_keywords: list[str],
    icp_description: str | None = None,
    max_per_query: int = 15,
    campaign_id: str | None = None,
) -> list[dict]:
    """Run the country's configured hiring actors for each role keyword.

    `role_keywords` are pulled from the campaign's pain keywords / ICP — e.g.
    if the product is an HR tool, the keywords might be ["hr manager",
    "people ops", "head of talent"].
    """
    cfg = get_country_config(country)
    actor_ids: list[str] = (cfg.get("signals") or {}).get("hiring", [])
    if not actor_ids or not role_keywords:
        return []

    cc = (cfg.get("search_country") or "us").lower()
    out: list[dict] = []

    for actor_id in actor_ids:
        for role_kw in role_keywords[:3]:  # cap roles per cycle
            if actor_id == "memo23/naukri-scraper":
                items = _apify_run(
                    actor_id,
                    {
                        "platform": "naukri",
                        "searchQuery": role_kw,
                        "location": "india",
                        "maximumJobs": max_per_query,
                    },
                    campaign_id=campaign_id,
                    stream="signals",
                    max_items=max_per_query,
                    timeout_secs=240,
                )
                for it in items:
                    norm = _hiring_from_naukri(it, role_kw)
                    if norm:
                        out.append(norm)

            elif actor_id == "logiover/apna-co-jobs-scraper":
                slug = role_kw.replace(" ", "_").lower()
                items = _apify_run(
                    actor_id,
                    {
                        "keywords": [slug],
                        "maxJobs": max_per_query,
                        "maxPages": 2,
                    },
                    campaign_id=campaign_id,
                    stream="signals",
                    max_items=max_per_query,
                    timeout_secs=180,
                )
                for it in items:
                    norm = _hiring_from_apna(it, role_kw)
                    if norm:
                        out.append(norm)

            elif actor_id == "curious_coder/linkedin-jobs-scraper":
                items = _apify_run(
                    actor_id,
                    {
                        "urls": [_build_linkedin_jobs_url(role_kw, cc)],
                        "scrapeCompany": False,
                        "count": max_per_query,
                    },
                    campaign_id=campaign_id,
                    stream="signals",
                    max_items=max_per_query,
                    timeout_secs=240,
                )
                for it in items:
                    norm = _hiring_from_linkedin(it, role_kw)
                    if norm:
                        out.append(norm)

    return out


# ─── Competitor engagement mining ─────────────────────────────────────────


def _engagement_from_reaction(item: dict, source_url: str) -> dict | None:
    reactor = item.get("profile") or item.get("reactor") or item.get("user") or {}
    if isinstance(reactor, str):
        name = reactor
        position = ""
        company = ""
        url = ""
    else:
        name = _safe(
            reactor, "fullName", "name", "displayName",
            default=f"{_safe(reactor, 'firstName')} {_safe(reactor, 'lastName')}".strip(),
        )
        position = _safe(reactor, "position", "headline", "title")
        company = _safe(reactor, "company", "companyName")
        url = _safe(reactor, "profileUrl", "publicProfileUrl", "url")
    if not name and not url:
        return None
    react_type = _safe(item, "reactionType", "type", default="reacted")
    return _signal(
        company_name=company or name or "Engaged user",
        signal_type="engagement",
        signal_text=f"{name} {react_type.lower()} a competitor post — {position}".strip(" —"),
        signal_url=url or source_url,
        suggested_role=position or "Decision maker",
        raw={**item, "linkedin_url": url, "name": name},
    )


def _engagement_from_comment(item: dict, source_url: str) -> dict | None:
    commenter = item.get("commenter") or item.get("author") or item.get("profile") or {}
    if isinstance(commenter, str):
        name = commenter
        position = ""
        company = ""
        url = ""
    else:
        name = _safe(
            commenter, "fullName", "name",
            default=f"{_safe(commenter, 'firstName')} {_safe(commenter, 'lastName')}".strip(),
        )
        position = _safe(commenter, "position", "headline")
        company = _safe(commenter, "company", "companyName")
        url = _safe(commenter, "profileUrl", "publicProfileUrl", "url")
    if not name and not url:
        return None
    text = _safe(item, "text", "comment", "body")[:200]
    return _signal(
        company_name=company or name,
        signal_type="engagement",
        signal_text=f"{name} commented on competitor post: \"{text}\"".strip(),
        signal_url=url or source_url,
        suggested_role=position or "Decision maker",
        raw={**item, "linkedin_url": url, "name": name, "comment_text": text},
    )


def scrape_competitor_engagement(
    competitor_linkedin_profile_urls: list[str],
    max_per_profile: int = 15,
    campaign_id: str | None = None,
) -> list[dict]:
    """For each competitor profile, pull the people who liked / commented on
    their recent posts. These are warm leads — they self-identified interest
    in the topic our product solves."""
    if not competitor_linkedin_profile_urls:
        return []

    out: list[dict] = []

    reactions = _apify_run(
        "harvestapi/linkedin-profile-reactions",
        {
            "profiles": competitor_linkedin_profile_urls[:5],
            "maxItems": max_per_profile,
            "postedLimit": "month",
        },
        campaign_id=campaign_id,
        stream="signals",
        max_items=max_per_profile * len(competitor_linkedin_profile_urls[:5]),
        timeout_secs=240,
    )
    for it in reactions:
        norm = _engagement_from_reaction(
            it, source_url=competitor_linkedin_profile_urls[0]
        )
        if norm:
            out.append(norm)

    comments = _apify_run(
        "harvestapi/linkedin-profile-comments",
        {
            "profiles": competitor_linkedin_profile_urls[:5],
            "maxItems": max_per_profile,
            "postedLimit": "month",
        },
        campaign_id=campaign_id,
        stream="signals",
        max_items=max_per_profile * len(competitor_linkedin_profile_urls[:5]),
        timeout_secs=240,
    )
    for it in comments:
        norm = _engagement_from_comment(
            it, source_url=competitor_linkedin_profile_urls[0]
        )
        if norm:
            out.append(norm)

    return out


__all__ = [
    "scrape_funding_signals",
    "scrape_hiring_signals",
    "scrape_competitor_engagement",
]
