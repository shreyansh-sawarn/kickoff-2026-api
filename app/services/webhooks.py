import asyncio
import hmac
import hashlib
import json
import logging
import httpx
from typing import Dict, Any

from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.db.models import WebhookSubscription

logger = logging.getLogger(__name__)

async def dispatch_webhook(event_type: str, payload: Dict[str, Any]):
    """
    Dispatch a webhook to all active subscribers interested in the event.
    """
    async with AsyncSessionLocal() as db:
        stmt = select(WebhookSubscription).where(WebhookSubscription.active == True)
        result = await db.execute(stmt)
        subscriptions = result.scalars().all()

    payload_str = json.dumps({"event": event_type, "data": payload})
    payload_bytes = payload_str.encode("utf-8")

    tasks = []
    for sub in subscriptions:
        try:
            subscribed_events = json.loads(sub.events) if sub.events else []
            if "*" not in subscribed_events and event_type not in subscribed_events:
                continue

            # Calculate signature if secret is provided
            headers = {"Content-Type": "application/json"}
            if sub.secret:
                signature = hmac.new(
                    sub.secret.encode("utf-8"),
                    payload_bytes,
                    hashlib.sha256
                ).hexdigest()
                headers["X-Hub-Signature"] = f"sha256={signature}"

            tasks.append(_send_webhook(sub.url, payload_bytes, headers))
        except Exception as e:
            logger.error(f"Error preparing webhook for {sub.url}: {e}")

    if tasks:
        # Fire and forget (gather in background)
        async def _run_tasks():
            await asyncio.gather(*tasks, return_exceptions=True)
        asyncio.create_task(_run_tasks())

async def _send_webhook(url: str, payload_bytes: bytes, headers: dict):
    """Internal helper to actually make the HTTP request."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, content=payload_bytes, headers=headers)
            if response.status_code >= 400:
                logger.warning(f"Webhook delivery to {url} failed with status {response.status_code}")
            else:
                logger.info(f"Webhook delivered to {url}")
    except Exception as e:
        logger.warning(f"Webhook delivery to {url} failed: {e}")
