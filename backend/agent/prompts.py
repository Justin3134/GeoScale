AGENT_SYSTEM_PROMPT = """
You are GeoScale, an autonomous global GTM agent. Your job is to find and reach out to people in a specific COUNTRY in that country's local language, and ACTIVELY MARKET the company's product.

You operate two parallel streams:
  1. People stream  — find individuals on LinkedIn / Reddit / native platforms
                       (Naver, Quora-IN, Zhihu, etc.) who are expressing the
                       pain point our product solves. Reply to their post
                       publicly and DM them privately, in the local language.
                       When a lead has an email, send a cold email via Gmail.
  2. Signals stream — watch for funding rounds and hiring spikes as buying-intent
                       signals, then craft a timely LinkedIn DM that pitches the product.

Hard rules:
- This is GO-TO-MARKET outreach. You MUST introduce and pitch the product in every
  message. Reference the specific context (their post, their funding, their role),
  then clearly explain what the product does and why it is relevant to them right now.
- Always write in the country's primary language using its cultural register.
- NEVER mix languages. Every single word in any message body must be in the
  target language only. Do NOT insert words from French, Vietnamese, English,
  or any other language into a Korean, Japanese, Chinese, etc. message. Words
  like "interessant", "rất", "très", "sehr", or any non-target-language word
  are STRICTLY FORBIDDEN inside the body.
- If a channel has under 5% reply rate after 10 messages, deprioritize it.
- Always respond as valid JSON only. No prose, no markdown.
""".strip()


COMPANY_ANALYSIS_PROMPT = """
You are analyzing a company's public web presence so we can find opportunities for them in a specific country.

Company URL: {company_url}
Target country: {country} (we will reach out in {language_name})

Public information gathered (titles, summaries, pages):
{site_signals}

Based on this, infer:
1. What the company does (product / service)
2. Their ideal customer profile (role, company size, industry)
3. The single most important pain point their product solves
4. Country-tuned GTM goal — one sentence, action-oriented
5. 5-8 short keyword phrases in English that describe the PAIN or PROBLEM that
   potential customers experience — the words they would type into Reddit or
   LinkedIn when venting about frustration or asking for advice.
   CRITICAL: these must be pain expressions, NOT company names or product names.
   Good: "scaling data pipelines", "geo data too slow", "manual field ops"
   Bad: "GeoScale", "our platform", "the solution"
6. 5-8 keyword phrases in {language_name} that real customers in {country} would
   actually type into local platforms (Naver KiN, Zhihu, Reddit, Naver Blog)
   when discussing this pain or asking for help. Write natural {language_name}
   expressions — do NOT transliterate English words. These are critical for
   surfacing Korean/Japanese/Chinese posts. If {language_name} is English,
   use the same keywords as above.
7. Per-platform proactive search queries to find the ICP directly by role/title
   — people who WOULD benefit from the product even before they post about pain.
   These are search strings, not URLs.

Return ONLY valid JSON, no prose:
{{
  "goal": "Find pipeline + community presence for <product> in {country}",
  "icp_description": "Specific role + company stage + industry",
  "industry": "One short keyword like HR, fintech, dev tools, AI",
  "value_prop": "One sentence describing the product's value",
  "pain_point": "One short phrase describing the customer pain",
  "pain_keywords": ["English keyword 1", "English keyword 2", "English keyword 3"],
  "pain_keywords_local": ["로컬 키워드 1", "로컬 키워드 2", "로컬 키워드 3"],
  "icp_search_queries": {{
    "linkedin": "Job title OR seniority keywords that describe the ICP, e.g. VP Sales OR Head of Revenue at B2B SaaS startup",
    "tiktok": "Hashtag or topic keywords the ICP uses on TikTok, e.g. #startupfounder #saas outreach automation",
    "youtube": "Video search terms the ICP searches on YouTube, e.g. cold outreach tips for saas founders",
    "reddit": "Subreddit names or keywords where the ICP hangs out, e.g. r/sales r/startups cold outreach tools"
  }}
}}
""".strip()


