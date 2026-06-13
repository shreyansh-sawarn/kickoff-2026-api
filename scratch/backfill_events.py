import asyncio
from app.db.database import AsyncSessionLocal
from app.db.models import Match, Event
from sqlalchemy import select
from scrapling import Fetcher

async def run():
    async with AsyncSessionLocal() as session:
        stmt = select(Match).where(Match.id == 'group_a_mex_v_rsa')
        result = await session.execute(stmt)
        match = result.scalar_one_or_none()
        if not match:
            return
            
        fetcher = Fetcher(auto_match=False)
        summ = fetcher.get('http://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event=760415').json()
        
        key_events = summ.get('keyEvents', [])
        for ev in key_events:
            etype = ev.get('type', {}).get('text', '').lower()
            if 'goal' in etype:
                mapped_type = 'goal'
            elif 'yellow' in etype:
                mapped_type = 'yellow'
            elif 'red' in etype:
                mapped_type = 'red'
            elif 'substitution' in etype:
                mapped_type = 'sub'
            else:
                continue
                
            clock = ev.get('clock', {}).get('displayValue', '0')
            minute = int(clock.split("'")[0]) if "'" in clock else 0
            
            participants = ev.get('participants', [{}])
            participant = participants[0].get('athlete', {}).get('displayName', 'Unknown')
            
            team_code = match.home_team_code
            for i, r in enumerate(summ.get('rosters', [])):
                for p in r.get('roster', []):
                    if p['athlete']['displayName'] == participant:
                        team_code = match.home_team_code if i == 0 else match.away_team_code
                        break
            
            if mapped_type != 'goal':
                e = Event(
                    match_id=match.id,
                    type=mapped_type,
                    player_name=participant,
                    team_code=team_code,
                    minute=minute,
                    source='espn'
                )
                session.add(e)
                
        await session.commit()
        print('Events added!')

asyncio.run(run())
