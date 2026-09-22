"""Shop Admin domain models."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import CHAR, TypeDecorator

from .db import Base


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return value if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class Customer(Base):
    __tablename__ = "shop_customers"
    __table_args__ = (
        UniqueConstraint("email", name="uq_shop_customer_email"),
        UniqueConstraint("messenger_psid", name="uq_shop_customer_psid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    messenger_psid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    incoming_messages: Mapped[list["IncomingMessage"]] = relationship(back_populates="customer")
    orders: Mapped[list["OrderDraft"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "shop_products"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    sku: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=23)
    active: Mapped[bool] = mapped_column(default=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock_balances: Mapped[list["StockBalance"]] = relationship(back_populates="product")
    order_lines: Mapped[list["OrderLine"]] = relationship(back_populates="product")


class Warehouse(Base):
    __tablename__ = "shop_warehouses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock_balances: Mapped[list["StockBalance"]] = relationship(back_populates="warehouse")


class StockBalance(Base):
    __tablename__ = "shop_stock_balances"
    __table_args__ = (UniqueConstraint("product_id", "warehouse_id", name="uq_shop_stock_product_warehouse"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("shop_products.id", ondelete="CASCADE"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("shop_warehouses.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    product: Mapped["Product"] = relationship(back_populates="stock_balances")
    warehouse: Mapped["Warehouse"] = relationship(back_populates="stock_balances")


class IncomingMessage(Base):
    __tablename__ = "shop_incoming_messages"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_shop_message_provider_external"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new", index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attachment_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("shop_customers.id", ondelete="SET NULL"), nullable=True, index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped[Customer | None] = relationship(back_populates="incoming_messages")
    processing_attempts: Mapped[list["ProcessingAttempt"]] = relationship(back_populates="message")


class OrderDraft(Base):
    __tablename__ = "shop_orders"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("shop_customers.id", ondelete="SET NULL"), nullable=True, index=True)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("shop_incoming_messages.id", ondelete="SET NULL"), nullable=True, index=True)
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("shop_warehouses.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    total_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_gross: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    invoice_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    invoice_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Customer | None] = relationship(back_populates="orders")
    source_message: Mapped[IncomingMessage | None] = relationship(
        foreign_keys="OrderDraft.source_message_id"
    )
    warehouse: Mapped[Warehouse | None] = relationship()
    lines: Mapped[list["OrderLine"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    invoice: Mapped["InvoiceDocument | None"] = relationship(back_populates="order", cascade="all, delete-orphan", uselist=False)


class OrderLine(Base):
    __tablename__ = "shop_order_lines"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("shop_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("shop_products.id", ondelete="SET NULL"), nullable=True, index=True)
    sku_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=23)
    line_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_gross: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="confirmed", index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[OrderDraft] = relationship(back_populates="lines")
    product: Mapped[Product | None] = relationship(back_populates="order_lines")


class InvoiceDocument(Base):
    __tablename__ = "shop_invoices"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("shop_orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[OrderDraft] = relationship(back_populates="invoice")


class ProcessingAttempt(Base):
    __tablename__ = "shop_processing_attempts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("shop_incoming_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message: Mapped[IncomingMessage] = relationship(back_populates="processing_attempts")
