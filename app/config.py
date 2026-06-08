"""
Application configuration loaded from environment variables / .env file.
"""
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv
import os

# Load .env from project root (two levels up from this file)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)


class Settings:
    """All application settings read from environment variables."""

    # Admin UI
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin")

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./data/wc26.db"
    )

    # Scraper
    scraper_enabled: bool = os.getenv("SCRAPER_ENABLED", "true").lower() == "true"
    poll_interval_live: int = int(os.getenv("POLL_INTERVAL_LIVE_SECONDS", "60"))
    poll_interval_idle: int = int(os.getenv("POLL_INTERVAL_IDLE_SECONDS", "300"))
    poll_interval_night: int = int(os.getenv("POLL_INTERVAL_NIGHT_SECONDS", "900"))
    wikipedia_user_agent: str = os.getenv(
        "WIKIPEDIA_USER_AGENT",
        "kickoff-2026-api/1.0 (contact@example.com)",
    )

    # CORS
    cors_origins: List[str] = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://localhost:3001"
        ).split(",")
        if o.strip()
    ]

    # Auth
    require_api_key: bool = os.getenv("REQUIRE_API_KEY", "false").lower() == "true"
    session_secret: str = os.getenv("SESSION_SECRET", "dev_secret_change_in_prod")

    # Webhooks
    webhook_signing_secret: str = os.getenv("WEBHOOK_SIGNING_SECRET", "")

    # Sentry
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")

    # App metadata
    app_name: str = "kickoff-2026-api"
    app_version: str = "0.1.0"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
