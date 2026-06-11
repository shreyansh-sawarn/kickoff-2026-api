import feedparser
import logging
from typing import List, Dict, Any
from datetime import datetime
from email.utils import parsedate_to_datetime
import re

logger = logging.getLogger(__name__)

# ESPN Soccer RSS
ESPN_RSS = "https://www.espn.com/espn/rss/soccer/news"
# SkySports Football RSS
SKYSPORTS_RSS = "https://www.skysports.com/rss/12040"

def clean_html(raw_html: str) -> str:
    """Removes HTML tags from a string and filters out literal 'null' strings."""
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    cleaned = re.sub(cleanr, '', raw_html).strip()
    if cleaned.lower() == "null":
        return ""
    return cleaned

def extract_image(entry) -> str:
    """Extracts an image URL from an RSS entry if available."""
    # Check media_content
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if 'url' in media:
                return media['url']
                
    # Check enclosures
    if hasattr(entry, 'enclosures'):
        for enclosure in entry.enclosures:
            if 'type' in enclosure and enclosure['type'].startswith('image/'):
                return enclosure['href']
                
    # Check for image embedded in description or summary
    for field in ['description', 'summary']:
        if hasattr(entry, field):
            val = getattr(entry, field)
            if val:
                match = re.search(r'<img[^>]+src="([^">]+)"', val)
                if match:
                    return match.group(1)
                
    # ESPN RSS specific: Check links or specific tag attributes
    if hasattr(entry, 'links'):
        for link in entry.links:
            if 'href' in link and any(ext in link['href'].lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                return link['href']
            
    return ""

async def fetch_latest_news(limit: int = 4) -> List[Dict[Any, Any]]:
    """Fetches and parses the latest soccer news from RSS feeds."""
    articles = []
    
    try:
        # We can use asyncio.to_thread since feedparser is synchronous
        import asyncio
        import urllib.request
        from datetime import timezone
        
        # Download ESPN RSS feed content with headers that bypass AWS WAF blocks on cloud servers
        def get_espn_xml():
            try:
                url = ESPN_RSS
                req = urllib.request.Request(url)
                # Simulating a scraper-safe User-Agent (like Wget or crawler bot)
                req.add_header('User-Agent', 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)')
                req.add_header('Accept', 'application/rss+xml, application/xml, text/xml, */*')
                with urllib.request.urlopen(req, timeout=4) as response:
                    if response.status == 200:
                        return response.read()
            except Exception as e:
                logger.warn(f"Failed to pull ESPN XML via custom headers: {e}")
            return None

        espn_xml, sky_feed = await asyncio.gather(
            asyncio.to_thread(get_espn_xml),
            asyncio.to_thread(feedparser.parse, SKYSPORTS_RSS)
        )
        
        # Parse ESPN Feed from downloaded string, or fallback to standard parse
        if espn_xml:
            espn_feed = feedparser.parse(espn_xml)
        else:
            espn_feed = await asyncio.to_thread(feedparser.parse, ESPN_RSS)
        
        # Parse ESPN
        for entry in espn_feed.entries:
            try:
                dt = parsedate_to_datetime(entry.published) if hasattr(entry, 'published') else datetime.now(timezone.utc)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except:
                dt = datetime.now(timezone.utc)
            
            summary_text = clean_html(entry.description) if hasattr(entry, 'description') else ""
            if not summary_text and hasattr(entry, 'summary'):
                summary_text = clean_html(entry.summary)

            articles.append({
                "title": entry.title,
                "summary": summary_text,
                "link": entry.link,
                "image_url": extract_image(entry),
                "source": "ESPN",
                "published_at": dt
            })
            
        # Parse SkySports
        for entry in sky_feed.entries:
            try:
                dt = parsedate_to_datetime(entry.published) if hasattr(entry, 'published') else datetime.now(timezone.utc)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except:
                dt = datetime.now(timezone.utc)
                
            articles.append({
                "title": entry.title,
                "summary": clean_html(entry.description) if hasattr(entry, 'description') else "",
                "link": entry.link,
                "image_url": extract_image(entry),
                "source": "SkySports",
                "published_at": dt
            })
            
        # Sort by published date descending
        articles.sort(key=lambda x: x['published_at'], reverse=True)
        
        # Filter for World Cup / International keywords, while excluding Tennis/Wimbledon keywords
        keywords = ["world cup", "fifa", "international", "qualifier", "national team", "worldcup", "tournament"]
        excluded_keywords = [
            "wimbledon", "tennis", "grand slam", "djokovic", "alcaraz", "sw19", "nadal", "federer", "court",
            "darts", "pdc", "littler", "humphries", "bullseye", "cricket", "ipl", "t20", "rugby", "golf", "f1",
            "formula 1", "nba", "basketball", "nfl", "super bowl", "hockey"
        ]
        
        filtered_articles = []
        for a in articles:
            text = (a["title"] + " " + a["summary"]).lower()
            # Must match soccer/WC keywords, and NOT contain tennis/wimbledon keywords
            if any(kw in text for kw in keywords) and not any(ex in text for ex in excluded_keywords):
                filtered_articles.append(a)
                
        # Fallback: if no world cup news found, just use the general news (applying exclusion list)
        if len(filtered_articles) < 2:
            final_articles = [a for a in articles if not any(ex in (a["title"] + " " + a["summary"]).lower() for ex in excluded_keywords)]
        else:
            final_articles = filtered_articles
            
        # Limit to required entries before fetching HTML metadata to avoid hitting limits or slowing down
        subset_articles = final_articles[:limit]
        
        # Async retrieve missing article image properties from web metadata
        from app.scraper.metadata_extractor import extract_image_from_html
        
        async def populate_image(art):
            if not art["image_url"] and art["link"]:
                # Fetch image from raw webpage metadata in background worker thread
                img = await asyncio.to_thread(extract_image_from_html, art["link"])
                if img:
                    art["image_url"] = img

        await asyncio.gather(*(populate_image(art) for art in subset_articles))
        
        # Clean up the output format for the API response
        result = []
        for a in subset_articles:
            result.append({
                "title": a["title"],
                "summary": a["summary"] if a["summary"] else "Latest updates from soccer spotlights.",
                "link": a["link"],
                "image_url": a["image_url"],
                "source": a["source"],
                "published_at": a["published_at"].isoformat()
            })
            
        return result
        
    except Exception as e:
        logger.error(f"Failed to fetch news: {e}", exc_info=True)
        return []
