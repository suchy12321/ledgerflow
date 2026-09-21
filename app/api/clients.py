"""Client CRUD + per-month detail endpoints."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from pathlib import Path

from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from requests import request, session

from app.utils.flash import flash
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db import get_session
from app.models.client import Client
from app.models.document import Document
from app.models.email import Email
from app.services.ai_service import AIService
from app.services.ledger_service import LedgerService, normalize_period
from app.services.reply_service import ReplyService

router = APIRouter(prefix="/api/clients", tags=["clients"])
pages = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


# ---------- API -----------------------------------------------------------

@router.get("")
async def list_clients(session: AsyncSession = Depends(get_session)):
    """List clients with their missing-doc list for the current period."""
    ledger = LedgerService(session)
    period = _period_now()
    rows = (await session.execute(select(Client).order_by(Client.name))).scalars().all()
    out = []
    for c in rows:
        missing = await ledger.find_missing(str(c.id), period)
        out.append(
            {
                "id": str(c.id),
                "name": c.name,
                "email": c.email,
                "tax_id": c.tax_id,
                "kind": c.kind,
                "missing": missing,
            }
        )
    return out


@router.post("", status_code=201)
async def create_client(
    request: Request,
    name: Annotated[str, Form()],
    email: Annotated[str | None, Form()] = None,
    tax_id: Annotated[str | None, Form()] = None,
    kind: Annotated[str, Form()] = "company",
    notes: Annotated[str | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
):
    client = Client(name=name, email=email, tax_id=tax_id, kind=kind, notes=notes)
    session.add(client)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback() # Cofnij zepsutą transakcję
        if "flash" not in request.session:
            request.session["flash"] = []
        request.session["flash"].append({"type": "error", "message": "Klient z tym adresem e-mail już istnieje."})
        
        # Przekieruj z powrotem do formularza (kod 303 zamienia POST na GET)
        return RedirectResponse(url="/clients/new", status_code=303)
    
    # W przypadku sukcesu również możesz dodać flash message i przekierować na listę
    if "flash" not in request.session:
        request.session["flash"] = []
    request.session["flash"].append({"type": "success", "message": "Dodano nowego klienta."})

    return JSONResponse(status_code=201, content={"id": str(client.id), "status": "created"})


@router.get("/{client_id}/documents")
async def list_client_documents(
    client_id: uuid.UUID,
    period: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    period = normalize_period(period) or _period_now()
    rows = (
        await session.execute(
            select(Document)
            .where(Document.client_id == client_id, Document.period == period)
            .order_by(Document.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(d.id),
            "type": d.type,
            "period": d.period,
            "confidence": d.confidence,
            "filename": d.filename,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in rows
    ]


@router.get("/{client_id}/detail")
async def client_detail(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Composite view: docs + last email + draft reply for the current period."""
    period = _period_now()
    ledger = LedgerService(session)
    received = await ledger.received_for_period(str(client_id), period)
    missing = await ledger.find_missing(str(client_id), period)

    client = await session.get(Client, client_id)
    if not client:
        raise HTTPException(404, "client not found")

    last_email_row = (
        await session.execute(
            select(Email)
            .where(Email.client_id == client_id)
            .order_by(Email.received_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    docs = (
        await session.execute(
            select(Document)
            .where(Document.client_id == client_id, Document.period == period)
            .order_by(Document.created_at.desc())
        )
    ).scalars().all()

    reply = await ReplyService(AIService(), ledger).draft(
        str(client_id), client.name, period
    )

    return {
        "id": str(client.id),
        "name": client.name,
        "email": client.email,
        "tax_id": client.tax_id,
        "kind": client.kind,
        "period": period,
        "received": received,
        "missing": missing,
        "documents": [
            {
                "id": str(d.id),
                "type": d.type,
                "filename": d.filename,
                "confidence": d.confidence,
            }
            for d in docs
        ],
        "last_email": {
            "id": str(last_email_row.id),
            "sender": last_email_row.sender,
            "subject": last_email_row.subject,
            "received_at": last_email_row.received_at.isoformat(),
            "ai_summary": last_email_row.ai_summary,
            "status": last_email_row.status,
            "documents": [
                {
                    "id": str(d.id),
                    "type": d.type,
                    "period": d.period,
                    "confidence": d.confidence,
                    "filename": d.filename,
                }
                for d in (
                    await session.execute(
                        select(Document).where(Document.email_id == last_email_row.id)
                    )
                ).scalars().all()
            ],
        }
        if last_email_row
        else None,
        "draft_reply": reply,
    }


@router.post("/{client_id}/delete", status_code=303)
async def delete_client(
    client_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """RODO: permanent deletion."""
    client = await session.get(Client, client_id)
    if not client:
        raise HTTPException(404, "client not found")
    # Detach docs + emails (FKs are SET NULL / CASCADE per model).
    await session.delete(client)
    await session.commit()
    if request.headers.get("accept", "").startswith("text/html"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return {"deleted": str(client_id)}


# ---------- HTML pages ----------------------------------------------------

@pages.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    period = _period_now()
    ledger = LedgerService(session)
    rows = (await session.execute(select(Client).order_by(Client.name))).scalars().all()
    clients_view = []
    for c in rows:
        missing = await ledger.find_missing(str(c.id), period)
        clients_view.append(
            {
                "id": str(c.id),
                "name": c.name,
                "email": c.email,
                "kind": c.kind,
                "missing": missing,
                "complete": not missing,
            }
        )
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "clients": clients_view, "period": period},
    )


@pages.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse(url="/dashboard", status_code=303)


# IMPORTANT: static `/clients/new` must be registered BEFORE `/clients/{client_id}`,
# otherwise FastAPI matches the dynamic path and tries to parse "new" as UUID.
@pages.get("/clients/new", response_class=HTMLResponse)
async def new_client_form(request: Request):
    return templates.TemplateResponse("new_client.html", {"request": request})


@pages.post("/clients/new")
async def create_client_html(
    request: Request,
    name: Annotated[str, Form()],
    email: Annotated[str | None, Form()] = None,
    tax_id: Annotated[str | None, Form()] = None,
    kind: Annotated[str, Form()] = "company",
    notes: Annotated[str | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
):
    # Check if client with this email already exists
    if email:
        existing = (
            await session.execute(
                select(Client).where(Client.email == email.strip())
            )
        ).scalar_one_or_none()
        if existing:
            flash(request, f"Klient o emailu „{email}” już istnieje.", "error")
            return RedirectResponse(url="/dashboard", status_code=303)

    client = Client(name=name, email=email, tax_id=tax_id, kind=kind, notes=notes)
    session.add(client)
    await session.commit()
    flash(request, f"Klient „{client.name}” dodany.", "success")
    return RedirectResponse(url="/dashboard", status_code=303)


@pages.get("/clients/{client_id}/edit", response_class=HTMLResponse)
async def edit_client_form(
    client_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    client = await session.get(Client, client_id)
    if not client:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "edit_client.html",
        {"request": request, "client": client},
    )


@pages.post("/clients/{client_id}/edit")
async def update_client_html(
    client_id: uuid.UUID,
    request: Request,
    name: Annotated[str, Form()],
    email: Annotated[str | None, Form()] = None,
    tax_id: Annotated[str | None, Form()] = None,
    kind: Annotated[str, Form()] = "company",
    notes: Annotated[str | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
):
    client = await session.get(Client, client_id)
    if not client:
        raise HTTPException(404)
    client.name = name
    client.email = email
    client.tax_id = tax_id
    client.kind = kind
    client.notes = notes
    await session.commit()
    flash(request, f"Klient „{client.name}” zaktualizowany.", "success")
    return RedirectResponse(url=f"/clients/{client.id}", status_code=303)


@pages.get("/clients/{client_id}", response_class=HTMLResponse)
async def client_page(
    client_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    period = _period_now()
    ledger = LedgerService(session)
    client = await session.get(Client, client_id)
    if not client:
        raise HTTPException(404)
    received = await ledger.received_for_period(str(client_id), period)
    missing = await ledger.find_missing(str(client_id), period)

    last_email = (
        await session.execute(
            select(Email)
            .where(Email.client_id == client_id)
            .order_by(Email.received_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    docs = (
        await session.execute(
            select(Document)
            .where(Document.client_id == client_id, Document.period == period)
            .order_by(Document.created_at.desc())
        )
    ).scalars().all()

    last_email_docs = []
    if last_email:
        last_email_docs = list(
            (
                await session.execute(
                    select(Document).where(Document.email_id == last_email.id)
                )
            ).scalars().all()
        )

    reply = await ReplyService(AIService(), ledger).draft(
        str(client_id), client.name, period
    )

    return templates.TemplateResponse(
        "client.html",
        {
            "request": request,
            "client": client,
            "period": period,
            "received": received,
            "missing": missing,
            "documents": docs,
            "last_email": last_email,
            "last_email_docs": last_email_docs,
            "draft_reply": reply,
        },
    )


def _period_now() -> str:
    from datetime import datetime

    return datetime.utcnow().strftime("%Y-%m")