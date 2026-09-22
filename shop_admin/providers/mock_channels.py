"""Deterministic demo channels for local development and tests."""
from __future__ import annotations

from .channels import InboundChannel, IncomingAttachment, IncomingMessage


class DemoEmailProvider:
    """Small shop inbox; replace with GmailProvider for production."""

    async def list_recent(self, max_results: int = 20) -> list:
        return [_email(0), _email(1)][:max_results]

    async def fetch_message(self, message_id: str):
        for index in range(2):
            if message_id == f"demo-email-{index}":
                return _email(index)
        raise KeyError(message_id)


class DemoMessengerChannel(InboundChannel):
    async def list_recent(self, max_results: int = 20) -> list[IncomingMessage]:
        return [_messenger()]

    async def fetch_message(self, message_id: str) -> IncomingMessage:
        if message_id != "demo-messenger-1":
            raise KeyError(message_id)
        return _messenger()


def _email(index: int) -> object:
    if index == 0:
        body = (
            "Dzień dobry, proszę przygotować zamówienie dla Anny: "
            "2x KAWA-1KG, 3x FILIZANKA-BIALA oraz 1x CUKIER-1KG. "
            "Magazyn: MAIN. Dziękuję!"
        )
        sender = "anna@example.pl"
        subject = "Zamówienie od Anny"
    else:
        body = "Poproszę 10x KAWA-1KG. Magazyn: MAIN."
        sender = "biuro@example.pl"
        subject = "Zamówienie z niedoborem"
    return type(
        "DemoMail",
        (),
        {
            "external_id": f"demo-email-{index}",
            "sender": sender,
            "subject": subject,
            "body": body,
            "received_at": "2026-09-19T10:00:00+00:00",
            "attachments": [],
        },
    )()


def _messenger() -> IncomingMessage:
    return IncomingMessage(
        provider="messenger",
        external_id="demo-messenger-1",
        sender="messenger:demo-psid",
        subject=None,
        body="Cześć, poproszę 2x KAWA-1KG i 1x CUKIER-1KG. Magazyn MAIN.",
        received_at="2026-09-19T11:00:00+00:00",
        raw_payload={"sender": {"id": "demo-psid"}, "message": {"mid": "demo-messenger-1", "text": ""}},
    )
