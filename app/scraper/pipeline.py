"""
Scrape pipeline — orchestrates scraping and writes results to the DB.

Called by the scheduler and admin manual-trigger endpoint.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models import Event, Match, Override, ScrapeLog, Standing, Lineup, MatchStat
from app.scraper.wikipedia import (
    ParsedMatch,
    ParsedMatchDetail,
    ParsedStanding,
    scrape_group_stage,
    scrape_match_detail,
    parse_standings_template,
    fetch_standings_template
)
from app.scraper.live_scraper import scrape_live_match
from app.services.webhooks import dispatch_webhook

logger = logging.getLogger(__name__)


async def run_scrape_pipeline() -> dict:
    """
    Full scrape pipeline:
    1. Fetch group stage summary → update match scores
    2. For each match in progress or recently finished → scrape individual page
    3. Persist to DB
    4. Log result to scrape_logs
    """
    pipeline_start = time.monotonic()
    total_changes = 0

    async with AsyncSessionLocal() as db:
        # --- Step 1: Group stage ---
        result = await scrape_group_stage(use_wc2022_for_testing=False)
        if result["error"]:
            await _log_scrape(db, "wikipedia", result.get("page", "group_stage"),
                              success=False, changes=0, error=result["error"])
            await db.commit()
            return {"changes": 0, "error": result["error"]}

        matches: list[ParsedMatch] = result["matches"]
        group_changes = await _upsert_matches(db, matches)
        total_changes += group_changes

        await _log_scrape(
            db, "wikipedia", result.get("page", "group_stage"),
            success=True, changes=group_changes,
            duration_ms=result.get("elapsed_ms")
        )

        # --- Step 1b: Knockout stage ---
        from app.scraper.wikipedia import fetch_wikitext, WC2026_KNOCKOUT_PAGE, parse_knockout_stage_wikitext
        ko_wikitext = await fetch_wikitext(WC2026_KNOCKOUT_PAGE)
        if ko_wikitext:
            ko_matches = parse_knockout_stage_wikitext(ko_wikitext)
            ko_changes = await _upsert_matches(db, ko_matches)
            total_changes += ko_changes
            await _log_scrape(
                db, "wikipedia", WC2026_KNOCKOUT_PAGE,
                success=True, changes=ko_changes
            )

        # --- Step 1c: Final match ---
        final_wikitext = await fetch_wikitext("2026_FIFA_World_Cup_final")
        if final_wikitext:
            final_matches = parse_knockout_stage_wikitext(final_wikitext)
            if final_matches:
                final_changes = await _upsert_matches(db, final_matches)
                total_changes += final_changes
                await _log_scrape(
                    db, "wikipedia", "2026_FIFA_World_Cup_final",
                    success=True, changes=final_changes
                )

        # --- Step 2: Individual match pages for live/recent matches ---
        # Get matches with a wikipedia_url that are live or finished recently
        # Get matches with a wikipedia_url that are live or finished recently
        # Prioritize live matches, then sort by kickoff
        stmt = select(Match).where(Match.status.in_(["live", "finished"])).order_by(Match.status.desc(), Match.kickoff_utc.desc())
        result_db = await db.execute(stmt)
        active_matches = result_db.scalars().all()

        for match in active_matches[:20]:  # cap at 20 per cycle to avoid rate limiting
            if not match.wikipedia_url:
                continue
            title = match.wikipedia_url  # stored as page title, not full URL

            # 1. Scrape Wikipedia for match detail (for goals fallback)
            detail_result = await scrape_match_detail(title)
            if detail_result["error"]:
                await _log_scrape(db, "wikipedia", title, success=False,
                                  changes=0, error=detail_result["error"])
                detail = ParsedMatchDetail()
            else:
                detail = detail_result["detail"]
                
            events_to_upsert = detail.events
            source_for_events = "wikipedia"

            # Overwrite Wikipedia data with ESPN live data if available
            fifa_match = await scrape_live_match(match.home_team, match.away_team, match.kickoff_utc)
            if fifa_match:
                # Hybrid Truth: Check for score conflict
                if fifa_match.home_score != match.home_score or fifa_match.away_score != match.away_score:
                    # Alert the admin!
                    logger.warning(f"CONFLICT DETECTED for {match.id}: Wiki({match.home_score}-{match.away_score}) vs FIFA({fifa_match.home_score}-{fifa_match.away_score})")
                    conflict_payload = {
                        "match_id": match.id,
                        "wikipedia_score": f"{match.home_score}-{match.away_score}",
                        "fifa_score": f"{fifa_match.home_score}-{fifa_match.away_score}",
                        "message": "Data source conflict detected. Check Admin UI."
                    }
                    await dispatch_webhook("system.conflict", conflict_payload)
                    await _log_scrape(db, "fifa_conflict", title, success=False, changes=0, error=f"Wiki({match.home_score}-{match.away_score}) != FIFA({fifa_match.home_score}-{fifa_match.away_score})")

                # UPDATE SCORES AND CLOCK FROM LIVE DATA
                if match.source != "override":
                    match.home_score = fifa_match.home_score
                    match.away_score = fifa_match.away_score
                    match.clock = fifa_match.clock

                # Trust FIFA for events
                events_to_upsert = fifa_match.events
                source_for_events = "fifa"

                # Phase 4: Upsert Lineups and Stats
                lineup_changes = await _upsert_lineups(db, match, fifa_match.lineups)
                stat_changes = await _upsert_stats(db, match, fifa_match.stats)
                total_changes += lineup_changes + stat_changes

            # 3. Upsert events into DB
            event_changes = await _upsert_events(db, match, events_to_upsert, source=source_for_events)
            total_changes += event_changes

            await _log_scrape(
                db, "wikipedia", title, success=True, changes=event_changes,
                duration_ms=detail_result.get("elapsed_ms")
            )

        # --- Step 3: Group standings ---
        standings_wt = await fetch_standings_template(2026) # fetch real 2026 data
        if standings_wt:
            parsed_standings = parse_standings_template(standings_wt)
            if parsed_standings:
                standings_changes = await _upsert_standings(db, parsed_standings)
                total_changes += standings_changes
                await _log_scrape(db, "wikipedia", "standings_template", success=True, changes=standings_changes)

        await db.commit()

    elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
    logger.info(
        "Pipeline complete: %d total changes in %dms", total_changes, elapsed_ms
    )
    return {"changes": total_changes, "elapsed_ms": elapsed_ms}


async def _upsert_matches(db: AsyncSession, parsed: list[ParsedMatch]) -> int:
    """Upsert match records from parsed group stage data. Returns count of changes."""
    changes = 0

    for pm in parsed:
        match_id = _make_match_id(pm)

        stmt = select(Match).where(Match.id == match_id)
        result = await db.execute(stmt)
        existing: Optional[Match] = result.scalar_one_or_none()

        if existing is None:
            # New match
            match = Match(
                id=match_id,
                home_team=pm.home_team,
                away_team=pm.away_team,
                home_team_code=_team_code(pm.home_team),
                away_team_code=_team_code(pm.away_team),
                kickoff_utc=pm.kickoff_utc or datetime(2026, 6, 11, tzinfo=timezone.utc),
                venue=pm.venue,
                group_name=pm.group_name,
                stage=pm.stage,
                status=pm.status,
                home_score=pm.home_score,
                away_score=pm.away_score,
                source="wikipedia",
                wikipedia_url=pm.wikipedia_title,
                last_scraped_at=datetime.now(timezone.utc),
            )
            db.add(match)
            changes += 1
            if pm.events:
                changes += await _upsert_events(db, match, pm.events)
        else:
            # Update if not overridden
            if existing.source != "override":
                updated = False
                
                if existing.kickoff_utc != pm.kickoff_utc and pm.kickoff_utc is not None:
                    existing.kickoff_utc = pm.kickoff_utc
                    updated = True

                if existing.stage != pm.stage:
                    existing.stage = pm.stage
                    updated = True

                score_changed = False
                if existing.home_score != pm.home_score:
                    existing.home_score = pm.home_score
                    updated = True
                    score_changed = True
                if existing.away_score != pm.away_score:
                    existing.away_score = pm.away_score
                    updated = True
                    score_changed = True
                    
                status_changed = False
                if existing.status != pm.status:
                    existing.status = pm.status
                    updated = True
                    status_changed = True

                if existing.wikipedia_url != pm.wikipedia_title:
                    existing.wikipedia_url = pm.wikipedia_title
                    updated = True
                    
                if updated:
                    existing.source = "wikipedia"
                    existing.last_scraped_at = datetime.now(timezone.utc)
                    changes += 1

                # Dispatch Webhooks
                if score_changed:
                    payload = {"match_id": match_id, "home_score": pm.home_score, "away_score": pm.away_score}
                    await dispatch_webhook("match.goal", payload)
                
                if status_changed:
                    payload = {"match_id": match_id, "status": pm.status}
                    if pm.status == "live":
                        await dispatch_webhook("match.started", payload)
                    elif pm.status == "finished":
                        await dispatch_webhook("match.finished", payload)
            
            if pm.events:
                changes += await _upsert_events(db, existing, pm.events)

    return changes


async def _upsert_events(db: AsyncSession, match: Match, events: list["ParsedEvent"], source: str = "wikipedia") -> int:
    """
    Replace non-overridden events for a match with freshly parsed ones.
    Returns count of changes.
    """
    if not events:
        return 0

    # Count existing non-overridden events
    stmt = select(Event).where(
        Event.match_id == match.id,
        Event.is_overridden == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    existing_events = result.scalars().all()
    old_count = len(existing_events)

    # Delete non-overridden events and re-insert
    delete_stmt = delete(Event).where(
        Event.match_id == match.id,
        Event.is_overridden == False,  # noqa: E712
    )
    await db.execute(delete_stmt)

    # Determine team codes for home/away
    home_code = match.home_team_code
    away_code = match.away_team_code

    for pe in events:
        # For FIFA mock, team_code might be set directly
        team_code = pe.team_code if getattr(pe, 'team_code', None) else (home_code if pe.team_side == "home" else away_code)
        event = Event(
            match_id=match.id,
            type=pe.type,
            player_name=pe.player_name,
            team_code=team_code,
            minute=pe.minute,
            extra_info=pe.extra_info,
            source=source,
            is_overridden=False,
        )
        db.add(event)

    new_count = len(events)
    return abs(new_count - old_count)


async def _upsert_lineups(db: AsyncSession, match: Match, lineups: list["ParsedLineup"]) -> int:
    """
    Replace all lineups for a match with freshly parsed ones.
    """
    if not lineups:
        return 0

    delete_stmt = delete(Lineup).where(Lineup.match_id == match.id)
    await db.execute(delete_stmt)

    home_code = match.home_team_code
    away_code = match.away_team_code

    for pl in lineups:
        team_code = home_code if pl.team_side == "home" else away_code
        lineup = Lineup(
            match_id=match.id,
            team_code=team_code,
            player_name=pl.player_name,
            position=pl.position,
            jersey_number=pl.jersey_number,
            is_starting=pl.is_starting,
        )
        db.add(lineup)

    return len(lineups)


async def _upsert_stats(db: AsyncSession, match: Match, stats: list["ParsedStat"]) -> int:
    """
    Replace all match stats for a match with freshly parsed ones.
    """
    if not stats:
        return 0

    delete_stmt = delete(MatchStat).where(MatchStat.match_id == match.id)
    await db.execute(delete_stmt)

    home_code = match.home_team_code
    away_code = match.away_team_code

    for ps in stats:
        team_code = home_code if ps.team_side == "home" else away_code
        stat = MatchStat(
            match_id=match.id,
            team_code=team_code,
            possession_pct=ps.possession_pct,
            shots=ps.shots,
            shots_on_target=ps.shots_on_target,
            corners=ps.corners,
            fouls=ps.fouls,
            yellow_cards=ps.yellow_cards,
            red_cards=ps.red_cards,
        )
        db.add(stat)

    return len(stats)


def _make_match_id(pm: ParsedMatch) -> str:
    """Generate a stable match ID from teams and group."""
    home = pm.home_team.lower().replace(" ", "_")
    away = pm.away_team.lower().replace(" ", "_")
    group = (pm.group_name or "unknown").lower().replace(" ", "_")
    return f"{group}_{home}_v_{away}"


def _team_code(team_name: str) -> Optional[str]:
    """
    Simple lookup for FIFA 3-letter country codes.
    Returns the string itself if it's already a 3-letter code.
    """
    if len(team_name) == 3 and team_name.isupper():
        return team_name

    CODES = {
        # Group A
        "United States": "USA", "Mexico": "MEX", "Canada": "CAN",
        # Group B
        "Argentina": "ARG", "Brazil": "BRA", "Chile": "CHI",
        # Common teams
        "France": "FRA", "Germany": "GER", "Spain": "ESP", "England": "ENG",
        "Portugal": "POR", "Netherlands": "NED", "Belgium": "BEL",
        "Italy": "ITA", "Croatia": "CRO", "Morocco": "MAR", "Senegal": "SEN",
        "Japan": "JPN", "South Korea": "KOR", "Australia": "AUS",
        "Saudi Arabia": "KSA", "Iran": "IRN", "Qatar": "QAT", "Ecuador": "ECU",
        "Uruguay": "URU", "Colombia": "COL", "Peru": "PER", "Poland": "POL",
        "Switzerland": "SUI", "Denmark": "DEN", "Serbia": "SRB",
        "Cameroon": "CMR", "Ghana": "GHA", "Tunisia": "TUN",
        "Costa Rica": "CRC", "Panama": "PAN", "Honduras": "HON",
        "Venezuela": "VEN", "Bolivia": "BOL", "Paraguay": "PAR",
        "New Zealand": "NZL", "Nigeria": "NGA", "Egypt": "EGY",
        "Algeria": "ALG", "Ivory Coast": "CIV", "Mali": "MLI",
    }
    return CODES.get(team_name) or team_name[:3].upper()


async def _log_scrape(
    db: AsyncSession,
    source: str,
    page: str,
    success: bool,
    changes: int,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> None:
    """Insert a scrape log entry."""
    log = ScrapeLog(
        source=source,
        page=page,
        success=success,
        changes_detected=changes,
        error_message=error,
        duration_ms=duration_ms,
    )
    db.add(log)


async def _upsert_standings(db: AsyncSession, parsed: list[ParsedStanding]) -> int:
    await db.execute(delete(Standing))
    for ps in parsed:
        s = Standing(
            group_name=ps.group_name,
            position=ps.position,
            team_name=ps.team_name,
            team_code=ps.team_code,
            played=ps.played,
            won=ps.won,
            drawn=ps.drawn,
            lost=ps.lost,
            goals_for=ps.goals_for,
            goals_against=ps.goals_against,
            goal_diff=ps.goal_diff,
            points=ps.points,
            updated_at=datetime.now(timezone.utc)
        )
        db.add(s)
    return len(parsed)
