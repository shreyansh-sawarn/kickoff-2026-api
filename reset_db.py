import asyncio
from sqlalchemy import delete
from app.db.database import AsyncSessionLocal
from app.db.models import Match, Event, PlayerStatistic

async def wipe():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Event))
        await db.execute(delete(PlayerStatistic))
        await db.execute(delete(Match))
        await db.commit()
    print("Database wiped!")

if __name__ == "__main__":
    asyncio.run(wipe())
