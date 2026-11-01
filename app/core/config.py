"""Application settings (12-factor). Every variable uses the ``HUB_`` prefix."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCALES: tuple[str, ...] = ("pt", "en")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEV_SECRET = "dev-only-insecure-secret-do-not-use-in-production"  # noqa: S105 (dev default; prod rejects it)
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HUB_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["dev", "test", "prod"] = "dev"
    secret_key: SecretStr = SecretStr(DEV_SECRET)
    site_url: str = "http://127.0.0.1:8000"
    database_url: str | None = None
    content_dir: Path = PROJECT_ROOT / "content"
    data_dir: Path = PROJECT_ROOT / "data"
    downloads_dir: Path = PROJECT_ROOT / "build" / "downloads"
    default_locale: Literal["pt", "en"] = "pt"

    github_user: str = ""
    github_token: SecretStr | None = None
    github_offline: bool = False
    notify_webhook_url: str | None = None

    trusted_proxies: str = "127.0.0.1"
    cookie_secure: bool | None = None
    hsts_max_age: int = 0
    log_level: str = "INFO"
    log_format: Literal["rich", "json"] | None = None

    allow_sample_content: bool = False
    form_min_seconds: float = 3.0

    @field_validator(
        "github_token", "notify_webhook_url", "cookie_secure", "log_format", mode="before"
    )
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("secret_key", mode="before")
    @classmethod
    def _blank_secret_uses_dev_default(cls, value: Any) -> Any:
        return DEV_SECRET if isinstance(value, str) and not value.strip() else value

    @field_validator("site_url")
    @classmethod
    def _normalize_site_url(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("must be an absolute http(s) URL")
        return value.strip().rstrip("/")

    @field_validator("notify_webhook_url")
    @classmethod
    def _check_webhook(cls, value: str | None) -> str | None:
        if value is not None and urlsplit(value).scheme not in {"http", "https"}:
            raise ValueError("must be an http(s) URL")
        return value

    @model_validator(mode="after")
    def _require_real_secret_in_prod(self) -> "Settings":
        if self.env == "prod":
            key = self.secret_key.get_secret_value()
            if key == DEV_SECRET or len(key) < MIN_SECRET_LENGTH:
                raise ValueError(
                    f"HUB_SECRET_KEY must be set to at least {MIN_SECRET_LENGTH} characters "
                    "when HUB_ENV=prod"
                )
        return self

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def secure_cookies(self) -> bool:
        return self.is_prod if self.cookie_secure is None else self.cookie_secure

    @property
    def resolved_log_format(self) -> str:
        return self.log_format or ("json" if self.is_prod else "rich")

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{(self.data_dir / 'hub.db').as_posix()}"

    @property
    def site_host(self) -> str:
        return urlsplit(self.site_url).netloc

    @property
    def ws_url(self) -> str:
        scheme = "wss" if urlsplit(self.site_url).scheme == "https" else "ws"
        return f"{scheme}://{self.site_host}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
