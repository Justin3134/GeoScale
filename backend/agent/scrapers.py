"""
Per-platform Apify Actor registry.

Replaces the Google `site:` shim (`tools.scrape_native_social`) with dedicated
Actors when one exists for a platform. Returns the same lead-shaped dict as
`scrape_native_social` so [streams/people.py](backend/agent/streams/people.py)
doesn't need to know which path was taken.

Lead dict shape (must match `tools.scrape_native_social`):
    {
      "platform":            str,
      "name":                str,
      "title":               str,
      "company":             str,
      "linkedin_url":        str,
      "source_post_url":     str,
      "source_comment_text": str,
    }

Adding a new platform: drop a new entry into PLATFORM_SCRAPERS with three things:
    - actor: Apify actor id ("user/name")
    - build_input: callable(keyword: str, max_results: int) -> dict
    - normalize:   callable(item: dict, site: str) -> dict (lead shape)

Unknown platforms fall through to `tools.scrape_native_social` (Google site:).
"""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import quote_plus

from agent.tools import _apify_run, _platform_from_site, scrape_native_social


# ─── Per-actor input builders ──────────────────────────────────────────────


def _blind_input(keyword: str, max_results: int, country_code: str = "kr") -> dict:
    """TeamBlind doesn't have keyword search via the actor's schema, so we
    feed it the public search URL plus the popular feed as a fallback.
    The actor follows /search/* and /?sort=pop list pages."""
    keyword_q = quote_plus(keyword)
    return {
        "startUrls": [
            {"url": f"https://www.teamblind.com/search/Post?query={keyword_q}"},
            {"url": "https://www.teamblind.com/?sort=pop"},
        ],
        "maxItems": max_results,
        "scrapePostsFromLists": True,
        "scrapeComments": False,
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
            "apifyProxyCountry": country_code.upper(),
        },
    }


def _naver_cafe_input(keyword: str, max_results: int, country_code: str = "kr") -> dict:
    """The actor crawls Naver search → cafe posts. Feed it the Naver search
    URL for cafe articles (`where=articleg`)."""
    keyword_q = quote_plus(keyword)
    return {
        "startUrls": [
            {
                "url": (
                    f"https://search.naver.com/search.naver?where=articleg&query={keyword_q}"
                )
            }
        ],
        "maxItems": max_results,
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
            "apifyProxyCountry": country_code.upper(),
        },
    }


def _naver_blog_cafe_input(keyword: str, max_results: int, country_code: str = "kr") -> dict:
    """huggable_quote/naver-blog-cafe-scraper — keyword + URL search."""
    return {
        "keyword": keyword,
        "maxItems": max_results,
        "includeBlog": True,
        "includeCafe": True,
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
            "apifyProxyCountry": country_code.upper(),
        },
    }


def _naver_kin_input(keyword: str, max_results: int, country_code: str = "kr") -> dict:
    return {
        "query": keyword,
        "maxResults": max_results,
        "sort": "newest",
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
            "apifyProxyCountry": country_code.upper(),
        },
    }


def _weibo_input(keyword: str, max_results: int, country_code: str = "cn") -> dict:
    """Weibo actor only takes `limit` — no keyword filter. We pull the main
    feed and filter post-hoc in `_weibo_norm` to keep posts containing
    the keyword."""
    return {
        "limit": max_results * 4,
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
            "apifyProxyCountry": country_code.upper(),
        },
    }


def _xiaohongshu_input(keyword: str, max_results: int, country_code: str = "cn") -> dict:
    return {
        "keywords": [keyword],
        "sortType": "general",
        "noteType": "all",
        "maxItems": max_results,
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
            "apifyProxyCountry": country_code.upper(),
        },
    }


def _douyin_comments_input(keyword: str, max_results: int, country_code: str = "cn") -> dict:
    """Douyin comments scraper takes a video URL not a keyword. We can't
    derive a video URL from a pain keyword cleanly, so this entry stays
    here for future expansion. For now we fall back to Google site:."""
    raise NotImplementedError("douyin requires a video URL — fallback to SERP")


# ─── Per-actor output normalizers ─────────────────────────────────────────


def _safe(d: dict, *keys: str, default: str = "") -> str:
    """Pick the first key that has a non-empty value."""
    for k in keys:
        v = d.get(k)
        if v:
            return str(v)
    return default


def _blind_norm(item: dict, site: str) -> dict:
    author = item.get("author") or item.get("user") or {}
    if isinstance(author, str):
        author_name = author
        company = ""
    else:
        author_name = _safe(author, "name", "username", "displayName", default="blind user")
        company = _safe(author, "company", "companyName", default=item.get("company", ""))
    return {
        "platform": "blind",
        "name": author_name[:120] or "blind user",
        "title": _safe(item, "title", "subject")[:160],
        "company": (company or "")[:120],
        "linkedin_url": "",
        "source_post_url": _safe(item, "url", "postUrl", "link"),
        "source_comment_text": _safe(item, "content", "body", "text", "title")[:600],
    }


def _naver_cafe_norm(item: dict, site: str) -> dict:
    return {
        "platform": "naver_cafe",
        "name": _safe(item, "author", "writer", "nickname", default="naver user")[:120],
        "title": _safe(item, "title", "subject")[:160],
        "company": "",
        "linkedin_url": "",
        "source_post_url": _safe(item, "url", "link", "postUrl"),
        "source_comment_text": _safe(item, "content", "body", "text", "description", "title")[:600],
    }


