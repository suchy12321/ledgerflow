"""Shop Admin dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import IncomingMessage, OrderDraft, Product, StockBalance
from .common import render


router = APIRouter(prefix="/shop", tags=["dashboard"])


@router.get("/dashboard")
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    message_count = await session.scalar(select(func.count(IncomingMessage.id)))
    review_count = await session.scalar(
        select(func.count(OrderDraft.id)).where(OrderDraft.status == "needs_review")
    )
    ready_count = await session.scalar(
        select(func.count(OrderDraft.id)).where(OrderDraft.status == "ready_for_approval")
    )
    low_stock = await session.scalar(
        select(func.count(StockBalance.id)).where(
            StockBalance.quantity_on_hand - StockBalance.reserved_quantity <= 5
        )
    )
    recent_messages = (
        await session.execute(
            select(IncomingMessage).order_by(IncomingMessage.received_at.desc()).limit(8)
        )
    ).scalars().all()
    recent_orders = (
        await session.execute(select(OrderDraft).order_by(OrderDraft.created_at.desc()).limit(8))
    ).scalars().all()
    return render(
        request,
        "dashboard.html",
        message_count=message_count or 0,
        review_count=review_count or 0,
        ready_count=ready_count or 0,
        low_stock=low_stock or 0,
        recent_messages=recent_messages,
        recent_orders=recent_orders,
    )
