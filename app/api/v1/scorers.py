"""
GET /api/v1/scorers, /assists, /yellow-cards, /red-cards endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Event

router = APIRouter(tags=["leaderboards"])


async def _aggregate_events(
    db: AsyncSession,
    event_types: list[str],
    limit: int,
    team: Optional[str] = None,
) -> list[dict]:
    """Aggregate events by player, returning ranked list."""
    stmt = (
        select(
            Event.player_name,
            Event.team_code,
            func.count(Event.id).label("count"),
        )
        .where(Event.type.in_(event_types))
        .where(Event.player_name != None)  # noqa: E711
        .where(Event.player_name != "")
        .group_by(Event.player_name, Event.team_code)
        .order_by(func.count(Event.id).desc())
        .limit(limit)
    )

    if team:
        stmt = stmt.where(Event.team_code == team.upper())

    result = await db.execute(stmt)
    rows = result.all()
    return [
        {"rank": i + 1, "player_name": r.player_name, "team_code": r.team_code, "count": r.count}
        for i, r in enumerate(rows)
    ]


@router.get("/scorers")
async def top_scorers(
    limit: int = Query(20, ge=1, le=100),
    team: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Top goal scorers (goals + penalties, excluding own goals)."""
    rows = await _aggregate_events(db, ["goal", "penalty"], limit, team)
    return {"count": len(rows), "scorers": rows}


@router.get("/assists")
async def top_assists(
    limit: int = Query(20, ge=1, le=100),
    team: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Top assist providers."""
    rows = await _aggregate_events(db, ["assist"], limit, team)
    return {"count": len(rows), "assists": rows}


@router.get("/yellow-cards")
async def yellow_cards(
    limit: int = Query(20, ge=1, le=100),
    team: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Players with most yellow cards."""
    rows = await _aggregate_events(db, ["yellow", "yellow_red"], limit, team)
    return {"count": len(rows), "yellow_cards": rows}


@router.get("/red-cards")
async def red_cards(
    limit: int = Query(20, ge=1, le=100),
    team: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Players with red cards (straight red or second yellow)."""
    rows = await _aggregate_events(db, ["red", "yellow_red"], limit, team)
    return {"count": len(rows), "red_cards": rows}
