import logging
import asyncio
import pandas as pd
import soccerdata as sd
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models import Match, Event, Lineup, MatchStat

logger = logging.getLogger(__name__)

def _sync_fetch_single_match_data():
    """Fetches events and lineups for a single highly-detailed match from 2022 World Cup."""
    fbref = sd.FBref(leagues="INT-World Cup", seasons=2022)
    sched = fbref.read_schedule()
    
    # Grab the very last match (The Final)
    game_id = sched['game_id'].iloc[-1]
    
    events = fbref.read_events(match_id=game_id)
    lineups = fbref.read_lineup(match_id=game_id)
    return events, lineups

async def inject_mock_match_data_for_2026(session: AsyncSession):
    try:
        events_df, lineups_df = await asyncio.to_thread(_sync_fetch_single_match_data)
        
        # Get all 2026 matches with eager loading
        stmt = select(Match).options(
            selectinload(Match.events),
            selectinload(Match.lineups),
            selectinload(Match.stats)
        )
        result = await session.execute(stmt)
        all_matches = result.scalars().all()
        
        if not all_matches:
            logger.info("No matches found in database to populate.")
            return False
            
        records_updated = 0
        import random
        
        for m in all_matches:
            # Delete existing relations to avoid duplicates
            await session.execute(delete(Event).where(Event.match_id == m.id))
            await session.execute(delete(Lineup).where(Lineup.match_id == m.id))
            await session.execute(delete(MatchStat).where(MatchStat.match_id == m.id))
            
            # Figure out the actual 2022 team names from the DataFrame
            unique_teams = list(lineups_df['team'].unique()) if 'team' in lineups_df.columns else []
            home_2022_team = unique_teams[0] if len(unique_teams) > 0 else "Team1"
            
            # --- MAP LINEUPS ---
            for idx, row in lineups_df.iterrows():
                team = str(row.get('team', ''))
                t_code = m.home_team_code if team == home_2022_team else m.away_team_code
                
                pos = row.get('position', 'MID')
                if pd.isna(pos): pos = 'MID'
                
                jersey_str = row.get('jersey_number')
                jersey = int(jersey_str) if not pd.isna(jersey_str) else 0
                
                is_starting = bool(row.get('is_starter', False))
                
                lineup_entry = Lineup(
                    match_id=m.id,
                    team_code=t_code or team[:3].upper(),
                    player_name=str(row.get('player', 'Unknown')),
                    position=str(pos),
                    jersey_number=jersey,
                    is_starting=is_starting
                )
                m.lineups.append(lineup_entry)
                records_updated += 1
                
            # --- MOCK MATCH STATS ---
            stat_entry_home = MatchStat(
                match_id=m.id,
                team_code=m.home_team_code or "HOM",
                possession_pct=random.randint(35, 65),
                shots=random.randint(5, 20),
                shots_on_target=random.randint(2, 8),
                corners=random.randint(1, 10),
                fouls=random.randint(5, 15)
            )
            m.stats.append(stat_entry_home)
            
            stat_entry_away = MatchStat(
                match_id=m.id,
                team_code=m.away_team_code or "AWA",
                possession_pct=100 - stat_entry_home.possession_pct,
                shots=random.randint(5, 20),
                shots_on_target=random.randint(2, 8),
                corners=random.randint(1, 10),
                fouls=random.randint(5, 15)
            )
            m.stats.append(stat_entry_away)
            records_updated += 2
                
            # --- MAP EVENTS ---
            for idx, row in events_df.iterrows():
                evt_type_raw = str(row.get('event_type', '')).lower()
                
                # Default type is goal
                evt_type = "goal"
                if "yellow" in evt_type_raw: evt_type = "yellow"
                elif "red" in evt_type_raw: evt_type = "red"
                elif "sub" in evt_type_raw: evt_type = "sub"
                elif "own_goal" in evt_type_raw: evt_type = "own_goal"
                elif "miss" in evt_type_raw: continue # Don't record missed penalties
                
                minute = row.get('minute')
                minute_val = 0
                if minute:
                    import re
                    match = re.search(r'\d+', str(minute))
                    if match:
                        minute_val = int(match.group())
                        
                # Fix penalty shootout minutes
                if "shootout" in evt_type_raw:
                    minute_val += 120
                    
                player_name = str(row.get('player1', ''))
                if not player_name or pd.isna(player_name) or player_name.lower() == 'nan':
                    continue
                
                player_two = str(row.get('player2', ''))
                if pd.isna(player_two) or player_two.lower() == 'nan':
                    player_two = ""
                    
                score = str(row.get('score', ''))
                if pd.isna(score) or score.lower() == 'nan':
                    score = ""
                    
                is_penalty = "penalty" in evt_type_raw
                is_shootout = "shootout" in evt_type_raw
                
                import json
                extra_data = {
                    "playerTwo": player_two,
                    "score": score,
                    "isPenalty": is_penalty,
                    "isShootoutPenalty": is_shootout
                }
                
                team = str(row.get('team', ''))
                t_code = m.home_team_code if team == home_2022_team else m.away_team_code
                
                event_entry = Event(
                    match_id=m.id,
                    type=evt_type,
                    player_name=player_name,
                    team_code=t_code or "UNK",
                    minute=minute_val,
                    extra_info=json.dumps(extra_data)
                )
                m.events.append(event_entry)
                records_updated += 1
                
        await session.commit()
        logger.info(f"Successfully injected placeholder match details. Created {records_updated} records.")
        return True
        
    except Exception as e:
        logger.error(f"Failed to inject match details: {e}", exc_info=True)
        return False

async def run_match_details_scraper():
    logger.info("Starting Match Details Scraper...")
    async with AsyncSessionLocal() as session:
        await inject_mock_match_data_for_2026(session)
