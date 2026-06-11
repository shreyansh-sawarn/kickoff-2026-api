import urllib.request
import urllib.error
import re
import logging

logger = logging.getLogger(__name__)

def extract_image_from_html(url: str) -> str:
    """Fetches the webpage HTML using Python's default User-Agent and extracts the og:image meta tag."""
    try:
        # Note: ESPN returns 202 Accepted and empty body with generic Chrome User-Agents
        # to prevent scraping, but accepts standard default Python urllib User-Agents
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as response:
            if response.status != 200:
                return ""
            html = response.read().decode('utf-8', errors='ignore')
            
            # Match og:image tag content
            match = re.search(r'<meta[^>]+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html)
            if match:
                return match.group(1)
            
            match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', html)
            if match:
                return match.group(1)
            
            # Twitter image fallbacks
            match = re.search(r'<meta[^>]+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']', html)
            if match:
                return match.group(1)
    except Exception as e:
        logger.warning(f"Failed to extract image from {url}: {e}")
    return ""
