"""
APScheduler setup with adaptive poll intervals.

Intervals:
  - 60s  during live match windows (kickoff ± 2 hours)
  - 300s between matches (no live games)
  - 900s overnight UTC 00:00–08:00
"""
import logging
from datetime import datetime, time, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_current_interval: int = settings.poll_interval_idle


def get_current_interval() -> int:
    """Return the current poll interval in seconds."""
    return _current_interval


def _is_night_utc() -> bool:
    """Returns True during UTC 00:00–08:00 (no WC matches)."""
    now_utc = datetime.now(timezone.utc).time()
    return time(0, 0) <= now_utc < time(8, 0)


async def _determine_interval() -> int:
    """
    Determine the appropriate poll interval based on live matches.
    """
    if _is_night_utc():
        return settings.poll_interval_night
        
    from app.db.database import AsyncSessionLocal
    from app.db.models import Match
    from sqlalchemy import select
    
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Match).where(Match.status == "live")
            result = await session.execute(stmt)
            if result.scalars().first():
                return settings.poll_interval_live
    except Exception as e:
        logger.error("Failed to check for live matches: %s", e)
        
    return settings.poll_interval_idle


async def _scrape_job() -> None:
    """Main scrape job executed by the scheduler."""
    from app.scraper.pipeline import run_scrape_pipeline

    try:
        await run_scrape_pipeline()
    except Exception as exc:
        logger.error("Scrape job failed: %s", exc, exc_info=True)

    # Reschedule with potentially updated interval
    new_interval = await _determine_interval()
    global _current_interval
    if new_interval != _current_interval:
        _current_interval = new_interval
        logger.info("Adjusting poll interval to %ds", new_interval)
        job = scheduler.get_job("scrape_job")
        if job:
            job.reschedule(trigger=IntervalTrigger(seconds=new_interval, jitter=10))


async def _soccerdata_scrape_job() -> None:
    """Soccerdata (FBref/Sofascore) scrape job executed every 3-4 hours."""
    from app.scraper.soccerdata_scraper import run_fbref_scraper
    try:
        await run_fbref_scraper()
    except Exception as exc:
        logger.error("Soccerdata scrape job failed: %s", exc, exc_info=True)


async def start_scheduler() -> None:
    """Start the APScheduler. Called from FastAPI lifespan."""
    if not settings.scraper_enabled:
        logger.info("Scraper is disabled (SCRAPER_ENABLED=false). Scheduler not started.")
        return

    initial_interval = await _determine_interval()
    global _current_interval
    _current_interval = initial_interval

    scheduler.add_job(
        _scrape_job,
        trigger=IntervalTrigger(seconds=initial_interval, jitter=10),
        id="scrape_job",
        name="Wikipedia Group Stage Scraper",
        replace_existing=True,
        max_instances=1,  # prevent overlapping runs
    )
    
    # 10800 seconds = 3 hours
    # DISABLED: soccerdata/FBref requires headless chrome and causes OOM kill on Fly.io's 256MB instances
    # scheduler.add_job(
    #     _soccerdata_scrape_job,
    #     trigger=IntervalTrigger(seconds=10800),
    #     id="soccerdata_scrape_job",
    #     name="Soccerdata Post-Match Scraper",
    #     replace_existing=True,
    #     max_instances=1,
    #     next_run_time=datetime.now(),
    # )
    

    scheduler.start()
    logger.info("Scheduler started. Initial poll interval: %ds", initial_interval)


def stop_scheduler() -> None:
    """Stop the scheduler. Called from FastAPI lifespan shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


async def trigger_manual_scrape() -> dict:
    """Trigger an immediate scrape and return the result."""
    from app.scraper.pipeline import run_scrape_pipeline

    try:
        result = await run_scrape_pipeline()
        return {"success": True, "result": result}
    except Exception as exc:
        logger.error("Manual scrape failed: %s", exc, exc_info=True)
        return {"success": False, "error": str(exc)}


async def set_scraper_enabled(enabled: bool) -> None:
    """Enable or disable the scraper at runtime."""
    settings.scraper_enabled = enabled
    if enabled and not scheduler.running:
        await start_scheduler()
    elif not enabled and scheduler.running:
        stop_scheduler()
