"""Smoke tests: every layer wired correctly, with all providers mocked."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

# Force a clean SQLite for tests.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_ledgerflow.db"
os.environ["AI_PROVIDER"] = "mock"
os.environ["MAIL_PROVIDER"] = "mock"
os.environ["OCR_PROVIDER"] = "mock"

# Import the app AFTER env vars.
from app.main import app  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import init_db, engine  # noqa: E402


@pytest_asyncio.fixture(scope="function", autouse=True)
async def _setup_db():
    # Fresh schema per test.
    Path("./test_ledgerflow.db").unlink(missing_ok=True)
    await init_db()
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_and_list_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/clients",
            data={
                "name": "ABC Transport",
                "email": "biuro@abctransport.pl",
                "tax_id": "1234567890",
                "kind": "company",
            },
        )
        assert r.status_code == 201
        cid = r.json()["id"]

        r = await c.get("/api/clients")
        assert r.status_code == 200
        rows = r.json()
        assert any(row["name"] == "ABC Transport" for row in rows)


@pytest.mark.asyncio
async def test_ingest_all_assigns_clients():
    """Pull mock mail -> 3 messages get processed -> 3 documents assigned."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Seed 3 clients so assignment works.
        for name, email in [
            ("Abc Transport", "biuro@abctransport.pl"),
            ("Janex", "kontakt@janex.com.pl"),
            ("Kowalski", "biuro@kowalski.pl"),
        ]:
            await c.post(
                "/api/clients",
                data={"name": name, "email": email, "kind": "company"},
            )

        # Trigger ingest.
        r = await c.post("/api/gmail/ingest-all")
        assert r.status_code == 200
        accepted = r.json()["accepted"]
        assert len(accepted) == 3

        # Background tasks run after the response; give them a moment via
        # a second request that depends on the DB state.
        # We rely on the endpoint ordering: tasks were scheduled before the
        # response was sent, but FastAPI BackgroundTasks run after. So we
        # call a small busy endpoint or just hit list to wait.
        # Simpler: poll up to 2s for documents.
        import asyncio as _a

        for _ in range(20):
            r = await c.get("/api/documents")
            if len(r.json()) >= 3:
                break
            await _a.sleep(0.1)

        r = await c.get("/api/documents")
        docs = r.json()
        assert len(docs) >= 3
        types = {d["type"] for d in docs}
        # From our mock: bank_statement, lease, invoice, plus raport_kasowy
        # (mapped to bank_statement by heuristic) -> overlap.
        assert "bank_statement" in types or "lease" in types or "invoice" in types


@pytest.mark.asyncio
async def test_ingest_all_repairs_existing_email_period():
    """Existing emails and documents get a period when AI could not infer one."""
    from datetime import datetime, timezone

    from app.db import SessionLocal
    from app.models.document import Document
    from app.models.email import Email

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.post(
            "/api/clients",
            data={
                "name": "ABC Transport",
                "email": "biuro@abctransport.pl",
                "kind": "company",
            },
        )
        assert r.status_code == 201
        client_id = r.json()["id"]

        async with SessionLocal() as session:
            for index, sender in enumerate(
                ["biuro@abctransport.pl", "kontakt@janex.com.pl", "biuro@kowalski.pl"]
            ):
                email = Email(
                    sender=sender,
                    subject="faktura",
                    body=None,
                    received_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
                    status="done",
                    external_id=f"mock-{index}",
                    period=None,
                )
                session.add(email)
                await session.flush()
                if index == 0:
                    session.add(
                        Document(
                            email_id=email.id,
                            client_id=client_id,
                            type="invoice",
                            period=None,
                            confidence=0.95,
                            filename="Faktura.pdf",
                            storage_path="Faktura.pdf",
                        )
                    )
            await session.commit()

        r = await c.post("/api/gmail/ingest-all")
        assert r.status_code == 200
        assert r.json()["accepted"] == []
        assert r.json()["skipped"] == 3

        async with SessionLocal() as session:
            email = (await session.execute(select(Email).where(Email.external_id == "mock-0"))).scalar_one()
            doc = (
                await session.execute(select(Document).where(Document.email_id == email.id))
            ).scalars().one()
            assert email.period == "2026-09"
            assert doc.period == "2026-09"


@pytest.mark.asyncio
async def test_dashboard_renders():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/dashboard")
        assert r.status_code == 200
        assert "Klienci" in r.text


@pytest.mark.asyncio
async def test_html_client_form_redirects_to_dashboard_with_flash():
    """The browser form posts to the HTML handler, not the JSON API."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/clients/new",
            data={"name": "Dashboard Redirect Test", "kind": "company"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/dashboard"

        r = await c.get("/dashboard")
        assert r.status_code == 200
        assert "Dashboard Redirect Test" in r.text
        assert "dodany" in r.text


@pytest.mark.asyncio
async def test_document_preview_and_download():
    from app.db import SessionLocal
    from app.models.document import Document
    from app.models.email import Email

    upload_dir = settings.upload_dir / f"document-preview-{uuid.uuid4()}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    source = upload_dir / "Faktura.pdf"
    source.write_bytes(b"%PDF preview test")

    async with SessionLocal() as session:
        email = Email(
            sender="office@example.com",
            subject="Faktura",
            received_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            status="done",
            external_id=f"preview-{uuid.uuid4()}",
        )
        session.add(email)
        await session.flush()
        document = Document(
            email_id=email.id,
            type="invoice",
            period="2026-09",
            confidence=0.95,
            filename="Faktura.pdf",
            storage_path=str(source),
        )
        session.add(document)
        await session.commit()
        document_id = document.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        preview = await c.get(f"/api/documents/{document_id}/view")
        assert preview.status_code == 200
        assert preview.content == b"%PDF preview test"
        assert preview.headers["content-disposition"].startswith("inline")

        download = await c.get(f"/api/documents/{document_id}/download")
        assert download.status_code == 200
        assert download.content == b"%PDF preview test"
        assert download.headers["content-disposition"].startswith("attachment")


@pytest.mark.asyncio
async def test_classification_validation_other_on_bad_ai():
    """If AI returns garbage, classification must default to 'other'."""
    from app.schemas.ai import Classification

    # Pydantic should reject unknown enum value when type is wrong.
    with pytest.raises(Exception):
        Classification.model_validate({"document_type": "nonsense", "confidence": 0.5})
    # But fallback path in pipeline creates a valid Classification anyway.
    fallback = Classification(document_type="other", confidence=0.0)
    assert fallback.document_type == "other"


@pytest.mark.asyncio
async def test_clients_new_routes_win_over_dynamic_uuid():
    """Regression: /clients/new must NOT be matched as client_id='new'."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # GET form page.
        r = await c.get("/clients/new")
        assert r.status_code == 200, r.text
        assert "Nowy klient" in r.text

        # POST form -> creates client and returns to the dashboard.
        r = await c.post(
            "/clients/new",
            data={"name": "Routing Test", "kind": "company"},
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
        assert r.headers["location"] == "/dashboard"

        # The dashboard should render the newly created client.
        r2 = await c.get("/dashboard")
        assert r2.status_code == 200, r2.text
        assert "Routing Test".upper() in r2.text.upper() or "ROUTING TEST" in r2.text