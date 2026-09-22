"""Session flash helpers for Shop Admin."""
from __future__ import annotations

from fastapi import Request


def flash(request: Request, message: str, category: str = "info") -> None:
    session = request.session
    session.setdefault("flash", []).append({"message": message, "category": category})


def get_flash(request: Request):
    flashes = request.session.pop("flash", None)
    return flashes[-1] if flashes else None
