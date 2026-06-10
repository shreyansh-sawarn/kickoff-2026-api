from fastapi import APIRouter
from typing import List, Dict, Any

from app.scraper.news import fetch_latest_news

router = APIRouter(prefix="/news", tags=["News"])

@router.get("", response_model=List[Dict[str, Any]])
async def get_news(limit: int = 4):
    """
    Fetches the latest soccer news.
    """
    return await fetch_latest_news(limit=limit)
