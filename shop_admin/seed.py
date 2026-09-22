"""Optional deterministic demo data for a fresh Shop Admin database."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Customer, Product, StockBalance, Warehouse


async def seed_demo_data(session: AsyncSession) -> None:
    warehouse = await session.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
    if warehouse is None:
        warehouse = Warehouse(code="MAIN", name="Magazyn główny", active=True)
        session.add(warehouse)
        await session.flush()

    products = [
        ("KAWA-1KG", "Kawa ziarnista 1 kg", Decimal("49.00"), Decimal("23"), 40),
        ("FILIZANKA-BIALA", "Filiżanka biała", Decimal("24.00"), Decimal("23"), 25),
        ("CUKIER-1KG", "Cukier 1 kg", Decimal("6.50"), Decimal("23"), 60),
    ]
    for sku, name, price, vat, stock in products:
        product = await session.scalar(select(Product).where(Product.sku == sku))
        if product is None:
            product = Product(sku=sku, name=name, unit_price=price, vat_rate=vat, active=True)
            session.add(product)
            await session.flush()
        balance = await session.scalar(
            select(StockBalance).where(
                StockBalance.product_id == product.id,
                StockBalance.warehouse_id == warehouse.id,
            )
        )
        if balance is None:
            session.add(
                StockBalance(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    quantity_on_hand=stock,
                    reserved_quantity=0,
                )
            )

    customer = await session.scalar(select(Customer).where(Customer.email == "anna@example.pl"))
    if customer is None:
        session.add(
            Customer(
                name="Anna Kowalska",
                email="anna@example.pl",
                phone="+48 123 456 789",
                messenger_psid="demo-psid",
                notes="Klient demo do testów zamówień.",
            )
        )
