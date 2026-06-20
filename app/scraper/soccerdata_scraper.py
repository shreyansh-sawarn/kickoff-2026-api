"""
Internal Scraper for Minutes Played

This calculates 2026 player minutes natively from our own Lineups and Events
database, avoiding external FBref data which only has 2022 World Cup data.
"""
import logging
import asyncio
import json
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models import PlayerStatistic, Lineup, Event, Match

logger = logging.getLogger(__name__)

async def fetch_and_parse_fbref(session: AsyncSession):
    # Note: kept function name to avoid breaking scheduler imports
    try:
        # Clear out any stale mock data (e.g. 2022 players)
        await session.execute(delete(PlayerStatistic))
        
        matches = await session.scalars(select(Match))
        player_mins = {} # name -> { 'team': str, 'mins': int }
        
        for m in matches:
            lineups = await session.scalars(select(Lineup).where(Lineup.match_id == m.id))
            events = await session.scalars(select(Event).where(Event.match_id == m.id))
            
            p_times = {}
            for l in lineups:
                p_times[l.player_name] = {'start': 0 if l.is_starting else None, 'end': 90 if l.is_starting else None, 'team': l.team_code}
                
            for e in events:
                try: minute = int(e.minute)
                except: continue
                
                if e.type == 'substitution':
                    p_out = e.player_name
                    extra = json.loads(e.extra_info) if e.extra_info else {}
                    p_in = extra.get('playerTwo')
                    
                    if p_out in p_times:
                        p_times[p_out]['end'] = minute
                    if p_in:
                        if p_in not in p_times:
                            p_times[p_in] = {'start': None, 'end': None, 'team': e.team_code}
                        p_times[p_in]['start'] = minute
                        p_times[p_in]['end'] = 90
                elif 'red' in e.type:
                    p_out = e.player_name
                    if p_out in p_times:
                        p_times[p_out]['end'] = minute
                        
            for name, times in p_times.items():
                s, end_m = times['start'], times['end']
                if s is not None and end_m is not None and end_m >= s:
                    if name not in player_mins:
                        player_mins[name] = {'team': times['team'], 'mins': 0}
                    player_mins[name]['mins'] += (end_m - s)
                    
        records_updated = 0
        for player_name, data in player_mins.items():
            stmt = select(PlayerStatistic).where(PlayerStatistic.player_name == player_name)
            result = await session.execute(stmt)
            stat = result.scalars().first()
            
            if stat:
                stat.minutes_played = data['mins']
                if stat.team_code == "UNK" or not stat.team_code:
                    stat.team_code = data['team']
            else:
                stat = PlayerStatistic(
                    player_name=player_name,
                    team_code=data['team'],
                    minutes_played=data['mins']
                )
                session.add(stat)
            records_updated += 1
            
        await session.commit()
        logger.info(f"Successfully calculated 2026 minutes played natively. Updated {records_updated} players.")
        return True
        
    except Exception as e:
        logger.error(f"Failed to calculate 2026 minutes: {e}", exc_info=True)
        return False

async def run_fbref_scraper():
    logger.info("Starting 2026 minutes played calculator...")
    async with AsyncSessionLocal() as session:
        await fetch_and_parse_fbref(session)
