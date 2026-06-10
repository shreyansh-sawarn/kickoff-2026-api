import asyncio
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.db.models import Match

async def f():
    async with AsyncSessionLocal() as db:
        matches = (await db.execute(select(Match))).scalars().all()
        for m in matches[:5]:
            print(m.home_team, m.status, m.kickoff_utc)

if __name__ == "__main__":
    asyncio.run(f())
