"""
Country -> language / platforms / cultural-context map.

Drives every country-aware behavior: which Apify scrapers to point where,
what language Llama-3.3 should reply in, and what cultural notes the LLM
should respect.

Active platforms: LinkedIn, Reddit, Instagram, YouTube, Gmail/Google.
Naver and TikTok have been removed.
"""

COUNTRY_CONFIG: dict[str, dict] = {
    "South Korea": {
        "language": "ko",
        "language_name": "Korean",
        "local_name": "한국",
        "search_locale": "ko",
        "search_country": "kr",
        "youtube_gl": "KR",
        "youtube_hl": "ko",
        "social": ["linkedin", "reddit", "youtube", "instagram"],
        "people_sites": [
            # Korean-native platforms — scraped via Google site: with Korean keywords
            "cafe.naver.com",        # Naver Café — largest Korean community forum
            "blog.naver.com",        # Naver Blog — Korea's biggest blogging platform
            "blind.com",             # Blind — anonymous Korean tech/startup pro network
            "okky.kr",               # Korean developer community Q&A
            "disquiet.io",           # Korean indie hacker / startup community
            # Reddit Korea subs (English-language, expats & Korean bilingual users)
            "reddit.com/r/korea",
            "reddit.com/r/seoul",
        ],
        "signals": {
            "funding": [
                "fortuitous_pirate/south-korea-dart-scraper",
            ],
            "hiring": ["curious_coder/linkedin-jobs-scraper"],
        },
        "cultural_context": (
            "Hierarchy matters. Use formal titles (직함). Relationship before business. "
            "Indirect communication. Never pitch product first. Reference the post they wrote. "
            "Use 존댓말 (formal speech endings -습니다/-입니다). Apologize for the cold reach-out."
        ),
    },
    "Japan": {
        "language": "ja",
        "language_name": "Japanese",
        "local_name": "日本",
        "search_locale": "ja",
        "search_country": "jp",
        "youtube_gl": "JP",
        "youtube_hl": "ja",
        "social": ["linkedin", "reddit", "youtube", "instagram"],
        "people_sites": [
            "reddit.com/r/japanlife",
            "reddit.com/r/Tokyo",
        ],
        "cultural_context": (
            "Extreme formality. Use です/ます form. Build trust via humility. "
            "Avoid hard asks. Apologize for sudden contact (突然のご連絡失礼いたします)."
        ),
    },
    "India": {
        "language": "en",
        "language_name": "English",
        "local_name": "India",
        "search_locale": "en",
        "search_country": "in",
        "youtube_gl": "IN",
        "youtube_hl": "en",
        "social": ["linkedin", "reddit", "youtube", "instagram"],
        "people_sites": [
            "reddit.com/r/india",
            "reddit.com/r/indianstartups",
            "reddit.com/r/developersIndia",
            "reddit.com/r/bangalore",
        ],
        "signals": {
            "funding": [
                "complex_intricate_networks/india-startup-vc-intelligence-economic-times-capital-tracker",
            ],
            "hiring": [
                "memo23/naukri-scraper",
                "logiover/apna-co-jobs-scraper",
            ],
        },
        "cultural_context": (
            "Warm, relationship-first tone. Reference credibility signals (funding, "
            "known customers). Persistence is respected. Formal but friendly."
        ),
    },
    "China": {
        "language": "zh",
        "language_name": "Simplified Chinese",
        "local_name": "中国",
        "search_locale": "zh-CN",
        "search_country": "cn",
        "youtube_gl": "CN",
        "youtube_hl": "zh-CN",
        "social": ["linkedin", "instagram", "youtube"],
        "people_sites": [
            "zhihu.com",
            "weibo.com",
            "v2ex.com",
            "juejin.cn",
        ],
        "signals": {
            "funding": [
                "complex_intricate_networks/fundraising-and-startup-funding-scraper",
            ],
            "hiring": ["curious_coder/linkedin-jobs-scraper"],
        },
        "cultural_context": (
            "Use simplified Chinese. Indirect, relationship-based. Reference "
            "credibility (clients, funding). Avoid sensitive political topics."
        ),
    },
    "Germany": {
        "language": "de",
        "language_name": "German",
        "local_name": "Deutschland",
        "search_locale": "de",
        "search_country": "de",
        "youtube_gl": "DE",
        "youtube_hl": "de",
        "social": ["linkedin", "reddit", "youtube", "instagram"],
        "people_sites": [
            "reddit.com/r/de",
            "reddit.com/r/berlin",
            "reddit.com/r/germany",
        ],
        "cultural_context": (
            "Direct, fact-based, no fluff. Privacy-conscious — be transparent about why "
            "you reached out and how you found them. References and credentials matter. "
            "Use Sie form by default."
        ),
    },
    "Singapore": {
        "language": "en",
        "language_name": "English",
        "local_name": "Singapore",
        "search_locale": "en",
        "search_country": "sg",
        "youtube_gl": "SG",
        "youtube_hl": "en",
        "social": ["linkedin", "reddit", "youtube", "instagram"],
        "people_sites": [
            "reddit.com/r/singapore",
            "reddit.com/r/singaporefi",
        ],
        "cultural_context": (
            "Professional, polished, multicultural. English standard. "
            "Concise and outcome-oriented. Mutual connections accelerate trust."
        ),
    },
    "United States": {
        "language": "en",
        "language_name": "English",
        "local_name": "USA",
        "search_locale": "en",
        "search_country": "us",
        "youtube_gl": "US",
        "youtube_hl": "en",
        "social": ["linkedin", "reddit", "youtube", "instagram"],
        "people_sites": [
            "reddit.com/r/startups",
            "reddit.com/r/SaaS",
            "reddit.com/r/Entrepreneur",
        ],
        "cultural_context": (
            "Direct, ROI-first. Casual but professional. Lead with numbers and outcomes. "
            "First message: zero pitch — pure value or curiosity."
        ),
    },
    "Brazil": {
        "language": "pt",
        "language_name": "Brazilian Portuguese",
        "local_name": "Brasil",
        "search_locale": "pt-BR",
        "search_country": "br",
        "youtube_gl": "BR",
        "youtube_hl": "pt",
        "social": ["linkedin", "reddit", "youtube", "instagram"],
        "people_sites": [
            "reddit.com/r/brasil",
            "reddit.com/r/brdev",
        ],
        "cultural_context": (
            "Warm, personal tone. Use tu/você naturally. Brazilians appreciate humor "
            "and personality, but stay professional in first contact."
        ),
    },
}


def get_country_config(country: str) -> dict:
    """Return config for the country, falling back to a sensible English default."""
    if country in COUNTRY_CONFIG:
        return COUNTRY_CONFIG[country]
    return {
        "language": "en",
        "language_name": "English",
        "search_locale": "en",
        "search_country": "us",
        "social": ["linkedin", "reddit", "youtube", "instagram"],
        "people_sites": [
            "reddit.com/r/startups",
            "reddit.com/r/SaaS",
        ],
        "cultural_context": "Be professional, respectful, and lead with empathy.",
    }


def list_countries() -> list[str]:
    return list(COUNTRY_CONFIG.keys())
