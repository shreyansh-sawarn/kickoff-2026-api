"""
GET /api/v1/standings endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Standing

router = APIRouter(prefix="/standings", tags=["standings"])


def _standing_to_dict(s: Standing) -> dict:
    return {
        "position": s.position,
        "team_name": s.team_name,
        "team_code": s.team_code,
        "played": s.played,
        "won": s.won,
        "drawn": s.drawn,
        "lost": s.lost,
        "goals_for": s.goals_for,
        "goals_against": s.goals_against,
        "goal_diff": s.goal_diff,
        "points": s.points,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("/")
async def all_standings(db: AsyncSession = Depends(get_db)):
    """Return standings for all groups."""
    stmt = select(Standing).order_by(Standing.group_name, Standing.position)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    # Group by group_name
    groups: dict = {}
    for row in rows:
        gname = row.group_name
        if gname not in groups:
            groups[gname] = []
        groups[gname].append(_standing_to_dict(row))

    return {"groups": groups}


@router.get("/{group}")
async def group_standings(group: str, db: AsyncSession = Depends(get_db)):
    """Return standings for a specific group (e.g. /standings/A)."""
    group_name = f"Group {group.upper()}"
    stmt = (
        select(Standing)
        .where(Standing.group_name == group_name)
        .order_by(Standing.position)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No standings found for {group_name}")

    return {
        "group": group_name,
        "standings": [_standing_to_dict(r) for r in rows],
    }
