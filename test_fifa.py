import asyncio
import time
from datetime import datetime, timezone
from app.db.database import AsyncSessionLocal
from app.db.models import WebhookSubscription, Event, Match
from app.scraper.fifa import scrape_fifa_match
from app.scraper.pipeline import _upsert_events
from app.services.webhooks import dispatch_webhook
from sqlalchemy import select

async def test_fifa():
    async with AsyncSessionLocal() as db:
        # Create webhook subscription for conflicts
        sub = WebhookSubscription(
            url='http://127.0.0.1:9999/webhook',
            secret='mysecret',
            events='["system.conflict"]',
            active=True
        )
        db.add(sub)
        await db.commit()

    print("Running FIFA mock scrape...")
    async with AsyncSessionLocal() as db:
        stmt = select(Match).where(Match.home_team_code == 'QAT', Match.away_team_code == 'ECU')
        match = (await db.execute(stmt)).scalar_one_or_none()
        
        if match:
            print(f"Match found: {match.home_team} {match.home_score} - {match.away_score} {match.away_team}")
            
            # Scrape FIFA
            fifa_match = await scrape_fifa_match(match.home_team_code, match.away_team_code)
            if fifa_match:
                if fifa_match.home_score != match.home_score or fifa_match.away_score != match.away_score:
                    print("CONFLICT DETECTED!")
                    payload = {
                        "match_id": match.id,
                        "wikipedia_score": f"{match.home_score}-{match.away_score}",
                        "fifa_score": f"{fifa_match.home_score}-{fifa_match.away_score}",
                    }
                    await dispatch_webhook("system.conflict", payload)
                
                await _upsert_events(db, match, fifa_match.events, source="fifa")
                await db.commit()

            # Wait for webhook delivery
            await asyncio.sleep(2)

            stmt = select(Event).where(Event.match_id == match.id)
            events = (await db.execute(stmt)).scalars().all()
            print(f"Found {len(events)} events for this match:")
            for e in events:
                print(f"  - Minute {e.minute}: {e.player_name} ({e.type}) [{e.source}]")
        else:
            print("Match not found!")

asyncio.run(test_fifa())
