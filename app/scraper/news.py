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
    """Removes HTML tags from a string."""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

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
                
    # Check for image embedded in description
    if hasattr(entry, 'description'):
        match = re.search(r'<img[^>]+src="([^">]+)"', entry.description)
        if match:
            return match.group(1)
            
    return ""

async def fetch_latest_news(limit: int = 4) -> List[Dict[Any, Any]]:
    """Fetches and parses the latest soccer news from RSS feeds."""
    articles = []
    
    try:
        # We can use asyncio.to_thread since feedparser is synchronous
        import asyncio
        from datetime import timezone
        espn_feed, sky_feed = await asyncio.gather(
            asyncio.to_thread(feedparser.parse, ESPN_RSS),
            asyncio.to_thread(feedparser.parse, SKYSPORTS_RSS)
        )
        
        # Parse ESPN
        for entry in espn_feed.entries:
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
        
        # Filter for World Cup / International keywords
        keywords = ["world cup", "fifa", "international", "qualifier", "national team", "worldcup", "tournament"]
        
        filtered_articles = []
        for a in articles:
            text = (a["title"] + " " + a["summary"]).lower()
            if any(kw in text for kw in keywords):
                filtered_articles.append(a)
                
        # Fallback: if no world cup news found, just use the general news so the UI isn't empty
        final_articles = filtered_articles if len(filtered_articles) >= 2 else articles
        
        # Clean up the output format for the API response
        result = []
        for a in final_articles[:limit]:
            result.append({
                "title": a["title"],
                "summary": a["summary"],
                "link": a["link"],
                "image_url": a["image_url"],
                "source": a["source"],
                "published_at": a["published_at"].isoformat()
            })
            
        return result
        
    except Exception as e:
        logger.error(f"Failed to fetch news: {e}", exc_info=True)
        return []
