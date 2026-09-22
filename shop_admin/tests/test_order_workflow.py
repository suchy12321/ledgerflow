from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from shop_admin.models import (
    IncomingMessage,
    InvoiceDocument,
    OrderDraft,
    ProcessingAttempt,
    Product,
    StockBalance,
)
from shop_admin.providers.email_channel import EmailChannel
from shop_admin.providers.mock_channels import DemoEmailProvider
from shop_admin.seed import seed_demo_data
from shop_admin.services.order_service import OrderIngestionService


@pytest.mark.asyncio
async def test_email_becomes_approvable_order_and_approval_reserves_stock(db_session):
    await seed_demo_data(db_session)
    message = await EmailChannel(DemoEmailProvider()).fetch_message("demo-email-0")
    service = OrderIngestionService(db_session)

    result = await service.ingest(message)
    duplicate = await service.ingest(message)

    assert duplicate == result
    assert result.status == "ready_for_approval"
    assert result.issues == []
    assert await db_session.scalar(select(func.count(IncomingMessage.id))) == 1

    order = await service._loaded_order(result.order_id)
    assert order.customer.name == "Anna Kowalska"
    assert order.warehouse.code == "MAIN"
    assert order.total_net == Decimal("176.50")
    assert order.total_vat == Decimal("40.60")
    assert order.total_gross == Decimal("217.10")
    assert [(line.sku_snapshot, line.status) for line in order.lines] == [
        ("KAWA-1KG", "confirmed"),
        ("FILIZANKA-BIALA", "confirmed"),
        ("CUKIER-1KG", "confirmed"),
    ]
    assert "Dzień dobry Anna Kowalska" in order.customer_message
    assert Path(order.invoice_path).is_file()
    assert order.invoice.number.startswith("PROJEKT-")
    assert order.invoice.status == "draft"

    coffee = await db_session.scalar(select(Product).where(Product.sku == "KAWA-1KG"))
    coffee_balance = await db_session.scalar(select(StockBalance).where(StockBalance.product_id == coffee.id))
    assert (coffee_balance.quantity_on_hand, coffee_balance.reserved_quantity) == (40, 0)

    approved = await service.approve(order.id)
    coffee_balance = await db_session.scalar(
        select(StockBalance).where(StockBalance.product_id == coffee_balance.product_id)
    )
    assert approved.status == "approved"
    assert approved.invoice.number.startswith("RACHUNEK-")
    assert approved.invoice.status == "final"
    assert (coffee_balance.quantity_on_hand, coffee_balance.reserved_quantity) == (40, 2)

    rejected = await service.reject(order.id)
    coffee_balance = await db_session.scalar(
        select(StockBalance).where(StockBalance.product_id == coffee_balance.product_id)
    )
    assert rejected.status == "rejected"
    assert (coffee_balance.quantity_on_hand, coffee_balance.reserved_quantity) == (40, 0)


@pytest.mark.asyncio
async def test_retry_rebuilds_message_without_creating_duplicate_orders(db_session):
    await seed_demo_data(db_session)
    message = await EmailChannel(DemoEmailProvider()).fetch_message("demo-email-0")
    service = OrderIngestionService(db_session)
    first = await service.ingest(message)
    incoming = await db_session.scalar(
        select(IncomingMessage).where(IncomingMessage.external_id == message.external_id)
    )

    retried = await service.retry(incoming.id)

    assert retried.status == "ready_for_approval"
    assert await db_session.scalar(select(func.count(OrderDraft.id))) == 1
    assert await db_session.scalar(select(func.count(ProcessingAttempt.id))) == 2
    assert await db_session.scalar(select(func.count(InvoiceDocument.id))) == 1
