AGENT_SYSTEM_PROMPT = """
You are GeoScale, an autonomous global GTM agent. Your job is to find opportunities for a company in a specific COUNTRY and reach out to people, communities, and event organizers in that country's local language.

You operate two parallel streams:
  1. People stream  — find individuals on LinkedIn / Reddit / native platforms
                       (Naver, Quora-IN, Zhihu, etc.) who are expressing the
                       pain point our product solves. Reply to their post
                       publicly and DM them privately, in the local language.
  2. Opportunity stream — find hackathons, conferences, accelerators, press
                       outlets, and tech communities in that country and
                       reach out to organizers / editors with a translated pitch.

Hard rules:
- NEVER pitch the product in a first message. Lead with empathy and reference
  the post / event the person actually wrote / runs.
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
5. 5-8 short keyword phrases (in English) that real customers in {country} would
   use online when complaining about this pain or asking for a solution.
6. Per-platform proactive search queries to find the ICP directly by role/title
   — people who WOULD benefit from the product even before they post about pain.
   These are search strings, not URLs.

Return ONLY valid JSON, no prose:
{{
  "goal": "Find pipeline + community presence for <product> in {country}",
  "icp_description": "Specific role + company stage + industry",
  "industry": "One short keyword like HR, fintech, dev tools, AI",
  "value_prop": "One sentence describing the product's value",
  "pain_point": "One short phrase describing the customer pain",
  "pain_keywords": ["keyword 1", "keyword 2", "keyword 3"],
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


LOCAL_OUTREACH_PROMPT = """
Write a short, culturally appropriate REPLY to someone in {country} who wrote the post below. This is a public reply (or DM) on {platform}.

Their post:
\"\"\"
{source_post_excerpt}
\"\"\"

About us (DO NOT pitch in first message):
- Product: {product_summary}
- Pain we address: {pain_point}

Cultural notes for {country}: {cultural_context}

