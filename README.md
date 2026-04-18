# GeoScale

Autonomous local market operator. Give it a goal, walk away, come back when a meeting is booked.

GeoScale is a 24/7 GTM agent. You give it one input — `"Acme HR Tech — expand to Seoul, South Korea"` — and it researches the market, finds ICPs, writes culturally tuned outreach, sends real LinkedIn DMs via [browser-use](https://browser-use.com), watches what works, and adjusts its strategy without human input.

## Architecture

```
frontend/  — Next.js 14 App Router, Tailwind, TypeScript
backend/   — FastAPI + SQLite + asyncio agent loop
              ├─ DigitalOcean GenAI (Llama 3.3 70B) for reasoning
              ├─ Apify — 15+ specialized actors across 5 categories
              │   (handles ALL scraping — including company analysis;
              │    no Tavily, no custom HTTP)
              │     ├─ native social  : Blind, Naver Cafe/Blog/KiN, Weibo, Xiaohongshu
              │     ├─ intent signals : funding (ET / DART / Naver News / TC+CB),
              │     │                   hiring (Naukri, Apna, LinkedIn Jobs)
              │     ├─ enrichment     : LinkedIn profile search + email finder
              │     ├─ engagement     : LinkedIn reactions / comments mining
              │     └─ discovery      : Google SERP + website-content-crawler
              └─ Browser-use for real-world actions (DMs, comments, contact forms)
```

Three parallel autonomous streams:

- **People** (every 30 min) — find buyers venting about the pain on LinkedIn /
  Reddit / native social, score for ICP fit, draft localized reply, send via
  browser-use. Top 5 leads with handles-but-no-LinkedIn get auto-enriched.
- **Opportunities** (every 2 h) — discover hackathons, conferences, accelerators,
  press, communities, then submit a localized pitch via contact form.
- **Signals** (every 4 h) — watch funding rounds + hiring spikes + competitor
  engagement; resolve each signal → likely buyer via LinkedIn search; send
  signal-aware DM (`"saw you raised Series A — also noticed you're hiring Head
  of People…"`). This is GeoScale's killer differentiator over a Google search.

## Run it

### 1. Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
uvicorn main:app --reload --port 8000
```

Required env vars (see `backend/.env.example`):

- `DIGITALOCEAN_API_KEY`
- `DIGITALOCEAN_BASE_URL` — your per-agent endpoint URL from the DO GenAI Platform
- `DIGITALOCEAN_MODEL` — defaults to `llama3.3-70b`, override if your endpoint serves a different model
- `APIFY_API_KEY`
- `BROWSER_USE_API_KEY`
- `BROWSER_USE_PROFILE_ID` — persistent Cloud profile that holds LinkedIn / Reddit / etc. cookies
- `BROWSER_USE_MODEL` — agent model for browser tasks (e.g. `claude-opus-4.7`)
- `BROWSER_USE_PROXY_COUNTRY` — residential proxy region, keep matched to the profile's usual geo (e.g. `US`)
- `MAX_APIFY_SPEND_USD` — soft cap (default `25`). When exceeded, the **Signals** and
  **enrichment** flows pause automatically and an error event is pushed to the SSE
  feed. People + opportunities streams keep running so the demo never goes dark.
- `OPENDART_API_KEY` *(optional)* — register free at https://opendart.fss.or.kr/ to
  unlock the South Korea DART funding-disclosure actor. If unset, GeoScale silently
  skips that actor and uses Naver News + the universal funding tracker instead.

### Browser Use profile (LinkedIn / Reddit auth)

GeoScale never stores or types LinkedIn / Reddit passwords. Auth is handled by a one-time
manual login captured into a persistent Browser Use Cloud profile, then replayed via cookies
on every agent run.

To create or refresh the profile, run locally:

```bash
export BROWSER_USE_API_KEY=bu_********
curl -fsSL https://browser-use.com/profile.sh | sh
```

This pops a Chromium window; log in to LinkedIn, Reddit, and anything else you want the agent
to act on, close the window, and the cookies are synced back to the cloud profile. Drop the
returned profile id into `BROWSER_USE_PROFILE_ID`. Every browser-use task in
[backend/agent/tools.py](backend/agent/tools.py) then runs against that profile.

Cookie lifetime is the only thing that expires:

- LinkedIn `li_at` lasts ~1 year
- Reddit `reddit_session` rolls faster (weeks)

When tasks start coming back with `auth_required` in the SSE feed, re-run the snippet above
to refresh the profile. The `_AUTH_GUARD` prompt in `tools.py` makes agents abort instead of
attempting to log in, so a stale profile fails loudly instead of silently spamming a login form.

### 2. Frontend

```bash
cd frontend
pnpm install         # or: npm install
cp .env.local.example .env.local
pnpm dev             # http://localhost:3000
```

## Demo flow

1. Open `http://localhost:3000`.
2. Enter company URL + goal, pick a market, paste LinkedIn credentials, hit deploy.
3. You're redirected to the live mission control dashboard. The agent immediately starts scanning, scoring leads, and sending DMs.
4. Pre-warm multiple sessions before a demo by deploying several markets — they all show up in the **Active sessions** list on the home page and keep running in the background.

### 60-second hackathon demo script

> "GeoScale is a 24/7 GTM agent for entering a foreign market. Watch it work live."

1. **0:00 — Deploy.** Form: `Acme HR Tech` → `Expand to Seoul`. Hit deploy.
2. **0:05 — Three parallel streams light up.** Point at the dashboard:
   `People` / `Signals` / `Opportunities` columns each get their own
   "Spawning…" event. The activity strip shows `apify · genai · browser-use`
   channels firing simultaneously.
3. **0:15 — Native scrape (People column).** Blind post scraper returns Korean
   HR-tech complaints from Naver employees. Watch a card render: handle, raw
   Korean snippet, ICP score, then `Enriching via LinkedIn` — handle resolves
   to a real `linkedin.com/in/...` profile.
4. **0:30 — Intent signal (Signals column).** A funding card appears:
   `🎯 Funding · Acme Korea raised ₩5B Series A` (source: Naver News). Click
   in: agent reasoning shows "company hiring 3 HR roles → high intent →
   resolving CHRO via LinkedIn search".
5. **0:40 — Outreach.** `genai` event: drafted Korean DM in 존댓말 referencing
   the round + the open req. `browser-use` event: DM sent. Channel stat for
   `linkedin` ticks `1 sent`.
6. **0:55 — Wrap.** "All of that in under a minute, fully autonomous, in the
   buyer's language, grounded in real signals — not a Google search."

Switch markets to **India** or **China** to show the same agent re-routing
through Naukri / Economic Times for India and Weibo / Xiaohongshu for China —
proves the per-country actor registry is real, not hardcoded to Korea.

## How it stays autonomous

- Three independent async tasks per campaign — `people` (30 min), `opportunities`
  (2 h), `signals` (4 h) — supervised by `agent/loop.py`. Any stream can crash
  without taking the others down.
- A separate hourly LLM "decision cycle" reads recent actions, channel stats,
  and fresh Apify signals, then picks the next strategic move.
- Every action is persisted to SQLite. Reconnecting to a dashboard replays the
  full history from the DB before attaching the live SSE stream — past sessions
  look identical to new ones.
- Pause endpoint cancels all three asyncio tasks and flips the campaign status;
  every loop also self-checks status each cycle.
- The agent escalates and stops itself when it detects a meeting opportunity
  (sets status to `meeting_booked`).
- Apify spend is tracked in-process; once `MAX_APIFY_SPEND_USD` is exceeded the
  expensive streams (signals + enrichment) self-throttle while cheap discovery
  keeps running.

## Apify actor registry

Configured per-country in [`backend/agent/country.py`](backend/agent/country.py)
and dispatched by [`backend/agent/scrapers.py`](backend/agent/scrapers.py) +
[`backend/agent/signals.py`](backend/agent/signals.py).

| Market | Native social | Funding signals | Hiring signals |
| --- | --- | --- | --- |
| **South Korea** | `hypebridge/blind-post-scraper`, `naver_crawling/naver-search-cafe-crawling`, `naver_crawling/naver-blog-crawler`, Naver KiN search | `oxygenated_quagmire/naver-news-scraper`, `fortuitous_pirate/south-korea-dart-scraper` | `curious_coder/linkedin-jobs-scraper` |
| **India** | LinkedIn search (HarvestAPI), Reddit (`/r/india`, `/r/bangalore`) | `complex_intricate_networks/economic-times-capital-tracker`, universal funding tracker | `whitestream/naukri-scraper`, `apna-jobs-scraper` |
| **China** | `apidojo/weibo-scraper`, `apify/xiaohongshu-search-scraper`, Douyin (fallback via Google) | universal funding tracker (`complex_intricate_networks/fundraising-and-startup-funding-scraper`) | `curious_coder/linkedin-jobs-scraper` |
| **Cross-market** | LinkedIn engagement: `harvestapi/linkedin-profile-reactions-scraper`, `harvestapi/linkedin-profile-comments-scraper` | — | — |
| **Enrichment** | `harvestapi/linkedin-profile-search-by-name`, `harvestapi/linkedin-profile-scraper` (with `email=true`) | — | — |

To swap an actor for a market, edit the `signals` / `people_sites` keys for that
country in `country.py`. To wire a brand-new platform, add an entry to
`PLATFORM_SCRAPERS` in `scrapers.py` with `actor`, `build_input`, and
`normalize` — the People stream picks it up automatically.

## File map

```
backend/
├── main.py                  FastAPI routes + agent task lifecycle + /signals endpoint
├── requirements.txt
├── .env.example
├── agent/
│   ├── llm.py               OpenAI-compatible client for DO GenAI
│   ├── prompts.py           System / decision / outreach / ICP / SIGNAL_OUTREACH prompts
│   ├── tools.py             Apify + browser-use wrappers + cost guardrail
│   ├── scrapers.py          Per-platform Apify actor registry (Blind, Naver, Weibo…)
│   ├── signals.py           Funding + hiring + competitor-engagement actors
│   ├── enrichment.py        LinkedIn search → full profile + email (cached)
│   ├── country.py           Per-country language, sites, signals actor IDs
│   ├── memory.py            SQLite read/write helpers (incl. CompanySignal)
│   ├── loop.py              The autonomous agent loop (spawns 3 streams)
│   └── streams/
│       ├── people.py        30-min loop: scrape → score → enrich → DM
│       ├── opportunities.py 2h loop  : hackathons / press / contact forms
│       └── signals.py       4h loop  : intent signals → resolve buyer → DM
└── models/
    └── db.py                SQLAlchemy models (Campaign, AgentAction, Lead, ChannelStat, CompanySignal)

frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx             Deploy form + active sessions list
│   ├── globals.css
│   └── dashboard/[marketId]/page.tsx   3-column mission control
├── components/
│   ├── DeployForm.tsx
│   ├── AgentFeed.tsx        Hydrates from DB, then attaches SSE
│   ├── PeopleStream.tsx     People column (leads + DMs)
│   ├── OpportunitiesStream.tsx Opportunities column
│   ├── SignalsStream.tsx    Intent-signals column (funding / hiring / engagement)
│   ├── PanelActivityStrip.tsx
│   └── CampaignsList.tsx
└── lib/
    ├── api.ts
    └── types.ts
```
