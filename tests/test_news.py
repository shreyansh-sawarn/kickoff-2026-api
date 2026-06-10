import asyncio
from app.scraper.news import fetch_latest_news

async def main():
    res = await fetch_latest_news(limit=10)
    for article in res:
        print(f"Title: {article['title']}")
        print(f"Source: {article['source']}")
        print(f"Image: {article['image_url']}")
        print("----")

if __name__ == "__main__":
    asyncio.run(main())
