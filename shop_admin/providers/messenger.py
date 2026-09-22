"""Meta Messenger webhook normalization and signature verification."""
from __future__ import annotations

from datetime import datetime, timezone

from ..security import verify_hmac_signature
from .channels import IncomingMessage


def normalize_messenger_event(payload: dict, app_secret: str, raw_body: bytes, signature: str | None) -> list[IncomingMessage]:
    if not verify_hmac_signature(raw_body, signature, app_secret):
        raise ValueError("Nieprawidłowy podpis wiadomości Messenger.")

    messages: list[IncomingMessage] = []
    for entry in payload.get("entry", []) or []:
        for item in entry.get("messaging", []) or []:
            sender = (item.get("sender") or {}).get("id")
            text = (item.get("message") or {}).get("text") or ""
            mid = item.get("mid") or item.get("message", {}).get("mid")
            if not sender or not text or not mid:
                continue
            timestamp = item.get("timestamp")
            received_at = None
            if timestamp:
                received_at = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).isoformat()
            messages.append(
                IncomingMessage(
                    provider="messenger",
                    external_id=str(mid),
                    sender=f"messenger:{sender}",
                    recipient=None,
                    subject=None,
                    body=text,
                    received_at=received_at,
                    raw_payload=item,
                )
            )
    return messages


def messenger_verification_token(payload: dict, expected: str) -> bool:
    return payload.get("hub.mode") == "subscribe" and payload.get("hub.verify_token") == expected


def verification_challenge(payload: dict) -> str | None:
    return payload.get("hub.challenge")
