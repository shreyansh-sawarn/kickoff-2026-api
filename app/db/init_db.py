"""
Database initialization — creates all tables on first run.
"""
import logging
from pathlib import Path

from app.db.database import Base, engine

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    # Ensure the data directory exists (for SQLite)
    from app.config import settings

    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "").replace("./", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    from sqlalchemy import text

    async with engine.begin() as conn:
        # Import models so they're registered with Base.metadata
        import app.db.models  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)

        # Force re-scraping of completed knockout matches that went to a shootout
        # if they don't have any shootout penalty events recorded yet.
        # This will trigger a re-scrape on deployment to backfill missing shootout data.
        await conn.execute(
            text(
                "UPDATE matches SET last_scraped_at = NULL "
                "WHERE status = 'finished' AND home_score = away_score AND stage != 'group' "
                "AND id NOT IN (SELECT DISTINCT match_id FROM events WHERE type = 'shootout_penalty')"
            )
        )

    logger.info("Database tables created / verified.")
