"""Offline order parser with a small provider interface for future AI parsers."""
from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod

from ..providers.channels import IncomingMessage
from ..schemas import ParsedLine, ParsedOrder


class OrderParser(ABC):
    @abstractmethod
    async def parse(self, message: IncomingMessage) -> ParsedOrder: ...


class RuleOrderParser(OrderParser):
    """Deterministic parser for the demo and common short purchase messages."""

    _email_re = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
    _phone_re = re.compile(r"(?<!\d)(?:\+48\s*)?\d{3}[\s-]?\d{3}[\s-]?\d{3}(?!\d)")
    _line_re = re.compile(
        r"(?P<qty>\d{1,4})\s*(?:x|szt\.?|komplet(?:y|ów)?|pcs?)\s*[:\-]?\s*(?P<sku>[A-Z0-9][A-Z0-9_-]{2,})",
        re.I,
    )
    _warehouse_re = re.compile(r"(?:magazyn|warehouse)\s*[:\-]?\s*([A-Z0-9_-]{2,})", re.I)

    async def parse(self, message: IncomingMessage) -> ParsedOrder:
        text = message.body or ""
        normalized = _ascii(text).upper()
        lines: list[ParsedLine] = []
        for match in self._line_re.finditer(normalized):
            sku = match.group("sku").strip("_-")
            if not sku:
                continue
            lines.append(
                ParsedLine(
                    sku=sku,
                    product_name=sku.replace("-", " ").title(),
                    quantity=max(1, int(match.group("qty"))),
                    confidence=0.92,
                )
            )

        emails = self._email_re.findall(text)
        phones = self._phone_re.findall(text)
        warehouse_match = self._warehouse_re.search(normalized)
        sender_name = _sender_name(message.sender)
        confidence = 0.9 if lines else 0.2
        return ParsedOrder(
            customer_name=sender_name,
            customer_email=emails[0].lower() if emails else None,
            customer_phone=phones[0] if phones else None,
            messenger_psid=message.sender.removeprefix("messenger:") if message.provider == "messenger" else None,
            warehouse_code=warehouse_match.group(1).upper() if warehouse_match else None,
            lines=lines,
            notes=text[:1000],
            confidence=confidence,
        )


def _ascii(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value or "") if not unicodedata.combining(char)
    )


def _sender_name(sender: str) -> str | None:
    if not sender:
        return None
    if sender.startswith("messenger:"):
        return None
    local = sender.split("@", 1)[0]
    local = local.replace(".", " ").replace("_", " ").strip()
    return local.title() if local else None
