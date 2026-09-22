"""Application configuration loaded from shop_admin/.env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_APP_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _APP_DIR.parent


class ShopAdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_APP_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="SHOP_ADMIN_",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    secret_key: str = "shop-admin-dev-secret-change-me"
    admin_token: str = "dev-admin-token"
    seed_demo: bool = True
    base_url: str = "http://localhost:8001"

    database_url: str = "sqlite+aiosqlite:///./shop_admin/data/shop_admin.db"
    upload_dir: Path = _APP_DIR / "data" / "uploads"

    ai_provider: Literal["mock", "openai"] = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    mail_provider: Literal["mock", "gmail"] = "mock"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    gmail_lookback_days: int = Field(default=30, ge=1, le=365)
    mail_webhook_secret: str = "dev-mail-webhook-secret"

    messenger_app_secret: str = "dev-messenger-secret"
    messenger_verify_token: str = "dev-messenger-verify"
    messenger_page_token: str = ""

    default_warehouse_code: str = "MAIN"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    parser_confidence_threshold: float = Field(default=0.55, ge=0, le=1)

    company_name: str = "Sklep Demo Sp. z o.o."
    company_nip: str = "0000000000"
    company_address: str = "ul. Przykładowa 1, 00-001 Warszawa"

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else _PROJECT_ROOT / path


@lru_cache
def get_settings() -> ShopAdminSettings:
    settings = ShopAdminSettings()
    settings.upload_dir = _project_path(settings.upload_dir).resolve()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    sqlite_prefix = "sqlite+aiosqlite:///"
    if settings.database_url.startswith(sqlite_prefix):
        database_path = settings.database_url.removeprefix(sqlite_prefix)
        if database_path not in {":memory:", ""}:
            resolved = _project_path(database_path).resolve()
            settings.database_url = f"{sqlite_prefix}{resolved.as_posix()}"
    return settings


settings = get_settings()
