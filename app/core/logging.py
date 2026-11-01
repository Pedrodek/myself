"""Logging: Rich in development, one JSON object per line in production."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

from rich.logging import RichHandler

from app.core.config import Settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_HANDLER_MARK = "_hub_handler"
_NOISY_LOGGERS = ("httpx2", "httpcore2", "asyncio", "multipart", "watchfiles", "aiosqlite")


class RequestIdFilter(logging.Filter):
    """Attaches the current request id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Set ``record.request_id`` from the context variable and keep the record."""
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Formats a record as one JSON object per line, for log collectors."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize the record (timestamp, level, logger, message, request id, traceback)."""
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    """Install the application log handler on the root logger.

    Safe to call more than once: a handler installed by a previous call is replaced.
    """
    root = logging.getLogger()
    for stale in list(root.handlers):
        if getattr(stale, _HANDLER_MARK, False):
            root.removeHandler(stale)

    handler: logging.Handler
    if settings.resolved_log_format == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
    else:
        handler = RichHandler(rich_tracebacks=True, show_path=False, markup=False)
        handler.setFormatter(logging.Formatter("[%(request_id)s] %(message)s"))
    handler.addFilter(RequestIdFilter())
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)

    level = logging.WARNING if settings.env == "test" else settings.log_level.upper()
    root.setLevel(level)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    # The app logs one access line per request itself (no query string, no client address).
    logging.getLogger("uvicorn.access").disabled = True
