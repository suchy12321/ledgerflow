"""DTOs used by the order intake pipeline."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ParsedLine(BaseModel):
    sku: str | None = None
    product_name: str | None = None
    quantity: int = Field(ge=1)
    confidence: float = Field(default=0.0, ge=0, le=1)


class ParsedOrder(BaseModel):
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    messenger_psid: str | None = None
    warehouse_code: str | None = None
    lines: list[ParsedLine] = Field(default_factory=list)
    notes: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class StockCheck(BaseModel):
    line_index: int
    product_id: str | None = None
    sku: str
    requested: int
    available: int = 0
    sufficient: bool = False


class OrderBuildResult(BaseModel):
    order_id: str
    status: str
    issues: list[str] = Field(default_factory=list)