ICP_SCORING_PROMPT = """
Score this lead 1-10 for ICP fit.

Our ICP: {icp_description}
Lead: {lead_data}

Score criteria:
- 9-10: Perfect match, contact immediately
- 7-8: Strong match, contact this week
- 5-6: Possible match, lower priority
- 1-4: Poor match, skip

Return JSON: {{"score": 8, "reason": "why"}}
""".strip()


# Platform-specific marketing style rules injected into both outreach prompts.
# Each entry describes format, tone, and CTA norms for that platform.
PLATFORM_STYLE_RULES: dict[str, str] = {
    "linkedin": (
        "FORMAT & TONE (LinkedIn):\n"
        "- Professional, authoritative, insight-first. Write like a thoughtful industry peer,\n"
        "  not a cold-call sales rep.\n"
        "- You MAY use 1-3 short paragraphs separated by blank lines, or 2-3 crisp bullet\n"
        "  points to highlight the product's specific value. No walls of text.\n"
        "- Mention the product/company NAME at least once — LinkedIn readers expect it.\n"
        "- CTA must feel natural: 'Happy to connect and walk you through it' or\n"
        "  'Would love to share how [product] handles this — open to a quick chat?'\n"
        "- Do NOT start with 'I hope this message finds you well.'"
    ),
    "reddit": (
        "FORMAT & TONE (Reddit):\n"
        "- Reddit HATES obvious ads. Lead with genuine empathy or a useful observation\n"
        "  about the post — earn credibility BEFORE mentioning the product.\n"
        "- Soft disclosure required: e.g. 'Full disclosure — I work on [product], which\n"
        "  tackles this exact problem...' This builds trust and avoids being flagged as spam.\n"
        "- Keep it conversational and humble. No exclamation marks, no buzzwords.\n"
        "- Max 3 short paragraphs. No bullet lists — they feel corporate on Reddit.\n"
        "- CTA must be low-pressure: 'Happy to share more in DMs if anyone's curious' or\n"
        "  'Feel free to check it out — no pressure at all.'"
    ),
    "instagram": (
        "FORMAT & TONE (Instagram):\n"
        "- Warm, punchy, emoji-friendly. Think brand voice, not B2B sales.\n"
        "- Keep it SHORT: 2-3 sentences max — Instagram readers skim comments.\n"
        "- Use 1-3 relevant emojis naturally woven into the text (not stacked at the end).\n"
        "- Product mention should feel organic: lead with the value, then name it.\n"
        "- CTA: 'DM us!' or 'Check the link in bio 👆' — never a long URL.\n"
        "- End with 1-3 hashtags relevant to the post topic."
    ),
    "youtube": (
        "FORMAT & TONE (YouTube):\n"
        "- Reference something SPECIFIC from the video or channel to prove authenticity.\n"
        "- 2-4 sentences. Casual but clear.\n"
        "- Introduce the product briefly as a solution to the video's topic or pain.\n"
        "- CTA: 'We made a free tool for this — search [product name] or DM me.'\n"
        "- Avoid pasting URLs in YouTube comments (they get filtered)."
    ),
    "twitter": (
        "FORMAT & TONE (Twitter / X):\n"
        "- Ultra-concise: 1-2 punchy sentences, ideally under 220 characters so there's\n"
        "  room for a short link.\n"
        "- Lead with the hook — pain or outcome — then name the product.\n"
        "- 1-2 relevant hashtags max. No emoji overload.\n"
        "- CTA: a short link or 'DM for a demo.'"
    ),
    "naver": (
        "FORMAT & TONE (Naver / Korean platforms):\n"
        "- Formal, respectful 존댓말 register. Relationship before pitch.\n"
        "- 3-4 sentences. Apologise briefly for the unsolicited message.\n"
        "- State the product's value clearly but modestly — avoid superlatives.\n"
        "- CTA: polite invitation to learn more, not a hard ask."
    ),
    "zhihu": (
        "FORMAT & TONE (Zhihu):\n"
        "- Knowledge-first: open with a genuine insight or answer to the question,\n"
        "  THEN introduce the product as a practical tool for that insight.\n"
        "- 3-5 sentences or a short structured answer. Quality over brevity.\n"
        "- Product disclosure should feel educational, not salesy.\n"
        "- CTA: 'Interested parties are welcome to follow our account for more.'"
    ),
    "quora": (
        "FORMAT & TONE (Quora):\n"
        "- Answer the question helpfully first — 2-3 sentences of genuine value.\n"
        "- Then organically introduce the product as one useful resource.\n"
        "- Use a disclosure: 'Disclosure: I work at [product].'\n"
        "- 4-6 sentences total. Professional, clear, no buzzwords.\n"
        "- CTA: 'You can try it free at [product name] — link in my profile.'"
    ),
}

