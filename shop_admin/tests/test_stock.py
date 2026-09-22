import pytest
from sqlalchemy import select

from shop_admin.models import Product, StockBalance, Warehouse
from shop_admin.providers.email_channel import EmailChannel
from shop_admin.providers.mock_channels import DemoEmailProvider
from shop_admin.seed import seed_demo_data
from shop_admin.services.order_service import OrderIngestionService
from shop_admin.services.stock_service import StockService, StockUnavailable


@pytest.mark.asyncio
async def test_insufficient_stock_requires_review_and_cannot_be_approved(db_session):
    await seed_demo_data(db_session)
    coffee = await db_session.scalar(select(Product).where(Product.sku == "KAWA-1KG"))
    coffee_balance = await db_session.scalar(
        select(StockBalance).where(StockBalance.product_id == coffee.id)
    )
    coffee_balance.quantity_on_hand = 1
    message = await EmailChannel(DemoEmailProvider()).fetch_message("demo-email-0")

    result = await OrderIngestionService(db_session).ingest(message)
    order = await OrderIngestionService(db_session)._loaded_order(result.order_id)
    coffee_line = next(line for line in order.lines if line.sku_snapshot == "KAWA-1KG")

    assert result.status == "needs_review"
    assert any("Za mało w magazynie" in issue for issue in result.issues)
    assert coffee_line.status == "unavailable"
    with pytest.raises(ValueError, match="gotowe do zatwierdzenia"):
        await OrderIngestionService(db_session).approve(order.id)


@pytest.mark.asyncio
async def test_reserve_fails_atomically_when_any_product_is_unavailable(db_session):
    await seed_demo_data(db_session)
    warehouse = await db_session.scalar(select(Warehouse))
    products = {
        product.sku: product
        for product in (
            await db_session.execute(select(Product).where(Product.sku.in_(["KAWA-1KG", "CUKIER-1KG"])))
        ).scalars()
    }
    coffee_balance = await db_session.scalar(
        select(StockBalance).where(
            StockBalance.product_id == products["KAWA-1KG"].id,
            StockBalance.warehouse_id == warehouse.id,
        )
    )
    coffee_balance.quantity_on_hand = 1
    stock = StockService(db_session)

    with pytest.raises(StockUnavailable, match="KAWA-1KG"):
        await stock.reserve(
            warehouse,
            [
                (products["KAWA-1KG"], 2),
                (products["CUKIER-1KG"], 1),
            ],
        )

    balances = (
        await db_session.execute(
            select(StockBalance).where(
                StockBalance.product_id.in_([products["KAWA-1KG"].id, products["CUKIER-1KG"].id])
            )
        )
    ).scalars().all()
    assert all(balance.reserved_quantity == 0 for balance in balances)
