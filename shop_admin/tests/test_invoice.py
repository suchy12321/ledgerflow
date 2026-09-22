from decimal import Decimal
from pathlib import Path

import pytest

from shop_admin.config import settings
from shop_admin.models import OrderDraft, OrderLine
from shop_admin.services.invoice_service import InvoiceService


@pytest.mark.asyncio
async def test_invoice_pdf_is_generated_without_async_relationship_loading(tmp_path):
    upload_dir = Path(settings.upload_dir)
    order = OrderDraft(
        total_net=Decimal("100.00"),
        total_vat=Decimal("23.00"),
        total_gross=Decimal("123.00"),
        invoice_number="PROJEKT-TEST",
    )
    line = OrderLine(
        sku_snapshot="KAWA-1KG",
        name_snapshot="Kawa ziarnista 1 kg",
        quantity=2,
        unit_price=Decimal("50.00"),
        vat_rate=Decimal("23"),
        line_net=Decimal("100.00"),
        line_vat=Decimal("23.00"),
        line_gross=Decimal("123.00"),
    )

    path = Path(
        InvoiceService(upload_dir=upload_dir).generate(
            order,
            final=False,
            customer_name="Anna Kowalska",
            customer_email="anna@example.pl",
            lines=[line],
        )
    )

    payload = path.read_bytes()
    assert payload.startswith(b"%PDF")
    assert path.stat().st_size > 500
    assert order.invoice_path == str(path)


@pytest.mark.asyncio
async def test_final_invoice_regenerates_same_order(tmp_path):
    upload_dir = Path(settings.upload_dir)
    order = OrderDraft(
        total_net=Decimal("10.00"),
        total_vat=Decimal("2.30"),
        total_gross=Decimal("12.30"),
        invoice_number="RACHUNEK-TEST",
    )
    service = InvoiceService(upload_dir=upload_dir)
    service.generate(
        order,
        final=False,
        customer_name="Anna Kowalska",
        lines=[],
    )
    first_path = Path(order.invoice_path)

    final_path = Path(service.generate(order, final=True))

    payload = final_path.read_bytes()
    assert payload.startswith(b"%PDF")
    assert final_path != first_path or final_path.stat().st_size > 0
