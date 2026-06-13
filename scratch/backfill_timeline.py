import asyncio
from app.db.database import AsyncSessionLocal
from app.db.models import Match, Event
from scrapling import Fetcher
from sqlalchemy import delete

async def run():
    async with AsyncSessionLocal() as session:
        match = await session.get(Match, 'group_a_mex_v_rsa')
        if not match: return
        
        fetcher = Fetcher(auto_match=False)
        summ = fetcher.get('http://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event=760415').json()
        
        parsed_events = []
        key_events = summ.get("keyEvents", [])
        for ev in key_events:
            etype = ev.get("type", {}).get("text", "").lower()
            if "goal" in etype:
                mapped_type = "goal"
            elif "yellow" in etype:
                mapped_type = "card_yellow"
            elif "red" in etype:
                mapped_type = "card_red"
            elif "substitution" in etype:
                mapped_type = "substitution"
            else:
                continue
                
            clock = ev.get("clock", {}).get("displayValue", "0").replace("'", "")
            minute = int(clock.split("+")[0]) if "+" in clock else (int(clock) if clock else 0)
            
            participant = ev.get("participants", [{}])[0].get("athlete", {}).get("displayName", "Unknown")
            ev_team = ev.get("team", {}).get("displayName", "")
            side = "home" if "mexico" in ev_team.lower() else "away"
            team_code = match.home_team_code if side == "home" else match.away_team_code
            
            import json
            extra_data = {}
            if "+" in clock:
                extra_data["clockDisplay"] = clock
                
            if mapped_type == "substitution":
                parts = ev.get("participants", [])
                if len(parts) > 1:
                    extra_data["playerTwo"] = parts[1].get("athlete", {}).get("displayName", "Unknown")
                    
            if ev.get("shootout"):
                extra_data["isShootoutPenalty"] = True
                
            extra = json.dumps(extra_data) if extra_data else None
                
            parsed_events.append(Event(
                match_id=match.id,
                type=mapped_type,
                player_name=participant,
                team_code=team_code,
                minute=minute,
                extra_info=extra,
                source="espn",
                is_overridden=True
            ))
            
        if parsed_events:
            await session.execute(delete(Event).where(Event.match_id == match.id))
            session.add_all(parsed_events)
            await session.commit()
            print(f'Timeline events backfilled and protected! Total: {len(parsed_events)}')

if __name__ == "__main__":
    asyncio.run(run())
