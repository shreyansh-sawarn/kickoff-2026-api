"""
GET /api/v1/events endpoint.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Event

router = APIRouter(prefix="/events", tags=["events"])


def _event_to_dict(e: Event) -> dict:
    return {
        "id": e.id,
        "match_id": e.match_id,
        "type": e.type,
        "player_name": e.player_name,
        "team_code": e.team_code,
        "minute": e.minute,
        "extra_info": e.extra_info,
        "source": e.source,
        "is_overridden": e.is_overridden,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.get("/")
async def list_events(
    match_id: Optional[str] = Query(None),
    type: Optional[str] = Query(None, description="goal|own_goal|penalty|yellow|red|assist|sub"),
    team: Optional[str] = Query(None, description="3-letter team code"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List match events with optional filters."""
    stmt = select(Event).order_by(Event.minute)

    if match_id:
        stmt = stmt.where(Event.match_id == match_id)
    if type:
        stmt = stmt.where(Event.type == type)
    if team:
        stmt = stmt.where(Event.team_code == team.upper())

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()
    return {"count": len(events), "events": [_event_to_dict(e) for e in events]}
