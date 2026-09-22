"""Customer CRUD routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Customer
from .common import flash, render


router = APIRouter(prefix="/shop", tags=["customers"])


@router.get("/customers")
async def customers(request: Request, session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Customer).order_by(Customer.name))).scalars().all()
    return render(request, "customers.html", customers=rows)


@router.get("/customers/new")
async def new_customer(request: Request):
    return render(request, "customer_form.html", customer=None)


@router.post("/customers/new")
async def create_customer(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    customer = Customer(
        name=str(form.get("name") or "").strip(),
        email=str(form.get("email") or "").strip() or None,
        phone=str(form.get("phone") or "").strip() or None,
        tax_id=str(form.get("tax_id") or "").strip() or None,
        messenger_psid=str(form.get("messenger_psid") or "").strip() or None,
        notes=form.get("notes"),
    )
    if not customer.name:
        flash(request, "Nazwa klienta jest wymagana.", "error")
        return render(request, "customer_form.html", customer=None, error="Uzupełnij nazwę.")
    session.add(customer)
    flash(request, "Klient dodany.", "success")
    return RedirectResponse("/shop/customers", status_code=303)


@router.get("/customers/{customer_id}/edit")
async def edit_customer(customer_id, request: Request, session: AsyncSession = Depends(get_session)):
    customer = await session.get(Customer, customer_id)
    return render(request, "customer_form.html", customer=customer)


@router.post("/customers/{customer_id}/edit")
async def update_customer(customer_id, request: Request, session: AsyncSession = Depends(get_session)):
    customer = await session.get(Customer, customer_id)
    if not customer:
        flash(request, "Nie znaleziono klienta.", "error")
        return RedirectResponse("/shop/customers", status_code=303)
    form = await request.form()
    customer.name = str(form.get("name") or "").strip()
    customer.email = str(form.get("email") or "").strip() or None
    customer.phone = str(form.get("phone") or "").strip() or None
    customer.tax_id = str(form.get("tax_id") or "").strip() or None
    customer.messenger_psid = str(form.get("messenger_psid") or "").strip() or None
    customer.notes = form.get("notes")
    flash(request, "Klient zaktualizowany.", "success")
    return RedirectResponse("/shop/customers", status_code=303)
