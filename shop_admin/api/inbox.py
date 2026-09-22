"""Inbox and channel ingestion routes."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import IncomingMessage
from ..providers.email_channel import create_email_channel
from ..providers.mock_channels import DemoMessengerChannel
from ..services.order_service import OrderIngestionService
from .common import flash, render


router = APIRouter(prefix="/shop", tags=["inbox"])


@router.get("/inbox")
async def inbox(request: Request, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(select(IncomingMessage).order_by(IncomingMessage.received_at.desc()))
    ).scalars().all()
    return render(request, "inbox.html", messages=rows)


@router.get("/inbox/{message_id}")
async def inbox_detail(message_id, request: Request, session: AsyncSession = Depends(get_session)):
    message = await session.get(IncomingMessage, message_id)
    if not message:
        return render(request, "inbox.html", messages=[], error="Nie znaleziono wiadomości.")
    return render(request, "inbox.html", messages=[message], selected=message)


@router.post("/inbox/ingest-email")
async def ingest_email(request: Request, session: AsyncSession = Depends(get_session)):
    try:
        channel = create_email_channel(__import__("shop_admin.config", fromlist=["settings"]).settings)
        messages = await channel.list_recent(20)
        service = OrderIngestionService(session)
        accepted = 0
        for message in messages:
            await service.ingest(message)
            accepted += 1
        flash(request, f"Sprawdzono {accepted} wiadomości e-mail.", "success")
    except Exception as exc:
        flash(request, f"Nie udało się pobrać wiadomości: {exc}", "error")
    return RedirectResponse("/shop/inbox", status_code=303)


@router.post("/inbox/ingest-messenger-demo")
async def ingest_messenger_demo(request: Request, session: AsyncSession = Depends(get_session)):
    try:
        service = OrderIngestionService(session)
        for message in await DemoMessengerChannel().list_recent(20):
            await service.ingest(message)
        flash(request, "Dodano demo wiadomości Messenger.", "success")
    except Exception as exc:
        flash(request, f"Nie udało się dodać demo Messenger: {exc}", "error")
    return RedirectResponse("/shop/inbox", status_code=303)


@router.post("/inbox/{message_id}/retry")
async def retry_message(message_id, request: Request, session: AsyncSession = Depends(get_session)):
    try:
        result = await OrderIngestionService(session).retry(message_id)
        flash(request, f"Przetwarzanie zakończone: {result.status}", "success")
    except Exception as exc:
        flash(request, f"Nie udało się ponowić: {exc}", "error")
    return RedirectResponse("/shop/inbox", status_code=303)
