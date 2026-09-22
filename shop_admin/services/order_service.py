"""Order intake, validation, approval, and retry workflow."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..models import (
    IncomingMessage,
    InvoiceDocument,
    OrderDraft,
    OrderLine,
    ProcessingAttempt,
    Product,
    Warehouse,
)
from ..providers.channels import IncomingMessage as ChannelMessage
from ..schemas import OrderBuildResult, ParsedOrder
from .customer_matcher import CustomerMatcher
from .invoice_service import InvoiceService
from .message_service import MessageService
from .order_parser import RuleOrderParser
from .stock_service import StockService


CENT = Decimal("0.01")


class OrderIngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.parser = RuleOrderParser()
        self.matcher = CustomerMatcher(session)
        self.stock = StockService(session)
        self.invoices = InvoiceService()
        self.messages = MessageService()

    async def ingest(self, message: ChannelMessage) -> OrderBuildResult:
        existing = await self.session.scalar(
            select(IncomingMessage).where(
                IncomingMessage.provider == message.provider,
                IncomingMessage.external_id == message.external_id,
            )
        )
        if existing:
            return OrderBuildResult(order_id=str(existing.order_id), status=existing.status)

        row = IncomingMessage(
            provider=message.provider,
            external_id=message.external_id,
            sender=message.sender,
            recipient=message.recipient,
            subject=message.subject,
            body=message.body,
            status="processing",
            raw_payload=message.raw_payload,
        )
        self.session.add(row)
        await self.session.flush()
        try:
            parsed = await self.parser.parse(message)
            result = await self._build(row, parsed)
            row.status = result.status
            row.order_id = result.order_id if result.order_id else None
            self.session.add(
                ProcessingAttempt(
                    message_id=row.id,
                    outcome="ok" if result.status == "ready_for_approval" else "review",
                    attempt_no=1,
                )
            )
            await self.session.flush()
            return result
        except Exception as exc:
            row.status = "error"
            self.session.add(
                ProcessingAttempt(message_id=row.id, outcome="error", error=str(exc)[:2000], attempt_no=1)
            )
            raise

    async def retry(self, message_id) -> OrderBuildResult:
        row = await self.session.get(IncomingMessage, message_id)
        if not row:
            raise KeyError("wiadomość nie istnieje")
        message = ChannelMessage(
            provider=row.provider,
            external_id=row.external_id,
            sender=row.sender,
            subject=row.subject,
            body=row.body or "",
            raw_payload=row.raw_payload,
        )
        parsed = await self.parser.parse(message)
        result = await self._build(row, parsed, replace_existing=True)
        row.status = result.status
        count = await self.session.scalar(
            select(func.count(ProcessingAttempt.id)).where(ProcessingAttempt.message_id == row.id)
        )
        self.session.add(
            ProcessingAttempt(
                message_id=row.id,
                outcome="ok" if result.status == "ready_for_approval" else "review",
                attempt_no=(count or 0) + 1,
            )
        )
        await self.session.flush()
        return result

    async def _build(
        self,
        message: IncomingMessage,
        parsed: ParsedOrder,
        replace_existing: bool = False,
    ) -> OrderBuildResult:
        warehouse_code = parsed.warehouse_code or settings.default_warehouse_code
        warehouse = await self.session.scalar(
            select(Warehouse).where(Warehouse.code == warehouse_code, Warehouse.active.is_(True))
        )
        issues: list[str] = []
        if warehouse is None:
            warehouse = await self.session.scalar(select(Warehouse).order_by(Warehouse.id))
            if warehouse is None:
                issues.append("Brak aktywnego magazynu.")
        customer = await self.matcher.resolve(parsed, message.sender)
        if customer is None:
            issues.append("Nie udało się jednoznacznie dopasować klienta.")

        items: list[tuple[Product | None, int, str]] = []
        lines: list[OrderLine] = []
        for item in parsed.lines:
            product = await self.session.scalar(
                select(Product).where(Product.sku == item.sku.upper(), Product.active.is_(True))
            )
            if product is None and item.product_name:
                product = await self.session.scalar(
                    select(Product).where(
                        Product.name == item.product_name,
                        Product.active.is_(True),
                    )
                )
            if product is None:
                issues.append(f"Nie znaleziono produktu {item.sku}.")
            items.append((product, item.quantity, item.sku))
            if product:
                net = (product.unit_price * item.quantity).quantize(CENT)
                vat = (net * product.vat_rate / Decimal("100")).quantize(
                    CENT, rounding=ROUND_HALF_UP
                )
                lines.append(
                    OrderLine(
                        product_id=product.id,
                        sku_snapshot=product.sku,
                        name_snapshot=product.name,
                        quantity=item.quantity,
                        unit_price=product.unit_price,
                        vat_rate=product.vat_rate,
                        line_net=net,
                        line_vat=vat,
                        line_gross=(net + vat).quantize(CENT, rounding=ROUND_HALF_UP),
                        status="confirmed",
                        confidence=item.confidence,
                    )
                )
            else:
                lines.append(
                    OrderLine(
                        sku_snapshot=item.sku,
                        name_snapshot=item.product_name or item.sku,
                        quantity=item.quantity,
                        unit_price=0,
                        vat_rate=Decimal("23"),
                        line_net=Decimal("0.00"),
                        line_vat=Decimal("0.00"),
                        line_gross=Decimal("0.00"),
                        status="manual",
                        confidence=item.confidence,
                    )
                )

        if not parsed.lines:
            issues.append("Nie rozpoznano żadnej pozycji zamówienia.")
        if parsed.confidence < settings.parser_confidence_threshold:
            issues.append("Zbyt niska pewność parsera.")

        stock_result = None
        if warehouse and items:
            stock_result = await self.stock.check(warehouse, items)
            for check in stock_result.checks:
                if not check.sufficient:
                    issues.append(f"Za mało w magazynie: {check.sku} ({check.available}/{check.requested}).")
            for line, check in zip(lines, stock_result.checks):
                line.status = "confirmed" if check.sufficient else "unavailable"

        if replace_existing and message.order_id:
            order = await self.session.get(OrderDraft, message.order_id)
            if order:
                old_lines = (
                    await self.session.execute(
                        select(OrderLine).where(OrderLine.order_id == order.id)
                    )
                ).scalars().all()
                for old_line in old_lines:
                    await self.session.delete(old_line)
                invoice = await self.session.scalar(
                    select(InvoiceDocument).where(InvoiceDocument.order_id == order.id)
                )
                if invoice:
                    await self.session.delete(invoice)
        else:
            order = OrderDraft(
                customer_id=customer.id if customer else None,
                source_message_id=message.id,
                warehouse_id=warehouse.id if warehouse else None,
                status="draft",
            )
            self.session.add(order)
        await self.session.flush()
        for line in lines:
            line.order_id = order.id
            self.session.add(line)
        order.total_net = sum((line.line_net for line in lines), Decimal("0"))
        order.total_vat = sum((line.line_vat for line in lines), Decimal("0"))
        order.total_gross = sum((line.line_gross for line in lines), Decimal("0"))
        order.notes = parsed.notes
        order.customer_message = self.messages.draft_for(
            customer.name if customer else "Kliencie",
            lines,
            order.total_gross,
        )
        ready = not issues and stock_result is not None and stock_result.sufficient
        order.status = "ready_for_approval" if ready else "needs_review"
        message.customer_id = customer.id if customer else None
        message.order_id = order.id
        if ready:
            order.invoice_number = f"PROJEKT-{str(order.id)[:8].upper()}"
            invoice_path = self.invoices.generate(
                order,
                final=False,
                customer_name=customer.name if customer else "Nieprzypisany klient",
                customer_email=customer.email if customer and customer.email else "",
                lines=lines,
            )
            order.invoice_path = invoice_path
            self.session.add(
                InvoiceDocument(
                    order_id=order.id,
                    number=order.invoice_number,
                    path=invoice_path,
                    status="draft",
                )
            )
            order.message_status = "ready"
        else:
            order.invoice_path = None
            order.message_status = "draft"
        return OrderBuildResult(order_id=str(order.id), status=order.status, issues=issues)

    async def approve(self, order_id) -> OrderDraft:
        order = await self._loaded_order(order_id)
        if order.status != "ready_for_approval":
            raise ValueError("Zamówienie nie jest gotowe do zatwierdzenia.")
        if not order.customer or not order.warehouse:
            raise ValueError("Zamówienie wymaga klienta i magazynu.")
        items = [(line.product, line.quantity) for line in order.lines if line.product]
        if len(items) != len(order.lines):
            raise ValueError("Zamówienie zawiera nierozpoznane pozycje.")
        await self.stock.reserve(order.warehouse, items)
        order.status = "approved"
        order.message_status = "ready"
        order.approved_at = datetime.now(timezone.utc)
        order.invoice_number = f"RACHUNEK-{order.approved_at.strftime('%Y%m%d')}-{str(order.id)[:6].upper()}"
        invoice_path = self.invoices.generate(order, final=True)
        order.invoice_path = invoice_path
        invoice = order.invoice or InvoiceDocument(order_id=order.id, path=invoice_path)
        invoice.number = order.invoice_number
        invoice.status = "final"
        invoice.path = invoice_path
        self.session.add(invoice)
        return order

    async def reject(self, order_id) -> OrderDraft:
        order = await self._loaded_order(order_id)
        if order.status == "approved" and order.customer and order.warehouse:
            items = [(line.product, line.quantity) for line in order.lines if line.product]
            await self.stock.release(order.warehouse, items)
        order.status = "rejected"
        order.message_status = "draft"
        return order

    async def _loaded_order(self, order_id):
        return await self.session.scalar(
            select(OrderDraft)
            .where(OrderDraft.id == order_id)
            .options(
                selectinload(OrderDraft.customer),
                selectinload(OrderDraft.warehouse),
                selectinload(OrderDraft.lines).selectinload(OrderLine.product),
                selectinload(OrderDraft.invoice),
            )
        )
