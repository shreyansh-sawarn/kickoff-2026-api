"""
GET /api/v1/matches endpoints.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models import Event, Match, Lineup, MatchStat

router = APIRouter(prefix="/matches", tags=["matches"])


def _match_to_dict(match: Match, include_events: bool = False) -> dict:
    d = {
        "id": match.id,
        "home_team": match.home_team,
        "away_team": match.away_team,
        "home_team_code": match.home_team_code,
        "away_team_code": match.away_team_code,
        "kickoff_utc": match.kickoff_utc.isoformat() if match.kickoff_utc else None,
        "venue": match.venue,
        "group_name": match.group_name,
        "stage": match.stage,
        "status": match.status,
        "clock": match.clock,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "home_score_ht": match.home_score_ht,
        "away_score_ht": match.away_score_ht,
        "source": match.source,
        "last_scraped_at": match.last_scraped_at.isoformat() if match.last_scraped_at else None,
    }
    if include_events:
        unique_events = {}
        for e in match.events:
            key = (e.type, e.minute, e.player_name, e.team_code)
            if key in unique_events:
                existing = unique_events[key]
                if e.is_overridden and not existing.is_overridden:
                    unique_events[key] = e
                elif not existing.is_overridden and e.extra_info and not existing.extra_info:
                    unique_events[key] = e
            else:
                unique_events[key] = e
                
        d["events"] = [_event_to_dict(e) for e in sorted(unique_events.values(), key=lambda e: e.minute or 0)]
    return d


def _event_to_dict(event: Event) -> dict:
    return {
        "id": event.id,
        "match_id": event.match_id,
        "type": event.type,
        "player_name": event.player_name,
        "team_code": event.team_code,
        "minute": event.minute,
        "extra_info": event.extra_info,
        "source": event.source,
        "is_overridden": event.is_overridden,
    }


def _lineup_to_dict(lineup: Lineup) -> dict:
    return {
        "player_name": lineup.player_name,
        "team_code": lineup.team_code,
        "position": lineup.position,
        "jersey_number": lineup.jersey_number,
        "is_starting": lineup.is_starting,
    }

def _stat_to_dict(stat: MatchStat) -> dict:
    return {
        "team_code": stat.team_code,
        "possession_pct": stat.possession_pct,
        "shots": stat.shots,
        "shots_on_target": stat.shots_on_target,
        "corners": stat.corners,
        "fouls": stat.fouls,
        "yellow_cards": stat.yellow_cards,
        "red_cards": stat.red_cards,
        "yellowCards": stat.yellow_cards,
        "redCards": stat.red_cards,
    }

@router.get("/")
async def list_matches(
    status: Optional[str] = Query(None, description="scheduled | live | finished"),
    group: Optional[str] = Query(None, description="Group letter, e.g. A"),
    stage: Optional[str] = Query(None, description="group | r32 | r16 | qf | sf | final"),
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """List all matches with optional filters."""
    stmt = select(Match)

    if status:
        stmt = stmt.where(Match.status == status)
    if group:
        group_name = f"Group {group.upper()}"
        stmt = stmt.where(Match.group_name == group_name)
    if stage:
        stmt = stmt.where(Match.stage == stage)
    if date:
        try:
            d = date  # YYYY-MM-DD string — filter by date portion of kickoff_utc
            stmt = stmt.where(Match.kickoff_utc.cast(str).startswith(d))
        except Exception:
            pass

    stmt = stmt.order_by(Match.kickoff_utc).options(selectinload(Match.events))
    result = await db.execute(stmt)
    matches = result.scalars().all()
    return {"count": len(matches), "matches": [_match_to_dict(m, include_events=True) for m in matches]}


@router.get("/live")
async def live_matches(db: AsyncSession = Depends(get_db)):
    """Return currently live matches."""
    stmt = select(Match).where(Match.status == "live").order_by(Match.kickoff_utc).options(selectinload(Match.events))
    result = await db.execute(stmt)
    matches = result.scalars().all()
    return {"count": len(matches), "matches": [_match_to_dict(m, include_events=True) for m in matches]}


@router.get("/{match_id}")
async def get_match(match_id: str, db: AsyncSession = Depends(get_db)):
    """Get full match detail including events."""
    stmt = (
        select(Match)
        .options(selectinload(Match.events))
        .where(Match.id == match_id)
    )
    result = await db.execute(stmt)
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail=f"Match '{match_id}' not found")
    return _match_to_dict(match, include_events=True)


@router.get("/{match_id}/lineups")
async def get_match_lineups(match_id: str, db: AsyncSession = Depends(get_db)):
    """Get starting XI and substitutes for a match."""
    stmt = select(Lineup).where(Lineup.match_id == match_id)
    result = await db.execute(stmt)
    lineups = result.scalars().all()
    if not lineups:
        raise HTTPException(status_code=404, detail=f"Lineups not found for match '{match_id}'")
    
    return {"match_id": match_id, "lineups": [_lineup_to_dict(l) for l in lineups]}


@router.get("/{match_id}/stats")
async def get_match_stats(match_id: str, db: AsyncSession = Depends(get_db)):
    """Get team-level match statistics."""
    stmt = select(MatchStat).where(MatchStat.match_id == match_id)
    result = await db.execute(stmt)
    stats = result.scalars().all()
    if not stats:
        raise HTTPException(status_code=404, detail=f"Stats not found for match '{match_id}'")
    
    return {"match_id": match_id, "stats": [_stat_to_dict(s) for s in stats]}

