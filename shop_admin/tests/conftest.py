"""Isolated application fixtures for Shop Admin tests."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shop_admin.config import settings


_TEST_DIR = Path(tempfile.mkdtemp(prefix="shop-admin-tests-"))
_TEST_DB = _TEST_DIR / "test.db"
settings.database_url = f"sqlite+aiosqlite:///{_TEST_DB}"
settings.upload_dir = _TEST_DIR / "uploads"
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.seed_demo = False

from shop_admin import db as database  # noqa: E402
from shop_admin.db import Base  # noqa: E402

database.engine = create_async_engine(settings.database_url, echo=False, future=True)
database.SessionLocal = async_sessionmaker(
    database.engine,
    expire_on_commit=False,
    autoflush=False,
)


async def _reset_database() -> None:
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
def isolated_database():
    asyncio.run(_reset_database())
    yield
    asyncio.run(_reset_database())


@pytest_asyncio.fixture
async def db_session():
    async with database.SessionLocal() as session:
        await session.commit()
        yield session
        if session.is_active:
            await session.commit()


@pytest_asyncio.fixture
async def client():
    from httpx import ASGITransport, AsyncClient

    from shop_admin.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


async def login(client) -> None:
    response = await client.post("/shop/login", data={"token": settings.admin_token})
    assert response.status_code == 303
