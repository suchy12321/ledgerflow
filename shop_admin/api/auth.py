"""Simple token-backed administrator login."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..config import settings
from .common import render


router = APIRouter(prefix="/shop", tags=["auth"])


@router.get("/login")
async def login_form(request: Request):
    if request.session.get("shop_admin_authenticated"):
        return RedirectResponse("/shop/dashboard", status_code=303)
    return render(request, "login.html", error=None)


@router.post("/login")
async def login(request: Request):
    form = await request.form()
    supplied = str(form.get("token") or "")
    if not hmac.compare_digest(supplied, settings.admin_token):
        return render(request, "login.html", error="Nieprawidłowy token administratora.", status_code=401)
    request.session["shop_admin_authenticated"] = True
    return RedirectResponse("/shop/dashboard", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.pop("shop_admin_authenticated", None)
    return RedirectResponse("/shop/login", status_code=303)
