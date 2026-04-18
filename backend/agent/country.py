"""
Country -> language / platforms / cultural-context map.

Drives every country-aware behavior: which Apify scrapers to point where,
what language Llama-3.3 should reply in, and what cultural notes the LLM
should respect.
"""

COUNTRY_CONFIG: dict[str, dict] = {
    "South Korea": {
        "language": "ko",
        "language_name": "Korean",
        "search_locale": "ko",
        "search_country": "kr",
        "social": ["linkedin", "reddit", "naver", "blind"],
        "people_sites": [
            "blind.com",
            "cafe.naver.com",
            "kin.naver.com",
            "blog.naver.com",
            "okky.kr",
            "reddit.com/r/korea",
            "reddit.com/r/seoul",
            "reddit.com/r/Living_in_Korea",
        ],
        "opportunity_queries": [
            'hackathon Korea {industry} 2026',
            'Seoul {industry} startup conference 2026',
            '"call for speakers" Korea {industry}',
            'Korea {industry} press contact email site:techm.kr OR site:bloter.net OR site:venturesquare.net',
            'Korea {industry} accelerator program 2026',
            '한국 {industry} 벤처캐피털 VC 투자 프로그램 2026',
            'Korea {industry} VC fund startup investment 2026',
            'Korea tech press journalist email {industry}',
        ],
        "signals": {
            "funding": [
                "oxygenated_quagmire/naver-news-scraper",
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
        "search_locale": "ja",
        "search_country": "jp",
        "social": ["linkedin", "reddit", "x"],
        "people_sites": [
            "qiita.com",
            "zenn.dev",
            "note.com",
            "reddit.com/r/japanlife",
            "reddit.com/r/Tokyo",
        ],
        "opportunity_queries": [
            'ハッカソン {industry} 2026',
            'Japan {industry} startup conference 2026',
            'Tokyo {industry} meetup 2026',
            'Japan {industry} tech press contact email site:techcrunch.jp OR site:thebridge.jp',
            'Japan {industry} accelerator program 2026',
            'Japan {industry} VC fund startup investment 2026',
        ],
        "cultural_context": (
            "Extreme formality. Use です/ます form. Build trust via humility. "
            "Avoid hard asks. Apologize for sudden contact (突然のご連絡失礼いたします)."
        ),
    },
    "India": {
        "language": "en",
        "language_name": "English",
        "search_locale": "en",
        "search_country": "in",
        "social": ["linkedin", "reddit", "youtube", "quora", "tiktok"],
        "people_sites": [
            "quora.com",
            "reddit.com/r/india",
            "reddit.com/r/indianstartups",
            "reddit.com/r/developersIndia",
            "reddit.com/r/bangalore",
            "tiktok.com",
        ],
        "opportunity_queries": [
            'hackathon India {industry} 2026',
            'Bangalore {industry} startup conference 2026',
            '"call for speakers" India {industry}',
            'India {industry} tech press contact email site:inc42.com OR site:yourstory.com',
            'India {industry} accelerator program 2026',
            'India {industry} VC fund startup investment 2026',
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
        "search_locale": "zh-CN",
        "search_country": "cn",
        "social": ["weibo", "zhihu", "xiaohongshu"],
        "people_sites": [
            "zhihu.com",
            "weibo.com",
            "xiaohongshu.com",
            "douyin.com",
            "v2ex.com",
            "juejin.cn",
        ],
        "opportunity_queries": [
            '黑客松 {industry} 2026',
            'China {industry} startup conference 2026',
            'Shanghai {industry} meetup',
            'China {industry} accelerator 2026',
            'China {industry} VC fund startup investment 2026',
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
        "search_locale": "de",
        "search_country": "de",
        "social": ["linkedin", "reddit", "xing"],
        "people_sites": [
            "reddit.com/r/de",
            "reddit.com/r/berlin",
            "reddit.com/r/germany",
            "xing.com",
        ],
        "opportunity_queries": [
            'Hackathon Deutschland {industry} 2026',
            'Berlin {industry} Konferenz 2026',
            'Germany {industry} tech press contact email site:gruenderszene.de OR site:deutsche-startups.de',
            'Germany {industry} Accelerator 2026',
            'Germany {industry} VC Fonds Startup Investition 2026',
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
        "search_locale": "en",
        "search_country": "sg",
        "social": ["linkedin", "reddit", "youtube"],
        "people_sites": [
            "reddit.com/r/singapore",
            "reddit.com/r/singaporefi",
            "hardwarezone.com.sg",
        ],
        "opportunity_queries": [
            'hackathon Singapore {industry} 2026',
            'Singapore {industry} startup conference 2026',
            '"call for speakers" Singapore {industry}',
            'Singapore {industry} tech press contact email site:techinasia.com OR site:e27.co',
            'Singapore {industry} accelerator program 2026',
            'Singapore {industry} VC fund startup investment 2026',
        ],
        "cultural_context": (
            "Professional, polished, multicultural. English standard. "
            "Concise and outcome-oriented. Mutual connections accelerate trust."
        ),
    },
    "United States": {
        "language": "en",
        "language_name": "English",
        "search_locale": "en",
        "search_country": "us",
        "social": ["linkedin", "reddit", "youtube", "tiktok"],
        "people_sites": [
            "reddit.com/r/startups",
            "reddit.com/r/SaaS",
            "reddit.com/r/Entrepreneur",
            "news.ycombinator.com",
            "indiehackers.com",
            "tiktok.com",
        ],
        "opportunity_queries": [
            'hackathon USA {industry} 2026',
            '{industry} startup conference USA 2026',
            '"call for speakers" {industry} USA',
            '{industry} tech press contact email site:techcrunch.com OR site:venturebeat.com',
            '{industry} accelerator program USA 2026',
            '{industry} VC fund startup investment USA 2026',
        ],
        "cultural_context": (
            "Direct, ROI-first. Casual but professional. Lead with numbers and outcomes. "
            "First message: zero pitch — pure value or curiosity."
        ),
    },
    "Brazil": {
        "language": "pt",
        "language_name": "Brazilian Portuguese",
        "search_locale": "pt-BR",
        "search_country": "br",
        "social": ["linkedin", "reddit", "youtube", "tiktok"],
        "people_sites": [
            "reddit.com/r/brasil",
            "reddit.com/r/brdev",
            "tabnews.com.br",
            "tiktok.com",
        ],
        "opportunity_queries": [
            'hackathon Brasil {industry} 2026',
            'São Paulo {industry} conferência 2026',
            'Brazil {industry} accelerator 2026',
            'Brazil {industry} VC fund startup investimento 2026',
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
        "social": ["linkedin", "reddit", "youtube"],
        "people_sites": ["reddit.com/r/startups", "reddit.com/r/SaaS"],
        "opportunity_queries": [
            "hackathon {country} {industry} 2026",
            "{country} {industry} conference 2026",
            "{country} {industry} accelerator 2026",
            "{country} {industry} tech press contact email",
            "{country} {industry} VC fund startup investment 2026",
        ],
        "cultural_context": "Be professional, respectful, and lead with empathy.",
    }


def list_countries() -> list[str]:
    return list(COUNTRY_CONFIG.keys())