def _naver_blog_cafe_norm(item: dict, site: str) -> dict:
    src = _safe(item, "type", "source", default="naver")
    platform = "naver_cafe" if "cafe" in src.lower() else "naver_blog"
    return {
        "platform": platform,
        "name": _safe(item, "author", "writer", "blogger", "nickname", default="naver user")[:120],
        "title": _safe(item, "title")[:160],
        "company": "",
        "linkedin_url": "",
        "source_post_url": _safe(item, "url", "link"),
        "source_comment_text": _safe(item, "content", "body", "text", "summary", "title")[:600],
    }


def _naver_kin_norm(item: dict, site: str) -> dict:
    return {
        "platform": "naver_kin",
        "name": _safe(item, "asker", "author", "writer", default="naver user")[:120],
        "title": _safe(item, "question", "title")[:160],
        "company": "",
        "linkedin_url": "",
        "source_post_url": _safe(item, "url", "link"),
        "source_comment_text": _safe(item, "answer", "questionContent", "content", "title")[:600],
    }


def _weibo_norm(item: dict, site: str) -> dict:
    user = item.get("user") or item.get("author") or {}
    if isinstance(user, str):
        user_name = user
    else:
        user_name = _safe(user, "screenName", "name", "nickname", default="weibo user")
    return {
        "platform": "weibo",
        "name": (user_name or "weibo user")[:120],
        "title": _safe(item, "title")[:160],
        "company": "",
        "linkedin_url": "",
        "source_post_url": _safe(item, "url", "link", "postUrl", "weiboUrl"),
        "source_comment_text": _safe(item, "text", "content", "rawText")[:600],
    }


def _weibo_filter(items: list[dict], keyword: str) -> list[dict]:
    """Weibo actor returns the global feed — filter to posts mentioning
    the keyword (case-insensitive substring on the text body)."""
    if not keyword:
        return items
    needle = keyword.lower()
    out = []
    for it in items:
        blob = " ".join(
            str(it.get(k, "")) for k in ("text", "content", "rawText", "title")
        ).lower()
        if needle in blob:
            out.append(it)
    return out or items[: max(1, len(items) // 4)]


def _xiaohongshu_norm(item: dict, site: str) -> dict:
    user = item.get("user") or item.get("author") or {}
    if isinstance(user, str):
        nickname = user
    else:
        nickname = _safe(user, "nickname", "name", "userName", default="rednote user")
    return {
        "platform": "xiaohongshu",
        "name": (nickname or "rednote user")[:120],
        "title": _safe(item, "title", "displayTitle")[:160],
        "company": "",
        "linkedin_url": "",
        "source_post_url": _safe(item, "url", "noteUrl", "link"),
        "source_comment_text": _safe(item, "desc", "content", "title", "displayTitle")[:600],
    }


# ─── Registry ─────────────────────────────────────────────────────────────


# build_input signature: (keyword: str, max_results: int, country_code: str) -> dict
PLATFORM_SCRAPERS: dict[str, dict[str, Any]] = {
    # blind.com / teamblind.com: hypebridge/blind-post-scraper costs $25/1k —
    # removed to avoid exhausting free-plan credits. Falls through to the
    # Google `site:` shim in scrape_native_social() instead.
    "cafe.naver.com": {
        "actor": "naver_crawling/naver-search-cafe-crawling",
        "build_input": _naver_cafe_input,
        "normalize": _naver_cafe_norm,
    },
    "blog.naver.com": {
        "actor": "huggable_quote/naver-blog-cafe-scraper",
        "build_input": _naver_blog_cafe_input,
        "normalize": _naver_blog_cafe_norm,
    },
    "kin.naver.com": {
        "actor": "oxygenated_quagmire/naver-kin-scraper",
        "build_input": _naver_kin_input,
        "normalize": _naver_kin_norm,
    },
    "weibo.com": {
        "actor": "piotrv1001/weibo-scraper",
        "build_input": _weibo_input,
        "normalize": _weibo_norm,
        "post_filter": _weibo_filter,
    },
    "xiaohongshu.com": {
        "actor": "easyapi/rednote-xiaohongshu-search-scraper",
        "build_input": _xiaohongshu_input,
        "normalize": _xiaohongshu_norm,
    },
}


# ─── Public entrypoint ────────────────────────────────────────────────────


def scrape_platform(
    site: str,
    keyword: str,
    country_code: str,
    locale: str,
    max_results: int = 10,
    campaign_id: str | None = None,
    timeout_secs: int = 180,
) -> list[dict]:
    """
    Scrape one platform for posts matching `keyword`.

    Uses a dedicated Apify actor when one is registered, otherwise falls back
    to the Google `site:` SERP shim already in `tools.scrape_native_social`.
    """
    cfg = PLATFORM_SCRAPERS.get(site.lower())
    if not cfg:
        return scrape_native_social(
            site, keyword, country_code, locale, max_results, campaign_id
        )

    actor: str = cfg["actor"]
    build_input: Callable[[str, int, str], dict] = cfg["build_input"]
    normalize: Callable[[dict, str], dict] = cfg["normalize"]
    post_filter: Callable[[list[dict], str], list[dict]] | None = cfg.get("post_filter")

    try:
        run_input = build_input(keyword, max_results, country_code)
    except NotImplementedError:
        # Actor exists but isn't keyword-addressable (e.g. Douyin needs a
        # video URL). Fall back to Google.
        return scrape_native_social(
            site, keyword, country_code, locale, max_results, campaign_id
        )

    items = _apify_run(
        actor,
        run_input,
        campaign_id=campaign_id,
        stream="people",
        max_items=max_results * 4,
        timeout_secs=timeout_secs,
    )

    if post_filter is not None:
        items = post_filter(items, keyword)

    out: list[dict] = []
    for it in items[:max_results]:
        try:
            out.append(normalize(it, site))
        except Exception:  # noqa: BLE001
            continue
    return out


__all__ = ["PLATFORM_SCRAPERS", "scrape_platform"]
