# kickoff-2026-api

A **self-hosted, free FIFA World Cup 2026 data API** — live scores, standings, goal scorers, assists, and cards — powered by Wikipedia scraping.

## Why Build This?

Every public football API either blocks WC2026 on the free tier or charges $20–$30/month for scorer/card data. Wikipedia editors update World Cup match pages within 1–2 minutes of live events. We poll Wikipedia, parse the structured Wikitext, and serve it through a clean REST API.

## Features

- 🏟️ **Live match scores** — updated every 60 seconds during matches
- ⚽ **Goal scorers** with minutes, penalties, own goals
- 🟨🟥 **Cards** — yellow, red, yellow-red
- 📋 **Group standings** — all 12 groups (A–L)
- 🔑 **Admin UI** — manual override any data the scraper gets wrong
- 📖 **Auto-generated OpenAPI docs** at `/docs`
- 🐳 **Docker + Fly.io** deployment config included

## Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)

### Setup

```bash
# Clone and enter the repo
git clone https://github.com/yourname/kickoff-2026-api
cd kickoff-2026-api

# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env
# Edit .env — set ADMIN_PASSWORD at minimum

# Create data directory
mkdir -p data

# Run the server
uv run uvicorn app.main:app --reload --port 8000
```

The server starts at `http://localhost:8000`.

- **API docs**: http://localhost:8000/docs
- **Admin UI**: http://localhost:8000/admin/
- **Health check**: http://localhost:8000/api/v1/health

## API Reference

### Matches

```
GET /api/v1/matches              # All matches (filter: status, group, stage, date)
GET /api/v1/matches/live         # Currently live matches only
GET /api/v1/matches/{match_id}   # Full match detail + events
```

### Leaderboards

```
GET /api/v1/scorers              # Top goal scorers (?limit=20&team=FRA)
GET /api/v1/assists              # Top assist providers
GET /api/v1/yellow-cards         # Yellow card leaders
GET /api/v1/red-cards            # Red card leaders
```

### Standings

```
GET /api/v1/standings            # All group standings
GET /api/v1/standings/A          # Single group (A–L)
```

### Events

```
GET /api/v1/events               # Match events (filter: match_id, type, team)
```

### Webhooks

Receive real-time push notifications via HTTP POST when a match state changes.

```
POST /api/v1/webhooks/subscribe  # Register a URL for events like 'match.goal'
DELETE /api/v1/webhooks/{id}     # Remove a subscription
```
*Note: Includes HMAC SHA-256 `X-Hub-Signature` support for payload verification.*

### Meta

```
GET /api/v1/health               # { status: "ok" }
GET /api/v1/status               # Scraper status, last scrape time, match counts
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ADMIN_PASSWORD` | `admin` | Password for the admin UI |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/wc26.db` | SQLite DB path |
| `SCRAPER_ENABLED` | `true` | Enable/disable the Wikipedia poller |
| `POLL_INTERVAL_LIVE_SECONDS` | `60` | Poll interval during live matches |
| `POLL_INTERVAL_IDLE_SECONDS` | `300` | Poll interval between matches |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |
| `SESSION_SECRET` | `dev_secret_change_in_prod` | Cookie signing secret |

## Running Tests

```bash
# Unit tests only (no network)
uv run pytest tests/ -v -m "not asyncio"

# All tests including Wikipedia integration tests
uv run pytest tests/ -v

# Scraper parser tests against WC2022 pages
uv run pytest tests/test_scraper.py -v -s
```

## Deploy to Fly.io

```bash
# Install Fly CLI
iwr https://fly.io/install.ps1 -useb | iex   # Windows PowerShell

# Login
fly auth login

# Create app (first time)
fly launch --name kickoff-2026-api --no-deploy

# Create persistent volume for SQLite
fly volumes create wc26_data --size 1 --region lax

# Set secrets
fly secrets set ADMIN_PASSWORD=your_secure_password
fly secrets set SESSION_SECRET=your_long_random_secret
fly secrets set CORS_ORIGINS=https://kickoff-2026.vercel.app

# Deploy
fly deploy
```

API live at: `https://kickoff-2026-api.fly.dev`

## Architecture

```
Wikipedia MediaWiki API
        │
        ▼
APScheduler (60s/300s/900s adaptive)
        │
        ▼
Wikipedia Scraper → SQLite DB (aiosqlite)
                           │
                    ┌──────┴──────┐
                    │             │
                FastAPI       Admin UI
               /api/v1/      /admin/
```

## Phased Roadmap

| Phase | Status | What |
|---|---|---|
| Phase 1 | ✅ **Current** | Wikipedia scraper, REST API, Admin UI, Fly.io deploy |
| Phase 2 | 🔄 During tournament | FIFA 2nd source, conflict detection, webhooks, SSE |
| Phase 3 | 💰 Mid-tournament | API keys, rate limiting, RapidAPI listing |

## License

MIT