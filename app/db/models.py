"""
SQLAlchemy ORM models for all database tables.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "group_a_match_1"
    home_team: Mapped[str] = mapped_column(String, nullable=False)
    away_team: Mapped[str] = mapped_column(String, nullable=False)
    home_team_code: Mapped[Optional[str]] = mapped_column(String(3))  # e.g. "USA"
    away_team_code: Mapped[Optional[str]] = mapped_column(String(3))  # e.g. "MEX"
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    venue: Mapped[Optional[str]] = mapped_column(String)
    group_name: Mapped[Optional[str]] = mapped_column(String)  # "Group A", "Round of 32"
    stage: Mapped[Optional[str]] = mapped_column(String)  # group|r32|r16|qf|sf|final
    status: Mapped[str] = mapped_column(String, default="scheduled")  # scheduled|live|finished
    home_score: Mapped[Optional[int]] = mapped_column(Integer)
    away_score: Mapped[Optional[int]] = mapped_column(Integer)
    home_score_ht: Mapped[Optional[int]] = mapped_column(Integer)
    away_score_ht: Mapped[Optional[int]] = mapped_column(Integer)
    clock: Mapped[Optional[str]] = mapped_column(String)  # Live match clock (e.g. 34', HT, FT)
    source: Mapped[Optional[str]] = mapped_column(String)  # wikipedia|fifa|override
    wikipedia_url: Mapped[Optional[str]] = mapped_column(Text)
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    home_formation: Mapped[Optional[str]] = mapped_column(String)
    away_formation: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    events: Mapped[list["Event"]] = relationship(
        "Event", back_populates="match", cascade="all, delete-orphan"
    )
    lineups: Mapped[list["Lineup"]] = relationship(
        "Lineup", back_populates="match", cascade="all, delete-orphan"
    )
    stats: Mapped[list["MatchStat"]] = relationship(
        "MatchStat", back_populates="match", cascade="all, delete-orphan"
    )


class Lineup(Base):
    __tablename__ = "lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(String, ForeignKey("matches.id"), nullable=False)
    team_code: Mapped[str] = mapped_column(String(3), nullable=False)
    player_name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[Optional[str]] = mapped_column(String)  # e.g., "GK", "DEF", "MID", "FWD"
    jersey_number: Mapped[Optional[int]] = mapped_column(Integer)
    is_starting: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    match: Mapped["Match"] = relationship("Match", back_populates="lineups")


class MatchStat(Base):
    __tablename__ = "match_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(String, ForeignKey("matches.id"), nullable=False)
    team_code: Mapped[str] = mapped_column(String(3), nullable=False)
    possession_pct: Mapped[Optional[int]] = mapped_column(Integer)
    shots: Mapped[Optional[int]] = mapped_column(Integer)
    shots_on_target: Mapped[Optional[int]] = mapped_column(Integer)
    corners: Mapped[Optional[int]] = mapped_column(Integer)
    fouls: Mapped[Optional[int]] = mapped_column(Integer)
    yellow_cards: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    red_cards: Mapped[Optional[int]] = mapped_column(Integer, default=0)

    # Relationships
    match: Mapped["Match"] = relationship("Match", back_populates="stats")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(String, ForeignKey("matches.id"), nullable=False)
    type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # goal|own_goal|penalty|yellow|red|yellow_red|assist|sub
    player_name: Mapped[Optional[str]] = mapped_column(String)
    team_code: Mapped[Optional[str]] = mapped_column(String(3))
    minute: Mapped[Optional[int]] = mapped_column(Integer)  # 90+3 stored as 93
    extra_info: Mapped[Optional[str]] = mapped_column(Text)  # e.g. "penalty", assisting player
    source: Mapped[Optional[str]] = mapped_column(String)  # wikipedia|fifa|override
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    match: Mapped["Match"] = relationship("Match", back_populates="events")


class Standing(Base):
    __tablename__ = "standings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_name: Mapped[str] = mapped_column(String, nullable=False)  # "Group A" through "Group L"
    team_name: Mapped[str] = mapped_column(String, nullable=False)
    team_code: Mapped[Optional[str]] = mapped_column(String(3))
    played: Mapped[int] = mapped_column(Integer, default=0)
    won: Mapped[int] = mapped_column(Integer, default=0)
    drawn: Mapped[int] = mapped_column(Integer, default=0)
    lost: Mapped[int] = mapped_column(Integer, default=0)
    goals_for: Mapped[int] = mapped_column(Integer, default=0)
    goals_against: Mapped[int] = mapped_column(Integer, default=0)
    goal_diff: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[Optional[int]] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Override(Base):
    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String)  # match|event|standings
    entity_id: Mapped[Optional[str]] = mapped_column(String)
    field_name: Mapped[Optional[str]] = mapped_column(String)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    applied_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[Optional[str]] = mapped_column(String)  # HMAC signing secret
    events: Mapped[Optional[str]] = mapped_column(Text)  # JSON array: ["goal","red_card"]
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # SHA256 hash
    owner_name: Mapped[Optional[str]] = mapped_column(String)
    owner_email: Mapped[Optional[str]] = mapped_column(String)
    plan: Mapped[str] = mapped_column(String, default="free")  # free|pro
    requests_today: Mapped[int] = mapped_column(Integer, default=0)
    daily_limit: Mapped[int] = mapped_column(Integer, default=1000)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ScrapeLog(Base):
    """Tracks scraper runs for the admin UI."""

    __tablename__ = "scrape_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String)  # wikipedia|fifa
    page: Mapped[Optional[str]] = mapped_column(String)  # which page was scraped
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    changes_detected: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PlayerStatistic(Base):
    """Stores individual player statistics scraped from external sources like FBref."""

    __tablename__ = "player_statistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_name: Mapped[str] = mapped_column(String, nullable=False)
    team_code: Mapped[Optional[str]] = mapped_column(String(3))
    minutes_played: Mapped[int] = mapped_column(Integer, default=0)
    fbref_url: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
