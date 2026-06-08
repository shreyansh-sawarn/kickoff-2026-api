"""
POST /api/v1/webhooks/subscribe endpoints.
"""
import json
from typing import List, Optional
from pydantic import BaseModel, HttpUrl
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.db.database import get_db
from app.db.models import WebhookSubscription

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class SubscribeRequest(BaseModel):
    url: HttpUrl
    secret: Optional[str] = None
    events: List[str] = ["*"]  # e.g., ["match.goal", "match.status_change"]


class SubscribeResponse(BaseModel):
    id: int
    url: str
    events: List[str]
    message: str


@router.post("/subscribe", response_model=SubscribeResponse, status_code=status.HTTP_201_CREATED)
async def subscribe(req: SubscribeRequest, db: AsyncSession = Depends(get_db)):
    """
    Subscribe a URL to receive real-time match events.
    """
    # Check if subscription already exists for this URL
    stmt = select(WebhookSubscription).where(WebhookSubscription.url == str(req.url))
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.secret = req.secret
        existing.events = json.dumps(req.events)
        existing.active = True
        sub_id = existing.id
        msg = "Subscription updated successfully"
    else:
        new_sub = WebhookSubscription(
            url=str(req.url),
            secret=req.secret,
            events=json.dumps(req.events),
            active=True
        )
        db.add(new_sub)
        await db.flush() # flush to get the ID
        sub_id = new_sub.id
        msg = "Subscription created successfully"

    await db.commit()
    return SubscribeResponse(
        id=sub_id,
        url=str(req.url),
        events=req.events,
        message=msg
    )


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(subscription_id: int, db: AsyncSession = Depends(get_db)):
    """
    Delete a webhook subscription.
    """
    stmt = select(WebhookSubscription).where(WebhookSubscription.id == subscription_id)
    result = await db.execute(stmt)
    sub = result.scalar_one_or_none()
    
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
        
    await db.execute(delete(WebhookSubscription).where(WebhookSubscription.id == subscription_id))
    await db.commit()
    return None
