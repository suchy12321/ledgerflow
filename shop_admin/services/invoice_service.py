"""Local PDF invoice generation."""
from __future__ import annotations

import unicodedata
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from ..config import settings
from ..models import OrderDraft, OrderLine
from ..security import safe_filename


class InvoiceService:
    def __init__(self, upload_dir: Path | None = None) -> None:
        self.upload_dir = (upload_dir or settings.upload_dir).resolve()
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        order: OrderDraft,
        final: bool = False,
        *,
        customer_name: str | None = None,
        customer_email: str = "",
        lines: list[OrderLine] | None = None,
        total_net: Decimal | None = None,
        total_vat: Decimal | None = None,
        total_gross: Decimal | None = None,
    ) -> str:
        from reportlab.pdfgen import canvas

        document_lines = list(lines if lines is not None else order.lines)
        net_total = total_net if total_net is not None else order.total_net
        vat_total = total_vat if total_vat is not None else order.total_vat
        gross_total = total_gross if total_gross is not None else order.total_gross
        resolved_customer_name = customer_name
        resolved_customer_email = customer_email
        if resolved_customer_name is None:
            resolved_customer_name = (
                order.customer.name if order.customer else "Nieprzypisany klient"
            )
            resolved_customer_email = (
                order.customer.email if order.customer and order.customer.email else ""
            )

        path = self.upload_dir / safe_filename(f"rachunek-{order.id}.pdf", "rachunek.pdf")
        pdf = canvas.Canvas(str(path), pagesize=(595, 842))
        width, height = 595, 842
        y = height - 48

        def line(text: str, size: int = 10, bold: bool = False) -> None:
            nonlocal y
            pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            pdf.drawString(42, y, _ascii(text)[:115])
            y -= size + 5

        line(settings.company_name, 16, True)
        line(settings.company_address, 9)
        line(f"NIP: {settings.company_nip}", 9)
        y -= 12
        line("RACHUNEK / PROJEKT" if not final else "RACHUNEK", 14, True)
        line(f"Numer roboczy: {order.invoice_number or str(order.id)[:8]}", 9)
        line(f"Data: {datetime.now().strftime('%Y-%m-%d')}", 9)
        y -= 14
        line(f"Klient: {resolved_customer_name}", 10, True)
        line(f"E-mail: {resolved_customer_email}", 9)
        y -= 14
        line("Pozycja | Ilość | Cena netto | VAT | Brutto", 9, True)
        y -= 4
        for item in document_lines:
            line(
                f"{item.sku_snapshot} | {item.quantity} | {item.unit_price:.2f} | "
                f"{item.vat_rate:.2f}% | {item.line_gross:.2f} PLN",
                9,
            )
            if y < 100:
                pdf.showPage()
                y = height - 48
        y -= 14
        line(f"Razem netto: {net_total:.2f} PLN", 10, True)
        line(f"Razem VAT: {vat_total:.2f} PLN", 10)
        line(f"Razem brutto: {gross_total:.2f} PLN", 11, True)
        if not final:
            y -= 18
            line("Dokument jest projektem i wymaga zatwierdzenia.", 10, True)
        pdf.save()
        order.invoice_path = str(path)
        return str(path)


def _ascii(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", value or "") if not unicodedata.combining(char))
