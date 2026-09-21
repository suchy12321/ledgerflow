"""Document-level endpoints. List + delete (RODO)."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from mimetypes import guess_type
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models.document import Document

router = APIRouter(prefix="/api/documents", tags=["documents"])
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _document_file_response(document: Document, *, inline: bool) -> FileResponse:
    if not document.storage_path:
        raise HTTPException(status_code=404, detail="document file not found")

    path = Path(document.storage_path)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    path = path.resolve()

    upload_root = settings.upload_dir.resolve()
    try:
        path.relative_to(upload_root)
    except ValueError:
        raise HTTPException(status_code=404, detail="document file not found")

    if not path.is_file():
        raise HTTPException(status_code=404, detail="document file not found")

    media_type = (
        "application/pdf"
        if path.suffix.lower() == ".pdf"
        else guess_type(path.name)[0] or "application/octet-stream"
    )
    filename = document.filename or path.name or "document"
    return FileResponse(
        path=path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline" if inline else "attachment",
    )


@router.get("")
async def list_documents(
    client_id: uuid.UUID | None = None,
    period: str | None = None,
    type: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Document)
    if client_id:
        stmt = stmt.where(Document.client_id == client_id)
    if period:
        stmt = stmt.where(Document.period == period)
    if type:
        stmt = stmt.where(Document.type == type)
    rows = (await session.execute(stmt.order_by(Document.created_at.desc()))).scalars().all()
    return [
        {
            "id": str(d.id),
            "email_id": str(d.email_id),
            "client_id": str(d.client_id) if d.client_id else None,
            "type": d.type,
            "period": d.period,
            "confidence": d.confidence,
            "filename": d.filename,
        }
        for d in rows
    ]


@router.get("/{document_id}/view")
async def view_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Open the stored file in the browser's native viewer."""
    document = await session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    return _document_file_response(document, inline=True)


@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Download the stored file instead of opening it inline."""
    document = await session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    return _document_file_response(document, inline=False)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """RODO: permanently remove a document and its file."""
    doc = await session.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "document not found")
    if doc.storage_path:
        try:
            Path(doc.storage_path).unlink(missing_ok=True)
        except OSError:
            pass
    await session.delete(doc)
    await session.commit()
    return None