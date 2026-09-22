"""Channel contracts and normalized inbound messages."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class IncomingAttachment:
    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"
    attachment_id: str | None = None


@dataclass
class IncomingMessage:
    provider: str
    external_id: str
    sender: str
    subject: str | None
    body: str
    received_at: str | None = None
    recipient: str | None = None
    attachments: list[IncomingAttachment] = field(default_factory=list)
    raw_payload: dict | None = None


class InboundChannel(ABC):
    @abstractmethod
    async def list_recent(self, max_results: int = 20) -> list[IncomingMessage]: ...

    @abstractmethod
    async def fetch_message(self, message_id: str) -> IncomingMessage: ...


def attachment_metadata(message: IncomingMessage) -> dict | None:
    if not message.attachments:
        return None
    return {
        "attachments": [
            {
                "filename": item.filename,
                "mime_type": item.mime_type,
                "size": len(item.content),
            }
            for item in message.attachments
        ]
    }
