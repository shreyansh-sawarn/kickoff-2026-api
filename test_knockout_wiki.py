import asyncio
from app.scraper.wikipedia import fetch_wikitext, WC2026_KNOCKOUT_PAGE

async def main():
    text = await fetch_wikitext(WC2026_KNOCKOUT_PAGE)
    with open("knockout_wiki.txt", "w", encoding="utf-8") as f:
        f.write(text or "FAILED")
    print("Done")

if __name__ == "__main__":
    asyncio.run(main())
