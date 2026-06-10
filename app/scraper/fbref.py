"""
FBref Scraper for Minutes Played

This scraper gently fetches the World Cup player stats using soccerdata 
to extract the exact minutes played for each player.
"""
import logging
import asyncio
import pandas as pd
import soccerdata as sd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models import PlayerStatistic

logger = logging.getLogger(__name__)

def _sync_fetch_and_parse_fbref():
    # soccerdata automatically bypasses Cloudflare and caches data
    fbref = sd.FBref(leagues="INT-World Cup", seasons=2022)
    df = fbref.read_player_season_stats(stat_type="standard")
    return df

async def fetch_and_parse_fbref(session: AsyncSession):
    try:
        # Run synchronous soccerdata in a separate thread so it doesn't block the async event loop
        df = await asyncio.to_thread(_sync_fetch_and_parse_fbref)
        
        records_updated = 0
        for index, row in df.iterrows():
            # soccerdata FBref multiindex is usually (league, season, team, player)
            # Just grabbing the player name and team from the index
            player_name = index[3]
            team_name = index[2]
            
            # The country usually has a format like 'nl NED'. We try to extract the code
            nation = row.get(('nation', ''))
            if not nation or pd.isna(nation):
                # Fallback to team name's first 3 chars
                nation_code = team_name[:3].upper()
            else:
                nation_code = str(nation).split()[-1]

            minutes = row.get(('Playing Time', 'Min'))
            if pd.isna(minutes) or minutes == 0:
                continue
                
            minutes = int(minutes)
            
            # Upsert into DB
            stmt = select(PlayerStatistic).where(PlayerStatistic.player_name == player_name)
            result = await session.execute(stmt)
            stat = result.scalars().first()
            
            if stat:
                stat.minutes_played = minutes
                stat.team_code = nation_code
            else:
                stat = PlayerStatistic(
                    player_name=player_name,
                    team_code=nation_code,
                    minutes_played=minutes
                )
                session.add(stat)
                
            records_updated += 1
            
        await session.commit()
        logger.info(f"Successfully scraped FBref via soccerdata. Updated {records_updated} players.")
        return True
        
    except Exception as e:
        logger.error(f"Failed to scrape FBref via soccerdata: {e}", exc_info=True)
        return False

async def run_fbref_scraper():
    logger.info("Starting FBref minutes played scraper using soccerdata...")
    async with AsyncSessionLocal() as session:
        await fetch_and_parse_fbref(session)
