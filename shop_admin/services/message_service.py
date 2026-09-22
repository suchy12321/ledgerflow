"""Draft customer messages. The service deliberately never sends messages."""
from __future__ import annotations

from decimal import Decimal

from ..models import OrderDraft, OrderLine


class MessageService:
    def draft(self, order: OrderDraft) -> str:
        return self.draft_for(
            order.customer.name if order.customer else "Kliencie",
            list(order.lines),
            order.total_gross,
        )

    def draft_for(
        self, customer: str, lines: list[OrderLine], total_gross: Decimal
    ) -> str:
        body_lines = "\n".join(
            f"- {line.quantity} x {line.sku_snapshot} ({line.name_snapshot}): {line.line_gross:.2f} PLN"
            for line in lines
        )
        if any(line.status != "confirmed" for line in lines):
            availability = "Niektóre pozycje wymagają potwierdzenia dostępności."
        else:
            availability = "Wszystkie pozycje są dostępne w wybranym magazynie."
        return (
            f"Dzień dobry {customer},\n\n"
            f"przygotowaliśmy zamówienie:\n{body_lines}\n\n"
            f"{availability}\n"
            f"Łącznie: {total_gross:.2f} PLN. "
            "W załączeniu przesyłamy projekt rachunku. Prosimy o potwierdzenie, "
            "a następnie zatwierdzimy zamówienie.\n\nPozdrawiamy,\n"
            "Zespół sklepu"
        )
