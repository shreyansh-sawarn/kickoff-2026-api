import asyncio
from app.scraper.match_details import run_match_details_scraper

if __name__ == "__main__":
    asyncio.run(run_match_details_scraper())
