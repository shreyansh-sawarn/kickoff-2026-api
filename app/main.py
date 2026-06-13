"""
FastAPI application entry point.

Lifespan:
  - startup: init DB, start APScheduler
  - shutdown: stop scheduler

Mounts:
  - /api/v1/  → REST API
  - /admin/   → Admin UI (HTML)
  - /docs     → Auto-generated OpenAPI docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db.init_db import init_db
from app.scraper.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    logger.info("Starting kickoff-2026-api...")

    # Initialize database
    await init_db()
    logger.info("Database ready.")

    # Start scraper scheduler
    await start_scheduler()

    yield

    # Cleanup
    stop_scheduler()
    logger.info("kickoff-2026-api stopped.")


app = FastAPI(
    title="kickoff-2026-api",
    description=(
        "Self-hosted FIFA World Cup 2026 data API. "
        "Live scores, standings, goal scorers, assists, and cards — "
        "powered by Wikipedia scraping."
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="wc26_admin_session",
    max_age=86400,  # 24 hours
    https_only=False,  # Set to True in production (Fly.io handles HTTPS)
    same_site="lax",
)

# ---------------------------------------------------------------------------
# API routers
# ---------------------------------------------------------------------------

from app.api.v1 import events, matches, meta, scorers, standings, webhooks, news

api_v1_prefix = "/api/v1"

app.include_router(matches.router, prefix=api_v1_prefix)
app.include_router(scorers.router, prefix=api_v1_prefix)
app.include_router(standings.router, prefix=api_v1_prefix)
app.include_router(events.router, prefix=api_v1_prefix)
app.include_router(meta.router, prefix=api_v1_prefix)
app.include_router(webhooks.router, prefix=api_v1_prefix)
app.include_router(news.router, prefix=api_v1_prefix)

# ---------------------------------------------------------------------------
# Admin UI
# ---------------------------------------------------------------------------

from app.admin import routes as admin_routes

app.include_router(admin_routes.router)

# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

from fastapi.responses import RedirectResponse


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/docs")
