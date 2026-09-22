"""Protected email webhook adapter."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..providers.email_channel import create_email_channel
from ..services.order_service import OrderIngestionService


router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/email")
async def email_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    supplied = request.headers.get("X-ShopAdmin-Secret", "")
    if not hmac.compare_digest(supplied, settings.mail_webhook_secret):
        raise HTTPException(status_code=401, detail="Nieprawidłowy sekret webhooka.")
    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    channel = create_email_channel(settings)
    if payload.get("message_id"):
        messages = [await channel.fetch_message(str(payload["message_id"]))]
    else:
        messages = await channel.list_recent(20)
    service = OrderIngestionService(session)
    accepted = 0
    for message in messages:
        await service.ingest(message)
        accepted += 1
    return {"accepted": accepted}
