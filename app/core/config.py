"""Application settings (12-factor). Every variable uses the ``HUB_`` prefix."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCALES: tuple[str, ...] = ("pt", "en")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEV_SECRET = "dev-only-insecure-secret-do-not-use-in-production"  # noqa: S105 (dev default; prod rejects it)
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Runtime configuration, read from ``HUB_*`` environment variables or a ``.env`` file.

    Attributes:
        env: Execution mode. ``prod`` enables stricter checks (real secret, no sample content).
        secret_key: Signing key. Must be at least 32 characters when ``env`` is ``prod``.
        site_url: Public base URL, used for canonical links, Open Graph and the sitemap.
        database_url: SQLAlchemy URL; defaults to a SQLite file in ``data_dir``.
        content_dir: Folder with the resume content (``pt/`` and ``en/``).
        data_dir: Folder for mutable data such as the SQLite file.
        downloads_dir: Folder with the generated PDFs and Open Graph image.
        default_locale: Language used when the visitor's preference is unknown.
        github_user: GitHub account shown by the (future) live-GitHub section.
        github_token: Optional token that raises the GitHub API rate limit.
        github_offline: Skips GitHub calls and uses bundled data.
        notify_webhook_url: Optional webhook notified by the (future) contact form.
        trusted_proxies: Comma-separated proxy IPs allowed to set ``X-Forwarded-*`` headers.
        cookie_secure: Forces the cookie ``Secure`` flag; ``None`` means "on in production".
        hsts_max_age: ``Strict-Transport-Security`` max-age in seconds; ``0`` disables HSTS.
        log_level: Root logger level.
        log_format: ``rich`` or ``json``; ``None`` means "json in production, rich otherwise".
        allow_sample_content: Lets production start with the fictional sample content.
        form_min_seconds: Minimum time a form must stay open (anti-bot, future contact form).
    """

    model_config = SettingsConfigDict(
        env_prefix="HUB_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["dev", "test", "prod"] = "dev"
    secret_key: SecretStr = SecretStr(DEV_SECRET)
    site_url: str = Field(
        default_factory=lambda: os.getenv("RENDER_EXTERNAL_URL", "http://127.0.0.1:8000")
    )
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
        """Treat an empty variable (``HUB_X=``) as unset for optional settings."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("secret_key", mode="before")
    @classmethod
    def _blank_secret_uses_dev_default(cls, value: Any) -> Any:
        """Fall back to the dev key for an empty value; production rejects it afterwards."""
        return DEV_SECRET if isinstance(value, str) and not value.strip() else value

    @field_validator("site_url")
    @classmethod
    def _normalize_site_url(cls, value: str) -> str:
        """Require an absolute http(s) URL and drop the trailing slash."""
        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("must be an absolute http(s) URL")
        return value.strip().rstrip("/")

    @field_validator("notify_webhook_url")
    @classmethod
    def _check_webhook(cls, value: str | None) -> str | None:
        """Accept only http(s) webhook URLs."""
        if value is not None and urlsplit(value).scheme not in {"http", "https"}:
            raise ValueError("must be an http(s) URL")
        return value

    @model_validator(mode="after")
    def _require_real_secret_in_prod(self) -> "Settings":
        """Refuse to start in production with the dev key or a short key."""
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
        """Whether the app runs in production mode."""
        return self.env == "prod"

    @property
    def secure_cookies(self) -> bool:
        """Whether cookies get the ``Secure`` flag (explicit setting, otherwise prod only)."""
        return self.is_prod if self.cookie_secure is None else self.cookie_secure

    @property
    def resolved_log_format(self) -> str:
        """The effective log format: the explicit setting or the default for the environment."""
        return self.log_format or ("json" if self.is_prod else "rich")

    @property
    def sqlalchemy_url(self) -> str:
        """Async SQLAlchemy URL: ``database_url`` or the default SQLite file."""
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{(self.data_dir / 'hub.db').as_posix()}"

    @property
    def site_host(self) -> str:
        """Host (and port) of ``site_url``."""
        return urlsplit(self.site_url).netloc

    @property
    def ws_url(self) -> str:
        """WebSocket origin matching ``site_url`` (``wss`` for https), used in the CSP."""
        scheme = "wss" if urlsplit(self.site_url).scheme == "https" else "ws"
        return f"{scheme}://{self.site_host}"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read from the environment once and cached."""
    return Settings()
