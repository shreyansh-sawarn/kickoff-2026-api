# `kickoff-2026-api` — Implementation Plan
### A self-hosted, free FIFA World Cup 2026 data API

---

## Background & Motivation

This document is fully self-contained. No prior context is needed.

We are building a **new standalone backend repository** (`kickoff-2026-api`) that serves live FIFA World Cup 2026 data — match scores, goal scorers, assists, yellow/red cards, standings — via a clean REST API.

### Why not use an existing football API?

| Option | Problem |
|---|---|
| API-Football (api-sports.io) | Free tier blocks season 2026. Pro plan = $19/month |
| football-data.org | Scorers/cards require €29/month. No assists at any tier |
| TheSportsDB | Has fixtures but zero player event data |
| worldcup26.ir (unofficial) | Returns `null` for all scorer/event fields |

**The solution:** Build our own data pipeline. Wikipedia editors update World Cup match pages within **1–2 minutes** of a goal or red card during live matches — a well-documented phenomenon used by several real-time sports data services. We poll Wikipedia on a fast cycle, parse structured match data, and serve it through our own API. A manual admin override UI lets an operator correct any discrepancy.

### What this repo produces

- A **REST API** (`/api/v1/...`) consumed by the `kickoff-2026` Next.js frontend (and potentially third-party developers)
- An **admin UI** (password-protected web interface) for manually overriding any match data
- A **webhook dispatcher** that fires events to registered endpoints when goals or cards are detected
- A path to becoming a **commercial sports data product**

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    kickoff-2026-api                          │
│                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐ │
│  │  Scheduler  │───▶│   Scrapers   │───▶│   SQLite DB     │ │
│  │ (APScheduler│    │ (Wikipedia   │    │ (matches,       │ │
│  │  60s cycle) │    │  + FIFA ph2) │    │  events,        │ │
│  └─────────────┘    └──────────────┘    │  overrides,     │ │
│                                         │  api_keys,      │ │
│  ┌─────────────┐                        │  webhooks)      │ │
│  │  Admin UI   │───▶(reads/writes)──────│                 │ │
│  │ (Jinja2     │                        └────────┬────────┘ │
│  │  templates) │                                 │          │
│  └─────────────┘                                 │          │
│                                         ┌────────▼────────┐ │
│  ┌─────────────┐                        │   FastAPI App   │ │
│  │  Webhook    │◀───(on change)─────────│   REST API      │ │
│  │  Dispatcher │                        │   /api/v1/...   │ │
│  └─────────────┘                        └─────────────────┘ │
└──────────────────────────────────────────────────────────────┘
            ▲ consumed by
┌───────────┴───────────────────────────────┐
│  kickoff-2026 (Next.js frontend)          │
│  calls https://kickoff-2026-api.fly.dev/  │
└───────────────────────────────────────────┘
```

---

## Tech Stack Decisions

| Component | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Best scraping ecosystem; cleaner Wikipedia HTML parsing |
| API framework | **FastAPI** | Async, automatic OpenAPI docs, SSE support, fast |
| Scraping | **httpx + BeautifulSoup4** | httpx is async-native; BS4 is the standard for HTML parsing |
| Scheduler | **APScheduler** | Mature, flexible; can vary poll interval (60s live, 5min pre-match) |
| Database | **SQLite + SQLAlchemy** | Zero cost, zero infrastructure, embedded. Single writer (poller), many readers (API). Sufficient for this scale. |
| Admin UI | **Jinja2 templates** (built into FastAPI) | No separate frontend needed. Simple form-based interface. |
| Hosting | **Fly.io (free tier)** | Always-on (doesn't spin down like Render). 3 shared VMs, 256MB RAM — sufficient. No credit card required to start. |
| Package manager | **uv** | Fast, modern Python package manager |
| Config | **python-dotenv** | Environment variable management |

---

## Repository Structure

```
kickoff-2026-api/
├── README.md
├── pyproject.toml          # uv/pip dependencies
├── .env.example            # Template for environment variables
├── .env                    # NOT committed (gitignored)
├── fly.toml                # Fly.io deployment config
├── Dockerfile
│
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI app entry point, lifespan events
│   ├── config.py           # Settings loaded from .env
│   ├── dependencies.py     # Shared FastAPI dependencies (DB session, auth)
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py     # SQLAlchemy engine + session factory
│   │   ├── models.py       # All ORM models
│   │   └── init_db.py      # Creates tables on first run
│   │
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── scheduler.py    # APScheduler setup, poll intervals
│   │   ├── wikipedia.py    # Wikipedia polling + HTML parsing logic
│   │   ├── fifa.py         # FIFA match center (Phase 2)
│   │   └── reconciler.py   # Cross-source conflict detection (Phase 2)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── matches.py      # GET /api/v1/matches
│   │   │   ├── scorers.py      # GET /api/v1/scorers
│   │   │   ├── standings.py    # GET /api/v1/standings
│   │   │   ├── events.py       # GET /api/v1/events
│   │   │   └── webhooks.py     # POST /api/v1/webhooks (register)
│   │
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── routes.py           # Admin UI page routes
│   │   └── templates/
│   │       ├── base.html
│   │       ├── dashboard.html
│   │       ├── match_detail.html
│   │       ├── override_form.html
│   │       └── login.html
│   │
│   └── webhooks/
│       ├── __init__.py
│       └── dispatcher.py       # Fires HTTP POST to registered endpoints
│
└── data/
    └── wc26.db                 # SQLite database file (gitignored in prod)
