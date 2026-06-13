import asyncio
from app.db.database import AsyncSessionLocal
from app.db.models import Match
from scrapling import Fetcher
from app.scraper.live_scraper import ParsedStat
from app.scraper.pipeline import _upsert_stats

async def run():
    async with AsyncSessionLocal() as session:
        match = await session.get(Match, 'group_a_mex_v_rsa')
        if not match: return
        
        fetcher = Fetcher(auto_match=False)
        summ = fetcher.get('http://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event=760415').json()
        
        parsed_stats = []
        boxscore = summ.get('boxscore', {})
        teams = boxscore.get('teams', [])
        for i, t in enumerate(teams):
            side = 'home' if i == 0 else 'away'
            stats_dict = {s['name']: s['displayValue'] for s in t.get('statistics', [])}
            parsed_stats.append(ParsedStat(
                team_side=side,
                possession_pct=int(float(stats_dict.get('possessionPct', '0').replace('%', ''))),
                shots=int(stats_dict.get('totalShots', '0')),
                shots_on_target=int(stats_dict.get('shotsOnTarget', '0')),
                corners=int(stats_dict.get('wonCorners', '0')),
                fouls=int(stats_dict.get('foulsCommitted', '0')),
                yellow_cards=int(stats_dict.get('yellowCards', '0')),
                red_cards=int(stats_dict.get('redCards', '0')),
            ))
            
        if parsed_stats:
            await _upsert_stats(session, match, parsed_stats)
            await session.commit()
            print('Stats updated with cards!')

if __name__ == "__main__":
    asyncio.run(run())