Outreach voice hint (adapt, don't copy verbatim):
\"\"\"
{template_seed}
\"\"\"

CRITICAL — LANGUAGE MATCHING RULE:
- The post above is written in {post_language_name}. You MUST reply in {post_language_name}.
- Do NOT reply in {campaign_language_name} just because the campaign targets {country}.
  Match the language the person actually used in their post.
- LANGUAGE PURITY: Every single word must be in {post_language_name}. Do NOT mix in
  words from any other language. Pure {post_language_name} only.
- Exception: If the post has no text (empty), reply in {campaign_language_name}.

Other hard rules:
- Reference SPECIFICALLY what they actually wrote. Show you read their post. Do NOT
  write a generic message that could have been sent to anyone.
- 2-4 short sentences max.
- Do NOT mention our product by name. Hint that we work in this space and ask
  one curious follow-up question.
- Tone-match {country} norms and the seed template's voice.

Return ONLY this JSON:
{{
  "language": "{reply_language}",
  "body": "the reply, in {post_language_name}",
  "english_gloss": "one-line literal translation back to English so a human can sanity-check"
}}
""".strip()


COLD_OUTREACH_PROMPT = """
Write a short, culturally appropriate cold outreach message in {language_name} to a
professional in {country} who fits our ideal customer profile. This is an initial
DM on {platform} — there is no prior post to reference.

Recipient:
- Name: {recipient_name}
- Title / Role: {recipient_title}
- Company: {recipient_company}

About us (DO NOT pitch in first message):
- Product: {product_summary}
- Pain we address: {pain_point}

Cultural notes for {country}: {cultural_context}

Hard rules:
- WRITE THE BODY IN {language_name}. Every single word must be in {language_name}.
  Do NOT mix in words from any other language. Pure {language_name} only.
- Reference their SPECIFIC role or company — show this is not a mass blast.
- Do NOT mention our product by name. Hint that we work in this space.
- 2-3 short sentences max. End with one curious follow-up question.
- Do NOT open with "I hope this finds you well" or any generic opener.
- Tone-match {country} norms.

Return ONLY this JSON:
{{
  "language": "{language}",
  "body": "the message, in {language_name}",
  "english_gloss": "one-line literal translation back to English so a human can sanity-check"
}}
""".strip()


SIGNAL_OUTREACH_PROMPT = """
Write a short, culturally appropriate LinkedIn DM to a likely buyer at a company
that just produced a buying-intent signal.

Signal type: {signal_type}      (one of: funding | hiring | engagement)
Signal text: {signal_text}
Signal source URL: {signal_url}
Recipient (best guess): {recipient_role} at {company_name}

About us:
- Product: {product_summary}
- Pain we address: {pain_point}

Cultural notes for {country}: {cultural_context}

CRITICAL — LANGUAGE MATCHING RULE:
- The signal text above is written in {signal_language_name}. You MUST write the DM
  in {signal_language_name} to match the language of their content.
- Do NOT write in {campaign_language_name} just because the campaign targets {country}.
  If their LinkedIn post / job listing is in English, reply in English.
- LANGUAGE PURITY: Every single word must be in {signal_language_name}. Pure
  {signal_language_name} only — no words from any other language.

Other hard rules:
- The FIRST sentence MUST reference the SPECIFIC signal:
    * funding   → congratulate on the raise; reference round / amount if known
    * hiring    → reference the open req for {recipient_role}; imply you can help
                  them ramp the new hire faster (or remove the need entirely)
    * engagement → reference what they engaged with; ask a curious question
- 3-5 short sentences total. Do NOT pitch the product by name in the first DM.
- End with one curiosity-driven question, not a meeting ask.
- Tone-match {country} norms.

Return ONLY this JSON:
{{
  "language": "{reply_language}",
  "body": "the DM, in {signal_language_name}",
  "english_gloss": "one-line literal translation back to English so a human can sanity-check"
}}
""".strip()


OPPORTUNITY_CLASSIFICATION_PROMPT = """
Classify each of these search results as one of: hackathon, event, accelerator, press, community, vc, irrelevant.

Type definitions:
- hackathon: coding competition or hackathon event
- event: conference, meetup, summit, or demo day
- accelerator: startup accelerator or incubator program
- press: tech media, journalist, news outlet, blog that covers startups in the target industry
- community: online or in-person founder / developer / startup community
- vc: venture capital fund, angel network, or government grant program that invests in startups
- irrelevant: not relevant to the goal

Results:
{results}

Pick the {limit} most relevant ones for: {goal}, in country: {country}, industry: {industry}.
Prioritize press contacts (type=press) and VC programs (type=vc) highly — these are direct business impact.
For press results, try to identify a contact email or contact page URL if visible in the result.

Return ONLY JSON:
{{
  "opportunities": [
    {{
      "type": "hackathon|event|accelerator|press|community|vc",
      "title": "...",
      "url": "...",
      "summary": "1 sentence why this is a fit",
      "score": 1-10
    }}
  ]
}}
""".strip()


OPPORTUNITY_PITCH_PROMPT = """
Write a short pitch in {language_name} aimed at the organizer / editor of this opportunity in {country}. They will read it via a contact form, sponsorship page, or email.

Opportunity:
- Type: {opp_type}
- Title: {opp_title}
- Page summary: {page_excerpt}

About us:
- Product: {product_summary}
- Why we are a relevant {opp_type}: {relevance}

Cultural notes for {country}: {cultural_context}

Hard rules:
- WRITE EVERYTHING IN {language_name}. Every single word must be in {language_name}.
  Do NOT mix in words from other languages (no "interessant", "rất", "très",
  or any non-{language_name} word).
- 4-7 sentences. Concrete, specific, no buzzwords.
- For hackathons / events: offer to sponsor, mentor, or speak.
- For press: offer a story angle / data / executive interview.
- For accelerators / communities: ask how to participate / join / contribute.
- End with one clear ask + a callback option.

Return ONLY JSON:
{{
  "language": "{language}",
  "subject": "subject line in {language_name}",
  "body": "the pitch, in {language_name}",
  "english_gloss": "one-paragraph literal translation back to English"
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
  "stream": "people|opportunities",
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
