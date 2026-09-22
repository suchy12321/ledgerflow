"""Product CRUD routes."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Product
from .common import flash, render


router = APIRouter(prefix="/shop", tags=["products"])


@router.get("/products")
async def products(request: Request, session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Product).order_by(Product.name))).scalars().all()
    return render(request, "products.html", products=rows)


@router.get("/products/new")
async def new_product(request: Request):
    return render(request, "product_form.html", product=None)


@router.post("/products/new")
async def create_product(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    try:
        product = Product(
            sku=str(form["sku"]).strip().upper(),
            name=str(form["name"]).strip(),
            unit_price=Decimal(str(form.get("unit_price") or "0")),
            vat_rate=Decimal(str(form.get("vat_rate") or "23")),
            active=True,
            description=form.get("description"),
        )
        session.add(product)
        flash(request, "Produkt dodany.", "success")
    except (InvalidOperation, KeyError) as exc:
        flash(request, f"Sprawdź ceny i wymagane pola: {exc}", "error")
        return render(request, "product_form.html", product=None, error="Nieprawidłowe dane produktu.")
    return RedirectResponse("/shop/products", status_code=303)


@router.get("/products/{product_id}/edit")
async def edit_product(product_id, request: Request, session: AsyncSession = Depends(get_session)):
    product = await session.get(Product, product_id)
    return render(request, "product_form.html", product=product)


@router.post("/products/{product_id}/edit")
async def update_product(product_id, request: Request, session: AsyncSession = Depends(get_session)):
    product = await session.get(Product, product_id)
    if not product:
        flash(request, "Nie znaleziono produktu.", "error")
        return RedirectResponse("/shop/products", status_code=303)
    form = await request.form()
    product.sku = str(form["sku"]).strip().upper()
    product.name = str(form["name"]).strip()
    product.unit_price = Decimal(str(form.get("unit_price") or "0"))
    product.vat_rate = Decimal(str(form.get("vat_rate") or "23"))
    product.description = form.get("description")
    flash(request, "Produkt zaktualizowany.", "success")
    return RedirectResponse("/shop/products", status_code=303)