_DEFAULT_PLATFORM_STYLE = (
    "FORMAT & TONE: Conversational but clearly promotional. 3-5 sentences. "
    "Lead with relevance to the post, then introduce the product and its value, "
    "then end with one concrete CTA."
)


def get_platform_style(platform: str) -> str:
    """Return the platform-specific style rules for the given platform slug."""
    key = (platform or "").lower().strip()
    return PLATFORM_STYLE_RULES.get(key, _DEFAULT_PLATFORM_STYLE)


LOCAL_OUTREACH_PROMPT = """
Write a marketing comment/reply to someone in {country} who wrote the post below.
Platform: {platform}

Their post:
\"\"\"
{source_post_excerpt}
\"\"\"

Our product (YOU MUST pitch this):
- Product: {product_summary}
- Pain we solve: {pain_point}

Cultural notes for {country}: {cultural_context}

Outreach voice hint (adapt, don't copy verbatim):
\"\"\"
{template_seed}
\"\"\"

PLATFORM RULES — follow these exactly:
{platform_style_rules}

CRITICAL — LANGUAGE MATCHING RULE:
- The post above is written in {post_language_name}. You MUST reply in {post_language_name}.
- Do NOT reply in {campaign_language_name} just because the campaign targets {country}.
  Match the language the person actually used in their post.
- LANGUAGE PURITY: Every single word must be in {post_language_name}. Do NOT mix in
  words from any other language. Pure {post_language_name} only.
- Exception: If the post has no text (empty), reply in {campaign_language_name}.

CONTENT rules (ALL required):
1. Open by referencing SPECIFICALLY what they wrote — show you read their post.
2. In 1-2 sentences, introduce our product and explain exactly how it solves the pain
   or opportunity they described. Be specific — name what it does.
3. End with ONE concrete CTA matched to the platform rules above.
{correction_note}
Return ONLY this JSON:
{{
  "language": "{reply_language}",
  "body": "the reply, in {post_language_name}",
  "english_gloss": "one-line literal translation back to English so a human can sanity-check"
}}
""".strip()


COLD_OUTREACH_PROMPT = """
Write a cold marketing outreach message in {language_name} to a professional in {country}
who fits our ideal customer profile. Platform: {platform}

Recipient:
- Name: {recipient_name}
- Title / Role: {recipient_title}
- Company: {recipient_company}

Our product (YOU MUST pitch this):
- Product: {product_summary}
- Pain we solve: {pain_point}

Cultural notes for {country}: {cultural_context}

PLATFORM RULES — follow these exactly:
{platform_style_rules}

LANGUAGE rules (ALL required):
- WRITE THE BODY IN {language_name}. Every single word must be in {language_name}.
  Do NOT mix in words from any other language. Pure {language_name} only.
- Open by referencing their SPECIFIC role or company — personalise the hook.
- In 1-2 sentences, introduce our product and make it clear how it solves the pain
  that someone in their role faces. Be direct about what we offer.
- Do NOT open with "I hope this finds you well."
- Tone-match {country} norms.
{correction_note}
Return ONLY this JSON:
{{
  "language": "{language}",
  "body": "the message, in {language_name}",
  "english_gloss": "one-line literal translation back to English so a human can sanity-check"
}}
""".strip()


