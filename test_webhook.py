import asyncio
from app.db.database import AsyncSessionLocal
from app.db.models import WebhookSubscription
from app.services.webhooks import dispatch_webhook

async def test_webhook():
    async with AsyncSessionLocal() as db:
        # Create subscription
        sub = WebhookSubscription(
            url='http://127.0.0.1:9999/webhook',
            secret='mysecret',
            events='["*"]',
            active=True
        )
        db.add(sub)
        await db.commit()
        
        # Test dispatch
        await dispatch_webhook('match.goal', {'match_id': 'test_123', 'home_score': 1, 'away_score': 0})
        
        # Sleep slightly to let async background task complete
        await asyncio.sleep(1)

asyncio.run(test_webhook())
