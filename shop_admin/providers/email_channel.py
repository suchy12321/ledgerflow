"""Email adapter built on LedgerFlow's mail provider contract."""
from __future__ import annotations

from .channels import InboundChannel, IncomingAttachment, IncomingMessage


class EmailChannel(InboundChannel):
    def __init__(self, provider) -> None:
        self._provider = provider

    async def list_recent(self, max_results: int = 20) -> list[IncomingMessage]:
        rows = await self._provider.list_recent(max_results=max_results)
        return [_normalize(row) for row in rows]

    async def fetch_message(self, message_id: str) -> IncomingMessage:
        return _normalize(await self._provider.fetch_message(message_id))


def _normalize(row) -> IncomingMessage:
    attachments = [
        IncomingAttachment(
            filename=item.filename,
            content=item.content,
            mime_type=item.mime_type,
            attachment_id=item.attachment_id,
        )
        for item in getattr(row, "attachments", [])
    ]
    return IncomingMessage(
        provider="email",
        external_id=str(getattr(row, "external_id") or getattr(row, "id")),
        sender=getattr(row, "sender") or "",
        subject=getattr(row, "subject") or None,
        body=getattr(row, "body") or "",
        received_at=getattr(row, "received_at") or None,
        attachments=attachments,
        raw_payload=None,
    )


def create_email_channel(settings):
    if settings.mail_provider == "gmail":
        from app.providers.mail import GmailProvider

        missing = [
            name
            for name, value in (
                ("GOOGLE_CLIENT_ID", settings.google_client_id),
                ("GOOGLE_CLIENT_SECRET", settings.google_client_secret),
                ("GOOGLE_REFRESH_TOKEN", settings.google_refresh_token),
            )
            if not str(value or "").strip()
        ]
        if missing:
            raise RuntimeError("SHOP_ADMIN_MAIL_PROVIDER=gmail wymaga: " + ", ".join(missing))
        provider = GmailProvider(
            settings.google_client_id.strip(),
            settings.google_client_secret.strip(),
            settings.google_refresh_token.strip(),
        )
    else:
        from .mock_channels import DemoEmailProvider

        provider = DemoEmailProvider()
    return EmailChannel(provider)