SIGNAL_OUTREACH_PROMPT = """
Write a short, culturally appropriate LinkedIn DM to a likely buyer at a company
that just produced a buying-intent signal. The goal is to PITCH OUR PRODUCT as
the perfect fit for their current moment.

Signal type: {signal_type}      (one of: funding | hiring | engagement)
Signal text: {signal_text}
Signal source URL: {signal_url}
Recipient (best guess): {recipient_role} at {company_name}

Our product (YOU MUST pitch this):
- Product: {product_summary}
- Pain we solve: {pain_point}

Cultural notes for {country}: {cultural_context}

CRITICAL — LANGUAGE MATCHING RULE:
- The signal text above is written in {signal_language_name}. You MUST write the DM
  in {signal_language_name} to match the language of their content.
- Do NOT write in {campaign_language_name} just because the campaign targets {country}.
  If their LinkedIn post / job listing is in English, reply in English.
- LANGUAGE PURITY: Every single word must be in {signal_language_name}. Pure
  {signal_language_name} only — no words from any other language.

GTM rules (ALL required):
- Sentence 1: Reference the SPECIFIC signal to show this is timely and relevant:
    * funding   → acknowledge the raise briefly (1 short clause), then pivot immediately
                  to how this growth moment is exactly when our product creates the most
                  value. Do NOT spend the whole message congratulating — get to the pitch.
    * hiring    → mention the open role, then explain how our product can help them scale
                  faster or make that hire unnecessary.
    * engagement → reference what they engaged with, connect it to our product's value.
- Sentences 2-3: Clearly introduce our product and explain what it does and why it is
  the right tool for them RIGHT NOW given this signal. Be specific, not vague.
- Final sentence: ONE concrete question or soft call-to-action (e.g. "Would it be worth
  a quick 15-min call to see how [product] fits into your expansion plans?").
- 3-5 sentences total. Conversational but clearly promotional.
- Tone-match {country} norms.

Return ONLY this JSON:
{{
  "language": "{reply_language}",
  "body": "the DM, in {signal_language_name}",
  "english_gloss": "one-line literal translation back to English so a human can sanity-check"
}}
""".strip()


# Kept for legacy callers in the old loop. Safe to remove once all callers migrate.
DECISION_PROMPT = """
Goal: {goal}
Country: {country}
Recent signals: {signals}
Leads found: {leads_count}
Recent actions: {recent_actions}
Channel performance: {channel_stats}

What ONE action should you take right now?

Respond ONLY as JSON:
{{
  "action_type": "scan|think|act|wait|escalate",
  "stream": "people|signals",
  "channel": "linkedin|reddit|naver|quora|zhihu|google|apify",
  "action": "Exact description of what to do",
  "reasoning": "Why this action, why now",
  "next_check_minutes": 30
}}
""".strip()


# Cultural context is kept here as a fallback when COUNTRY_CONFIG doesn't have it.
CULTURAL_CONTEXT = {
    "South Korea": (
        "Hierarchy matters. Use formal titles. Relationship before business. Indirect "
        "communication. Use 존댓말. Apologize for the cold reach-out."
    ),
    "Japan": (
        "Extreme formality. です/ます form. Build trust via humility. Avoid hard asks; "
        "lead with respect."
    ),
    "India": (
        "Warm, relationship-first. Reference credibility (funding, customers). "
        "Persistence is respected."
    ),
    "China": (
        "Indirect, relationship-based. Reference credibility. Avoid sensitive topics."
    ),
    "Germany": (
        "Direct, fact-based. Privacy-conscious. References and credentials matter."
    ),
    "Singapore": (
        "Professional, polished. English standard. Concise and outcome-oriented."
    ),
    "United States": (
        "Direct, ROI-first. Casual but professional. Lead with numbers and outcomes."
    ),
    "Brazil": (
        "Warm, personal tone. Brazilians appreciate humor — stay professional in first contact."
    ),
}
