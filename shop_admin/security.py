"""Small security helpers kept local to Shop Admin."""
from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path

from .config import settings


def verify_hmac_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret:
        return False
    supplied = signature.removeprefix("sha256=")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


def safe_filename(filename: str | None, fallback: str = "attachment") -> str:
    name = Path(filename or fallback).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:180] or fallback


def redact_for_log(value: str, limit: int = 160) -> str:
    compact = " ".join((value or "").split())
    return compact[:limit]
