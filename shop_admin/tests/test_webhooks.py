import hashlib
import hmac
import json

import pytest
from sqlalchemy import func, select

from shop_admin.config import settings
from shop_admin.db import SessionLocal
from shop_admin.models import IncomingMessage
from shop_admin.seed import seed_demo_data


@pytest.mark.asyncio
async def test_messenger_webhook_rejects_bad_signature_and_accepts_valid_event(client, db_session):
    await seed_demo_data(db_session)
    await db_session.commit()
    await db_session.close()
    payload = {
        "object": "page",
        "entry": [
            {
                "messaging": [
                    {
                        "sender": {"id": "demo-psid"},
                        "message": {
                            "mid": "messenger-valid-1",
                            "text": "Poproszę 1x CUKIER-1KG. Magazyn MAIN.",
                        },
                        "timestamp": 1789900000000,
                    }
                ]
            }
        ],
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    bad_signature = "sha256=" + hashlib.sha256(raw_body + b"tampered").hexdigest()
    rejected = await client.post(
        "/api/webhooks/messenger",
        content=raw_body,
        headers={"X-Hub-Signature-256": bad_signature},
    )

    assert rejected.status_code == 401

    signature = "sha256=" + hmac.new(
        settings.messenger_app_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    accepted = await client.post(
        "/api/webhooks/messenger",
        content=raw_body,
        headers={
            "X-Hub-Signature-256": signature,
            "content-type": "application/json",
        },
    )
    async with SessionLocal() as session:
        incoming = await session.scalar(
            select(IncomingMessage).where(IncomingMessage.external_id == "messenger-valid-1")
        )

    assert accepted.json() == {"accepted": 1}
    assert incoming.provider == "messenger"
    assert incoming.status == "ready_for_approval"


@pytest.mark.asyncio
async def test_messenger_verification_challenge(client):
    response = await client.get(
        "/api/webhooks/messenger",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.messenger_verify_token,
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 200
    assert response.text == "challenge-123"


@pytest.mark.asyncio
async def test_email_webhook_requires_secret_and_is_idempotent(client, db_session):
    await seed_demo_data(db_session)
    await db_session.commit()
    await db_session.close()
    unauthorized = await client.post("/api/webhooks/email", json={})
    assert unauthorized.status_code == 401

    headers = {"X-ShopAdmin-Secret": settings.mail_webhook_secret}
    first = await client.post("/api/webhooks/email", json={}, headers=headers)
    second = await client.post("/api/webhooks/email", json={}, headers=headers)
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count(IncomingMessage.id)))

    assert first.json() == {"accepted": 2}
    assert second.json() == {"accepted": 2}
    assert count == 2
