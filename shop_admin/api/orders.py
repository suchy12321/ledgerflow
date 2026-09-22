"""Order list, detail, approval, and invoice routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_session
from ..models import OrderDraft, OrderLine
from ..services.order_service import OrderIngestionService
from .common import flash, render


router = APIRouter(prefix="/shop", tags=["orders"])


@router.get("/orders")
async def orders(request: Request, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(OrderDraft)
            .options(selectinload(OrderDraft.customer), selectinload(OrderDraft.lines))
            .order_by(OrderDraft.created_at.desc())
        )
    ).scalars().all()
    return render(request, "orders.html", orders=rows)


@router.get("/orders/{order_id}")
async def order_detail(order_id, request: Request, session: AsyncSession = Depends(get_session)):
    order = await _loaded(session, order_id)
    if not order:
        return render(request, "orders.html", orders=[], error="Nie znaleziono zamówienia.")
    return render(request, "order_detail.html", order=order)


@router.post("/orders/{order_id}/approve")
async def approve_order(order_id, request: Request, session: AsyncSession = Depends(get_session)):
    try:
        await OrderIngestionService(session).approve(order_id)
        flash(request, "Zamówienie zatwierdzone. Rachunek i wiadomość są gotowe.", "success")
    except Exception as exc:
        flash(request, f"Nie udało się zatwierdzić: {exc}", "error")
    return RedirectResponse(f"/shop/orders/{order_id}", status_code=303)


@router.post("/orders/{order_id}/reject")
async def reject_order(order_id, request: Request, session: AsyncSession = Depends(get_session)):
    try:
        await OrderIngestionService(session).reject(order_id)
        flash(request, "Zamówienie odrzucone, rezerwacja została zwolniona.", "info")
    except Exception as exc:
        flash(request, f"Nie udało się odrzucić: {exc}", "error")
    return RedirectResponse(f"/shop/orders/{order_id}", status_code=303)


@router.post("/orders/{order_id}/message")
async def update_message(order_id, request: Request, session: AsyncSession = Depends(get_session)):
    order = await session.get(OrderDraft, order_id)
    if not order:
        flash(request, "Nie znaleziono zamówienia.", "error")
        return RedirectResponse("/shop/orders", status_code=303)
    form = await request.form()
    order.customer_message = str(form.get("message") or "")
    order.message_status = "ready"
    flash(request, "Szkic wiadomości zapisany.", "success")
    return RedirectResponse(f"/shop/orders/{order_id}", status_code=303)


@router.get("/orders/{order_id}/invoice.pdf")
async def invoice(order_id, request: Request, session: AsyncSession = Depends(get_session)):
    order = await _loaded(session, order_id)
    if not order or not order.invoice_path:
        flash(request, "Rachunek nie został jeszcze wygenerowany.", "error")
        return RedirectResponse(f"/shop/orders/{order_id}", status_code=303)
    return FileResponse(order.invoice_path, media_type="application/pdf", filename=f"rachunek-{order_id}.pdf")


async def _loaded(session: AsyncSession, order_id):
    return await session.scalar(
        select(OrderDraft)
        .where(OrderDraft.id == order_id)
        .options(
            selectinload(OrderDraft.customer),
            selectinload(OrderDraft.warehouse),
            selectinload(OrderDraft.lines).selectinload(OrderLine.product),
            selectinload(OrderDraft.invoice),
        )
    )
