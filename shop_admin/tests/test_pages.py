import pytest
from sqlalchemy import func, select

from shop_admin.db import SessionLocal
from shop_admin.config import settings
from shop_admin.models import IncomingMessage, OrderDraft
from shop_admin.providers.email_channel import EmailChannel
from shop_admin.providers.mock_channels import DemoEmailProvider
from shop_admin.seed import seed_demo_data
from shop_admin.services.order_service import OrderIngestionService


async def login(client) -> None:
    response = await client.post("/shop/login", data={"token": settings.admin_token})
    assert response.status_code == 303



@pytest.mark.asyncio
async def test_authentication_and_main_pages_render(client):
    unauthenticated = await client.get("/shop/dashboard", follow_redirects=False)
    invalid_login = await client.post("/shop/login", data={"token": "wrong"})

    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"] == "/shop/login"
    assert invalid_login.status_code == 401

    await login(client)
    for path in (
        "/shop/dashboard",
        "/shop/inbox",
        "/shop/orders",
        "/shop/products",
        "/shop/products/new",
        "/shop/warehouses",
        "/shop/customers",
        "/shop/customers/new",
    ):
        response = await client.get(path)
        assert response.status_code == 200, path
        assert "SHOP ADMIN" in response.text


@pytest.mark.asyncio
async def test_inbox_ingestion_order_detail_pdf_and_message_edit(client, db_session):
    await seed_demo_data(db_session)
    await login(client)
    service = OrderIngestionService(db_session)
    result = await service.ingest(await EmailChannel(DemoEmailProvider()).fetch_message("demo-email-0"))
    await db_session.commit()

    ingestion = await client.post("/shop/inbox/ingest-email")
    detail = await client.get(f"/shop/orders/{result.order_id}")
    invoice = await client.get(f"/shop/orders/{result.order_id}/invoice.pdf")
    message_response = await client.post(
        f"/shop/orders/{result.order_id}/message",
        data={"message": "Gotowy szkic po edycji handlowca."},
    )

    async with SessionLocal() as session:
        order = await session.get(OrderDraft, result.order_id)
        incoming_count = await session.scalar(select(func.count(IncomingMessage.id)))

    assert ingestion.status_code == 303
    assert detail.status_code == 200
    assert "Zatwierdź zamówienie" in detail.text
    assert "Wyślij" not in detail.text
    assert invoice.status_code == 200
    assert invoice.headers["content-type"].startswith("application/pdf")
    assert invoice.content.startswith(b"%PDF")
    assert message_response.status_code == 303
    assert order.customer_message == "Gotowy szkic po edycji handlowca."
    assert incoming_count == 2


@pytest.mark.asyncio
async def test_crud_pages_accept_new_records(client):
    await login(client)

    product = await client.post(
        "/shop/products/new",
        data={
            "sku": "TEST-SKU",
            "name": "Produkt testowy",
            "unit_price": "12.50",
            "vat_rate": "23",
            "description": "Tylko test",
        },
    )
    customer = await client.post(
        "/shop/customers/new",
        data={
            "name": "Jan Testowy",
            "email": "jan@example.pl",
            "messenger_psid": "test-psid",
        },
    )
    warehouse = await client.post(
        "/shop/warehouses/new",
        data={"code": "TEST", "name": "Magazyn testowy"},
    )

    assert product.status_code == 303
    assert customer.status_code == 303
    assert warehouse.status_code == 303
    assert "TEST-SKU" in (await client.get("/shop/products")).text
    assert "Jan Testowy" in (await client.get("/shop/customers")).text
    assert "Magazyn testowy" in (await client.get("/shop/warehouses")).text
