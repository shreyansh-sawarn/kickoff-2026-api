"""
GET /api/v1/health and /api/v1/status meta endpoints.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.db.models import Match, ScrapeLog

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health():
    """Simple health check — returns 200 if the server is running."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)):
    """API status — last scrape time, match counts, scraper state."""
    # Last scrape
    last_scrape_stmt = (
        select(ScrapeLog)
        .where(ScrapeLog.success == True)  # noqa: E712
        .order_by(ScrapeLog.scraped_at.desc())
        .limit(1)
    )
    last_scrape_result = await db.execute(last_scrape_stmt)
    last_scrape = last_scrape_result.scalar_one_or_none()

    # Match counts by status
    counts_stmt = select(Match.status, func.count(Match.id)).group_by(Match.status)
    counts_result = await db.execute(counts_stmt)
    counts = {row[0]: row[1] for row in counts_result.all()}

    from app.scraper.scheduler import get_current_interval, scheduler

    return {
        "app_version": settings.app_version,
        "scraper_enabled": settings.scraper_enabled,
        "scraper_running": scheduler.running if settings.scraper_enabled else False,
        "poll_interval_seconds": get_current_interval(),
        "last_scraped_at": (
            last_scrape.scraped_at.isoformat() if last_scrape else None
        ),
        "matches_tracked": sum(counts.values()),
        "matches_by_status": counts,
        "sources_active": ["wikipedia"],
        "db_version": "1",
    }
