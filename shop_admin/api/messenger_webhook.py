"""Meta Messenger verification and message webhook."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..providers.messenger import messenger_verification_token, normalize_messenger_event, verification_challenge
from ..services.order_service import OrderIngestionService


router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.get("/messenger")
async def messenger_verify(request: Request):
    payload = request.query_params
    if messenger_verification_token(dict(payload), settings.messenger_verify_token):
        return PlainTextResponse(verification_challenge(dict(payload)))
    raise HTTPException(status_code=403, detail="Token weryfikacyjny nie pasuje.")


@router.post("/messenger")
async def messenger_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    raw_body = await request.body()
    try:
        payload = await request.json()
        messages = normalize_messenger_event(
            payload,
            settings.messenger_app_secret,
            raw_body,
            request.headers.get("X-Hub-Signature-256"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    service = OrderIngestionService(session)
    accepted = 0
    for message in messages:
        await service.ingest(message)
        accepted += 1
    return {"accepted": accepted}
