"""Shop Admin FastAPI entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from . import api
from .config import settings
from .db import dispose_engine, get_session, init_db
from .seed import seed_demo_data
from .utils.flash import get_flash


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    if settings.seed_demo:
        from .db import SessionLocal

        async with SessionLocal() as session:
            await seed_demo_data(session)
            await session.commit()
    yield
    await dispose_engine()


app = FastAPI(
    title="Shop Admin",
    version="0.1.0",
    description="Asystent zamówień sklepowych z akceptacją przed wysyłką.",
    lifespan=lifespan,
)

@app.middleware("http")
async def administrator_auth(request: Request, call_next):
    public = (
        request.url.path == "/healthz"
        or request.url.path.startswith("/api/webhooks")
        or request.url.path in {"/shop/login", "/shop"}
        or request.url.path.startswith("/docs")
        or request.url.path.startswith("/openapi")
    )
    if not public and not request.session.get("shop_admin_authenticated"):
        if request.url.path.startswith("/api/"):
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "Wymagane logowanie administratora."}, status_code=401)
        return RedirectResponse("/shop/login", status_code=303)
    request.state.flash = get_flash(request)
    return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=settings.is_production,
    same_site="lax",
)



app.include_router(api.auth_router)
app.include_router(api.dashboard_router)
app.include_router(api.inbox_router)
app.include_router(api.orders_router)
app.include_router(api.products_router)
app.include_router(api.warehouses_router)
app.include_router(api.customers_router)
app.include_router(api.email_webhook_router)
app.include_router(api.messenger_webhook_router)


@app.get("/")
async def root():
    return RedirectResponse("/shop/dashboard", status_code=303)


@app.get("/shop")
async def shop_root():
    return RedirectResponse("/shop/dashboard", status_code=303)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
