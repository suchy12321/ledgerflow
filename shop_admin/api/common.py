"""Shared route helpers."""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from ..utils.flash import flash


templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def render(request: Request, name: str, *, status_code: int = 200, headers: dict[str, str] | None = None, **context):
    return templates.TemplateResponse(
        request,
        name,
        {"request": request, **context},
        status_code=status_code,
        headers=headers,
    )


def require_value(value: str, label: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"Pole „{label}” jest wymagane.")
    return value


def flash_error(request: Request, exc: Exception) -> None:
    flash(request, str(exc), "error")
