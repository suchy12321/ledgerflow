"""Customer resolution for inbound shop messages."""
from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Customer
from ..schemas import ParsedOrder


class CustomerMatcher:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, parsed: ParsedOrder, sender: str) -> Customer | None:
        if parsed.messenger_psid:
            row = await self.session.scalar(
                select(Customer).where(func.lower(Customer.messenger_psid) == parsed.messenger_psid.lower())
            )
            if row:
                return row

        if parsed.customer_email:
            row = await self.session.scalar(
                select(Customer).where(func.lower(Customer.email) == parsed.customer_email.lower().strip())
            )
            if row:
                return row

        sender_email = sender.strip() if "@" in sender else ""
        if sender_email:
            row = await self.session.scalar(
                select(Customer).where(func.lower(Customer.email) == sender_email.lower())
            )
            if row:
                return row

        if parsed.customer_phone:
            row = await self.session.scalar(select(Customer).where(Customer.phone == parsed.customer_phone))
            if row:
                return row

        name = (parsed.customer_name or _name_from_sender(sender) or "").strip()
        if name:
            customers = (await self.session.execute(select(Customer))).scalars().all()
            best = _best_name_match(name, customers)
            if best and best[1] >= 0.68:
                return best[0]
        return None


def _name_from_sender(sender: str) -> str:
    if not sender or sender.startswith("messenger:"):
        return ""
    return sender.split("@", 1)[0].replace(".", " ").replace("_", " ").title()


def _best_name_match(query: str, customers: list[Customer]):
    query_norm = _normalize(query)
    best = None
    for customer in customers:
        score = SequenceMatcher(None, query_norm, _normalize(customer.name)).ratio()
        if best is None or score > best[1]:
            best = (customer, score)
    return best


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())
