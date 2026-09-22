"""Warehouse availability and reservation operations."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Product, StockBalance, Warehouse
from ..schemas import StockCheck


class StockUnavailable(RuntimeError):
    pass


@dataclass
class StockResult:
    checks: list[StockCheck]
    sufficient: bool


class StockService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def balance(self, product: Product, warehouse: Warehouse) -> StockBalance:
        row = await self.session.scalar(
            select(StockBalance).where(
                StockBalance.product_id == product.id,
                StockBalance.warehouse_id == warehouse.id,
            )
        )
        if row is None:
            row = StockBalance(product_id=product.id, warehouse_id=warehouse.id, quantity_on_hand=0, reserved_quantity=0)
            self.session.add(row)
            await self.session.flush()
        return row

    async def check(self, warehouse: Warehouse, items: list[tuple[Product | None, int, str]]) -> StockResult:
        checks: list[StockCheck] = []
        sufficient = True
        for index, (product, quantity, sku) in enumerate(items):
            if product is None:
                checks.append(StockCheck(line_index=index, sku=sku, requested=quantity, available=0, sufficient=False))
                sufficient = False
                continue
            balance = await self.balance(product, warehouse)
            available = max(0, balance.quantity_on_hand - balance.reserved_quantity)
            checks.append(
                StockCheck(
                    line_index=index,
                    product_id=str(product.id),
                    sku=sku,
                    requested=quantity,
                    available=available,
                    sufficient=available >= quantity,
                )
            )
            if available < quantity:
                sufficient = False
        return StockResult(checks=checks, sufficient=sufficient)

    async def reserve(self, warehouse: Warehouse, items: list[tuple[Product, int]]) -> None:
        if not items:
            return
        product_ids = [product.id for product, _ in items]
        rows = (
            await self.session.execute(
                select(StockBalance)
                .where(
                    StockBalance.product_id.in_(product_ids),
                    StockBalance.warehouse_id == warehouse.id,
                )
                .with_for_update()
            )
        ).scalars().all()
        balances = {row.product_id: row for row in rows}
        updates: list[tuple[StockBalance, int]] = []
        for product, quantity in items:
            balance = balances.get(product.id)
            if balance is None:
                raise StockUnavailable(f"Brak rekordu magazynowego dla {product.sku}.")
            available = balance.quantity_on_hand - balance.reserved_quantity
            if available < quantity:
                raise StockUnavailable(f"Brak stanu magazynowego dla {product.sku}.")
            updates.append((balance, quantity))
        for balance, quantity in updates:
            balance.reserved_quantity += quantity

    async def release(self, warehouse: Warehouse, items: list[tuple[Product, int]]) -> None:
        if not items:
            return
        product_ids = [product.id for product, _ in items]
        rows = (
            await self.session.execute(
                select(StockBalance).where(
                    StockBalance.product_id.in_(product_ids),
                    StockBalance.warehouse_id == warehouse.id,
                )
            )
        ).scalars().all()
        balances = {row.product_id: row for row in rows}
        for product, quantity in items:
            balance = balances.get(product.id)
            if balance:
                balance.reserved_quantity = max(0, balance.reserved_quantity - quantity)
