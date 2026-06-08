"""
Admin UI routes — password-protected HTML interface.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.db.models import Event, Match, Override, ScrapeLog, Standing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Use absolute path so the template dir works regardless of working directory
_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _check_auth(request: Request) -> bool:
    return bool(request.session.get("admin_authenticated"))


def _require_auth(request: Request):
    """Redirect to login if not authenticated."""
    if not _check_auth(request):
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/admin/login"},
        )


def _resp(template_name: str, request: Request, context: dict):
    """
    Helper to call TemplateResponse in a way compatible with Starlette 1.x+.
    In Starlette >= 1.0, request is a keyword arg and must NOT be in the context dict.
    Injects current_path for sidebar active-link detection.
    """
    context.setdefault("current_path", request.url.path)
    return templates.TemplateResponse(
        name=template_name,
        request=request,
        context=context,
    )


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _check_auth(request):
        return RedirectResponse("/admin/", status_code=302)
    return _resp("login.html", request, {"error": None})


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == settings.admin_password:
        request.session["admin_authenticated"] = True
        return RedirectResponse("/admin/", status_code=302)
    return _resp("login.html", request, {"error": "Invalid password"})


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    _require_auth(request)

    from sqlalchemy import func

    counts_stmt = select(Match.status, func.count(Match.id)).group_by(Match.status)
    counts_result = await db.execute(counts_stmt)
    match_counts = {row[0]: row[1] for row in counts_result.all()}

    logs_stmt = select(ScrapeLog).order_by(desc(ScrapeLog.scraped_at)).limit(10)
    logs_result = await db.execute(logs_stmt)
    recent_logs = logs_result.scalars().all()

    last_ok_stmt = (
        select(ScrapeLog)
        .where(ScrapeLog.success == True)  # noqa: E712
        .order_by(desc(ScrapeLog.scraped_at))
        .limit(1)
    )
    last_ok_result = await db.execute(last_ok_stmt)
    last_ok_log = last_ok_result.scalar_one_or_none()

    from app.scraper.scheduler import get_current_interval, scheduler

    return _resp("dashboard.html", request, {
        "match_counts": match_counts,
        "recent_logs": recent_logs,
        "last_scraped_at": last_ok_log.scraped_at if last_ok_log else None,
        "scraper_running": scheduler.running if settings.scraper_enabled else False,
        "poll_interval": get_current_interval(),
    })


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------


@router.get("/matches", response_class=HTMLResponse)
async def match_list(request: Request, db: AsyncSession = Depends(get_db)):
    _require_auth(request)
    stmt = select(Match).order_by(Match.kickoff_utc)
    result = await db.execute(stmt)
    matches = result.scalars().all()
    return _resp("match_list.html", request, {"matches": matches})


@router.get("/matches/{match_id}", response_class=HTMLResponse)
async def match_detail(match_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    _require_auth(request)
    stmt = (
        select(Match)
        .options(selectinload(Match.events))
        .where(Match.id == match_id)
    )
    result = await db.execute(stmt)
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    overrides_stmt = select(Override).where(Override.entity_id == match_id).order_by(
        desc(Override.applied_at)
    )
    overrides_result = await db.execute(overrides_stmt)
    overrides = overrides_result.scalars().all()

    return _resp("match_detail.html", request, {
        "match": match,
        "events": sorted(match.events, key=lambda e: e.minute or 0),
        "overrides": overrides,
    })


@router.post("/matches/{match_id}/override")
async def match_override(
    match_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    home_score: Optional[int] = Form(None),
    away_score: Optional[int] = Form(None),
    home_score_ht: Optional[int] = Form(None),
    away_score_ht: Optional[int] = Form(None),
    match_status: Optional[str] = Form(None),
    reason: Optional[str] = Form(None),
):
    _require_auth(request)

    stmt = select(Match).where(Match.id == match_id)
    result = await db.execute(stmt)
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    fields_updated = []

    if home_score is not None and match.home_score != home_score:
        db.add(Override(
            entity_type="match", entity_id=match_id, field_name="home_score",
            old_value=str(match.home_score), new_value=str(home_score), reason=reason,
        ))
        match.home_score = home_score
        fields_updated.append("home_score")

    if away_score is not None and match.away_score != away_score:
        db.add(Override(
            entity_type="match", entity_id=match_id, field_name="away_score",
            old_value=str(match.away_score), new_value=str(away_score), reason=reason,
        ))
        match.away_score = away_score
        fields_updated.append("away_score")

    if home_score_ht is not None and match.home_score_ht != home_score_ht:
        match.home_score_ht = home_score_ht
        fields_updated.append("home_score_ht")

    if away_score_ht is not None and match.away_score_ht != away_score_ht:
        match.away_score_ht = away_score_ht
        fields_updated.append("away_score_ht")

    if match_status and match.status != match_status:
        db.add(Override(
            entity_type="match", entity_id=match_id, field_name="status",
            old_value=match.status, new_value=match_status, reason=reason,
        ))
        match.status = match_status
        fields_updated.append("status")

    if fields_updated:
        match.source = "override"
        await db.commit()
        logger.info("Override applied to match %s: %s", match_id, fields_updated)

    return RedirectResponse(f"/admin/matches/{match_id}", status_code=302)


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------


@router.get("/standings", response_class=HTMLResponse)
async def standings_page(request: Request, db: AsyncSession = Depends(get_db)):
    _require_auth(request)
    stmt = select(Standing).order_by(Standing.group_name, Standing.position)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    groups: dict = {}
    for row in rows:
        gname = row.group_name
        if gname not in groups:
            groups[gname] = []
        groups[gname].append(row)

    return _resp("standings.html", request, {"groups": groups})


# ---------------------------------------------------------------------------
# Scraper controls
# ---------------------------------------------------------------------------


@router.get("/scrapers", response_class=HTMLResponse)
async def scrapers_page(request: Request, db: AsyncSession = Depends(get_db)):
    _require_auth(request)

    logs_stmt = select(ScrapeLog).order_by(desc(ScrapeLog.scraped_at)).limit(50)
    logs_result = await db.execute(logs_stmt)
    logs = logs_result.scalars().all()

    from app.scraper.scheduler import get_current_interval, scheduler

    return _resp("scrapers.html", request, {
        "logs": logs,
        "scraper_enabled": settings.scraper_enabled,
        "scraper_running": scheduler.running if settings.scraper_enabled else False,
        "poll_interval": get_current_interval(),
    })


@router.post("/scrapers/trigger")
async def trigger_scrape(request: Request):
    _require_auth(request)
    from app.scraper.scheduler import trigger_manual_scrape

    await trigger_manual_scrape()
    return RedirectResponse("/admin/scrapers", status_code=302)


@router.post("/scrapers/toggle")
async def toggle_scraper(request: Request):
    _require_auth(request)
    from app.scraper.scheduler import set_scraper_enabled

    new_state = not settings.scraper_enabled
    set_scraper_enabled(new_state)
    return RedirectResponse("/admin/scrapers", status_code=302)
