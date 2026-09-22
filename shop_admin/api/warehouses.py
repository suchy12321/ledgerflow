"""Warehouse CRUD routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Product, Warehouse, StockBalance
from .common import flash, render


router = APIRouter(prefix="/shop", tags=["warehouses"])


@router.get("/warehouses")
async def warehouses(request: Request, session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Warehouse).order_by(Warehouse.name))).scalars().all()
    products = (await session.execute(select(Product).where(Product.active.is_(True)).order_by(Product.name))).scalars().all()
    return render(request, "warehouses.html", warehouses=rows, products=products)


@router.post("/warehouses/new")
async def create_warehouse(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    code = str(form.get("code") or "").strip().upper()
    name = str(form.get("name") or "").strip()
    if not code or not name:
        flash(request, "Kod i nazwa magazynu są wymagane.", "error")
        return RedirectResponse("/shop/warehouses", status_code=303)
    warehouse = Warehouse(code=code, name=name, active=True)
    session.add(warehouse)
    flash(request, "Magazyn dodany.", "success")
    return RedirectResponse("/shop/warehouses", status_code=303)


@router.post("/warehouses/{warehouse_id}/stock")
async def update_stock(warehouse_id, request: Request, session: AsyncSession = Depends(get_session)):
    warehouse = await session.get(Warehouse, warehouse_id)
    if not warehouse:
        flash(request, "Nie znaleziono magazynu.", "error")
        return RedirectResponse("/shop/warehouses", status_code=303)
    form = await request.form()
    product_id = form.get("product_id")
    quantity = int(form.get("quantity_on_hand") or 0)
    product = await session.get(__import__("shop_admin.models", fromlist=["Product"]).Product, product_id)
    if product is None:
        flash(request, "Nie znaleziono produktu.", "error")
        return RedirectResponse("/shop/warehouses", status_code=303)
    balance = await session.scalar(
        select(StockBalance).where(
            StockBalance.product_id == product.id,
            StockBalance.warehouse_id == warehouse.id,
        )
    )
    if balance is None:
        balance = StockBalance(product_id=product.id, warehouse_id=warehouse.id)
        session.add(balance)
    balance.quantity_on_hand = max(0, quantity)
    flash(request, "Stan magazynowy zapisany.", "success")
    return RedirectResponse("/shop/warehouses", status_code=303)