```

---

## Database Schema

### `matches` table
```sql
CREATE TABLE matches (
    id              TEXT PRIMARY KEY,   -- e.g. "group_a_match_1"
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    home_team_code  TEXT,               -- e.g. "USA"
    away_team_code  TEXT,               -- e.g. "MEX"
    kickoff_utc     DATETIME NOT NULL,
    venue           TEXT,
    group_name      TEXT,               -- "Group A", "Round of 32", etc.
    stage           TEXT,               -- "group", "r32", "r16", "qf", "sf", "final"
    status          TEXT DEFAULT 'scheduled', -- scheduled | live | finished
    home_score      INTEGER,
    away_score      INTEGER,
    home_score_ht   INTEGER,            -- half-time score
    away_score_ht   INTEGER,
    source          TEXT,               -- "wikipedia" | "fifa" | "override"
    wikipedia_url   TEXT,               -- URL of the Wikipedia match page
    last_scraped_at DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### `events` table
```sql
CREATE TABLE events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        TEXT REFERENCES matches(id),
    type            TEXT NOT NULL,  -- "goal" | "own_goal" | "penalty" | "yellow" | "red" | "yellow_red" | "assist" | "sub"
    player_name     TEXT,
    team_code       TEXT,
    minute          INTEGER,        -- match minute (e.g. 45, 90+3 stored as 93)
    extra_info      TEXT,           -- e.g. "penalty" | "header" | assisting player name
    source          TEXT,           -- "wikipedia" | "fifa" | "override"
    is_overridden   BOOLEAN DEFAULT FALSE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### `standings` table
```sql
CREATE TABLE standings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name      TEXT NOT NULL,   -- "Group A" through "Group L"
    team_name       TEXT NOT NULL,
    team_code       TEXT,
    played          INTEGER DEFAULT 0,
    won             INTEGER DEFAULT 0,
    drawn           INTEGER DEFAULT 0,
    lost            INTEGER DEFAULT 0,
    goals_for       INTEGER DEFAULT 0,
    goals_against   INTEGER DEFAULT 0,
    goal_diff       INTEGER DEFAULT 0,
    points          INTEGER DEFAULT 0,
    position        INTEGER,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### `overrides` table (audit log of manual corrections)
```sql
CREATE TABLE overrides (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT,       -- "match" | "event" | "standings"
    entity_id       TEXT,       -- match_id or event id
    field_name      TEXT,       -- e.g. "home_score", "player_name"
    old_value       TEXT,
    new_value       TEXT,
    reason          TEXT,       -- operator note
    applied_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### `webhook_subscriptions` table (Phase 2)
```sql
CREATE TABLE webhook_subscriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT NOT NULL,
    secret      TEXT,           -- HMAC signing secret
    events      TEXT,           -- JSON array: ["goal","red_card","fulltime"]
    active      BOOLEAN DEFAULT TRUE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### `api_keys` table (Phase 3 — for selling)
```sql
CREATE TABLE api_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash    TEXT UNIQUE NOT NULL,   -- SHA256 hash of the actual key
    owner_name  TEXT,
    owner_email TEXT,
    plan        TEXT DEFAULT 'free',   -- "free" | "pro"
    requests_today  INTEGER DEFAULT 0,
    daily_limit     INTEGER DEFAULT 1000,
    active      BOOLEAN DEFAULT TRUE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## Wikipedia Scraping — How It Works

### Key insight
Wikipedia has **dedicated pages for every World Cup match** with structured infoboxes, plus group stage summary tables. Editors update these pages within 1–2 minutes of live events during the tournament.

### Pages to poll

**Group stage summary (for live scores + standings):**
```
https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_group_stage
```
This single page has ALL group matches with scores in wikitable format. Poll this every 60 seconds during active match windows.

**Individual match pages (for events: scorers, cards):**
```
https://en.wikipedia.org/wiki/Mexico_v_Poland_(2026_FIFA_World_Cup)
```
Pattern: `{HomeTeam}_v_{AwayTeam}_(2026_FIFA_World_Cup)`
These pages have the detailed match infobox with goal scorers, cards, minutes.

**Knockout stage pages:**
```
https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage
```

### Using Wikipedia's REST API (preferred over raw HTML)
Wikipedia provides a Mediawiki REST API that returns structured Wikitext — easier to parse than rendered HTML:
```
GET https://en.wikipedia.org/w/api.php?action=parse&page=2026_FIFA_World_Cup_group_stage&prop=wikitext&format=json
```
This returns the raw Wikitext which has a predictable format for wikitables and infoboxes.

### Parsing approach
1. Fetch Wikitext via MediaWiki API (no auth needed, generous rate limits)
2. Parse `{{Football box` infobox templates for individual match pages → extract home/away score, goal events, cards, minutes
3. Parse `{| class="wikitable"` tables on the group stage page → extract group standings
4. Compare parsed data to current DB state
5. On change detected → update DB + trigger webhook dispatcher

### Polling schedule
```python
# During a live match window (kickoff ± 2 hours):
poll_interval = 60   # seconds

# Between matches (no live games right now):
poll_interval = 300  # 5 minutes

# Night hours (UTC 00:00–08:00, no WC matches scheduled):
poll_interval = 900  # 15 minutes
```

---

## REST API Endpoints (`/api/v1/`)

All responses are JSON. All endpoints support CORS.

### Matches
```
GET /api/v1/matches
  ?status=scheduled|live|finished
  ?group=A|B|...|L
  ?stage=group|r32|r16|qf|sf|final
  ?date=2026-06-11

GET /api/v1/matches/{match_id}
  → Full match detail including all events

GET /api/v1/matches/live
  → Only currently live matches
```

### Player Leaderboards
```
GET /api/v1/scorers
  ?limit=20 (default)
  → Ranked list: player_name, team, goals, assists

GET /api/v1/assists
  → Ranked list: player_name, team, assists

GET /api/v1/yellow-cards
GET /api/v1/red-cards
GET /api/v1/minutes-played
```

### Standings
```
GET /api/v1/standings
  → All groups

GET /api/v1/standings/{group}
  → e.g. /api/v1/standings/A
```

### Events (timeline)
```
GET /api/v1/events
  ?match_id=...
  ?type=goal|yellow|red|assist
  ?team=...
```

### Webhooks (Phase 2)
```
POST /api/v1/webhooks/subscribe
  Body: { url, secret, events: ["goal", "red_card", "fulltime"] }

DELETE /api/v1/webhooks/{id}
```

### Meta
```
GET /api/v1/status
  → { last_scraped_at, matches_tracked, db_version, sources_active }

GET /api/v1/health
  → { status: "ok" }
```

---

## Admin UI

Password-protected. Set `ADMIN_PASSWORD` in `.env`.

### Pages

**`/admin/`** — Dashboard
- Last scrape timestamp + source status
- Count of live matches
- Recent changes detected by scraper
- Quick links

**`/admin/matches`** — Match list
- Table of all matches with current scores
- Status badges (scheduled / live / finished)
- "Edit" button per match

**`/admin/matches/{match_id}`** — Match detail + override
- Shows all scraped events (goals, cards, minutes)
- Form to: edit score, add/remove/edit any event, change match status
- All changes logged to `overrides` table with timestamp
- "Mark as overridden" flag so scraper doesn't overwrite it

**`/admin/standings`** — Standings overview
- Group tables as rendered HTML
- Manual edit option per row

**`/admin/scrapers`** — Scraper control
- Toggle scraper on/off
- Manually trigger a scrape right now
- View last 50 scrape logs (success/fail/changes detected)
- Adjust poll intervals

**`/admin/webhooks`** — Webhook subscriptions (Phase 2)
- List all registered webhooks
- Test fire a webhook
- Enable/disable per subscription

---

## Environment Variables (`.env`)

```bash
# Admin UI
ADMIN_PASSWORD=your_secure_password_here

# Database
DATABASE_URL=sqlite:///./data/wc26.db

# Scraper settings
SCRAPER_ENABLED=true
POLL_INTERVAL_LIVE_SECONDS=60
POLL_INTERVAL_IDLE_SECONDS=300
WIKIPEDIA_USER_AGENT=kickoff-2026-api/1.0 (contact@youremail.com)

# CORS (comma-separated origins allowed to call your API)
CORS_ORIGINS=https://kickoff-2026.vercel.app,http://localhost:3000

# API Key auth (Phase 3 — leave empty to disable)
REQUIRE_API_KEY=false

# Webhook signing secret (Phase 2)
WEBHOOK_SIGNING_SECRET=

# Optional: Sentry DSN for error tracking (free tier)
SENTRY_DSN=
```

---

## Deployment — Fly.io (Free Tier)

Fly.io's free tier includes:
- 3 shared-CPU VMs (256MB RAM each) — always on, no spin-down
- 3GB persistent volume storage (for SQLite)
- No credit card required for the free tier

### Steps

1. **Install Fly CLI:**
   ```bash
   # Windows (PowerShell):
   iwr https://fly.io/install.ps1 -useb | iex
   ```

2. **Login:**
   ```bash
   fly auth login
   ```

3. **Create app:**
   ```bash
   fly launch --name kickoff-2026-api --no-deploy
   ```

4. **Create a persistent volume** (for SQLite):
   ```bash
   fly volumes create wc26_data --size 1 --region lax
   ```

5. **Set secrets:**
   ```bash
   fly secrets set ADMIN_PASSWORD=your_password_here
   fly secrets set CORS_ORIGINS=https://kickoff-2026.vercel.app
   ```

6. **Deploy:**
   ```bash
   fly deploy
   ```

7. **Your API is live at:**
   ```
   https://kickoff-2026-api.fly.dev/api/v1/
   https://kickoff-2026-api.fly.dev/admin/
   https://kickoff-2026-api.fly.dev/docs   ← Auto-generated OpenAPI docs
   ```

### `fly.toml` (key settings)
```toml
app = "kickoff-2026-api"
primary_region = "lax"  # Los Angeles — close to WC host cities

[build]

[mounts]
  source = "wc26_data"
  destination = "/app/data"

[http_service]
  internal_port = 8000
  force_https = true

[[vm]]
  memory = "256mb"
  cpu_kind = "shared"
  cpus = 1
```

---

## Phased Rollout

### ✅ Phase 1 — Before June 11 (MVP, ~3–4 days)
- [ ] Repo setup (uv, FastAPI, SQLAlchemy, SQLite)
- [ ] Database models + init script
- [ ] Wikipedia scraper: group stage page → match scores
- [ ] Wikipedia scraper: individual match pages → goal scorers + red cards
- [ ] APScheduler with adaptive poll intervals
- [ ] REST API: `/matches`, `/scorers`, `/standings`, `/events`, `/health`, `/status`
- [ ] Admin UI: dashboard, match list, match override form, scraper controls
- [ ] Dockerfile + fly.toml
- [ ] Deploy to Fly.io
- [ ] Update `kickoff-2026` frontend to call this API instead of `worldcup26.ir`

### 🔄 Phase 2 — During tournament (Week 1–2)
- [ ] Add yellow card + assist parsing from Wikipedia match pages
- [ ] Add FIFA match-center as second source
- [ ] Conflict detection logic (Wikipedia vs FIFA disagreement → alert in admin)
- [ ] Webhook registration + async dispatcher
- [ ] SSE endpoint for live match state push (`/api/v1/stream`)

### 💰 Phase 3 — Commercial (mid-tournament if data quality is good)
- [ ] API key generation + hashing
- [ ] Rate limiting middleware per key
- [ ] Usage tracking (requests per key per day)
- [ ] API key management in admin UI
- [ ] List on **RapidAPI marketplace**
- [ ] Add usage dashboard to admin UI

---

## Connecting the Frontend (`kickoff-2026`)

In the Next.js frontend, replace all calls to `worldcup26.ir` with calls to this API.

Create a new environment variable in `apps/web/.env`:
```bash
# Replace existing worldcup26.ir API
WC26_API_BASE_URL=https://kickoff-2026-api.fly.dev
```

The Next.js API routes (`/app/api/matches/route.ts`, etc.) become thin proxies that call your new Python backend.

---

## Wikipedia Data Quality Notes

- **Goal scorers**: Available within 1–2 minutes on individual match pages. Very reliable.
- **Red cards**: Same — shown in the infobox with minute and player name.
- **Yellow cards**: Added to match pages but sometimes 5–15 minutes after the event. Acceptable.
- **Assists**: Added within the first half-hour of match completion. Not real-time, but accurate.
- **Scores**: Updated on the group stage summary page within 1–2 minutes. Very reliable.
- **Own goals**: Marked distinctly in Wikipedia infoboxes — parse and flag accordingly.
- **Penalties (shootout)**: Wikipedia tracks shootout results on knockout match pages.

**Important:** Wikipedia match pages for WC2026 will follow the same structure as WC2022. You can verify the structure and test your parser against WC2022 pages *right now*, before the tournament starts.

Test URL for parser development:
```
https://en.wikipedia.org/wiki/France_v_Morocco_(2022_FIFA_World_Cup)
https://en.wikipedia.org/wiki/2022_FIFA_World_Cup_group_stage
```

---

## Dependencies (`pyproject.toml`)

```toml
[project]
name = "kickoff-2026-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "sqlalchemy>=2.0.0",
    "httpx>=0.27.0",
    "beautifulsoup4>=4.12.0",
    "apscheduler>=3.10.0",
    "jinja2>=3.1.0",
    "python-dotenv>=1.0.0",
    "python-multipart>=0.0.9",    # for form parsing in admin UI
    "itsdangerous>=2.2.0",        # for admin session cookies
    "aiosqlite>=0.20.0",          # async SQLite driver
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",   # for TestClient
]
```

---

## Key Design Decisions (rationale)

1. **SQLite over Postgres**: No hosted DB cost. Single-writer pattern (only the scraper writes) makes SQLite ideal. If the project grows to sell API access at scale, migrating to Turso (SQLite at the edge, free tier) requires a one-line connection string change.

2. **Jinja2 admin UI over React**: Keeps the repo single-language (Python). No build step. Faster to build. The admin UI is operator-only, not user-facing — simplicity beats aesthetics here.

3. **Wikipedia as primary source**: Genuinely proven for live football. Wikipedia editors have a strong culture of real-time updates during major tournaments. The MediaWiki API is free, has no authentication, and has generous rate limits (as long as you set a proper `User-Agent` header).

4. **APScheduler over Celery/Redis**: Celery requires a Redis broker (adds cost/complexity). APScheduler runs in-process, which is fine for a single-instance scraper. No extra infrastructure.

5. **Adaptive poll intervals**: Polling every 60 seconds 24/7 would waste resources. Knowing the WC2026 schedule, we can automatically reduce polling frequency when no match is in progress.

6. **Override always wins**: When an operator sets a manual override for a field, the scraper will never overwrite it. This is tracked via the `is_overridden` flag and the `overrides` audit table.
