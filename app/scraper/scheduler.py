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


def _determine_interval() -> int:
    """
    Determine the appropriate poll interval.

    TODO Phase 2: check DB for currently live matches to use 60s interval.
    For now: use night vs idle as a simple heuristic.
    """
    if _is_night_utc():
        return settings.poll_interval_night
    return settings.poll_interval_idle


async def _scrape_job() -> None:
    """Main scrape job executed by the scheduler."""
    from app.scraper.pipeline import run_scrape_pipeline

    try:
        await run_scrape_pipeline()
    except Exception as exc:
        logger.error("Scrape job failed: %s", exc, exc_info=True)

    # Reschedule with potentially updated interval
    new_interval = _determine_interval()
    global _current_interval
    if new_interval != _current_interval:
        _current_interval = new_interval
        logger.info("Adjusting poll interval to %ds", new_interval)
        job = scheduler.get_job("scrape_job")
        if job:
            job.reschedule(trigger=IntervalTrigger(seconds=new_interval))


def start_scheduler() -> None:
    """Start the APScheduler. Called from FastAPI lifespan."""
    if not settings.scraper_enabled:
        logger.info("Scraper is disabled (SCRAPER_ENABLED=false). Scheduler not started.")
        return

    initial_interval = _determine_interval()
    global _current_interval
    _current_interval = initial_interval

    scheduler.add_job(
        _scrape_job,
        trigger=IntervalTrigger(seconds=initial_interval),
        id="scrape_job",
        name="Wikipedia Group Stage Scraper",
        replace_existing=True,
        max_instances=1,  # prevent overlapping runs
    )
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


def set_scraper_enabled(enabled: bool) -> None:
    """Enable or disable the scraper at runtime."""
    settings.scraper_enabled = enabled
    if enabled and not scheduler.running:
        start_scheduler()
    elif not enabled and scheduler.running:
        stop_scheduler()
