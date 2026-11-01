"""Pure ASGI middlewares: request context (id, locale, access log) and body size limit."""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import LOCALES
from app.core.logging import request_id_var

logger = logging.getLogger("app.access")

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_QUIET_PREFIXES = ("/static/", "/healthz", "/readyz")


def locale_from_path(path: str, default: str) -> str:
    """Return the locale in the first path segment (``/en/...`` gives ``en``) or ``default``."""
    first = path.split("/", 2)[1] if path.startswith("/") else ""
    return first if first in LOCALES else default


class RequestContextMiddleware:
    """Assigns a request id, resolves the locale from the URL prefix and logs one access line."""

    def __init__(self, app: ASGIApp, default_locale: str) -> None:
        """Wrap ``app``; ``default_locale`` is used for paths without a locale prefix."""
        self.app = app
        self.default_locale = default_locale

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Populate ``request.state`` (``request_id``, ``locale``), echo the id, log the access.

        A client-supplied ``X-Request-ID`` is reused only if it looks safe (8-64 characters of
        ``[A-Za-z0-9._-]``); otherwise a new id is generated, which prevents log injection.
        """
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["locale"] = locale_from_path(scope["path"], self.default_locale)

        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            level = logging.DEBUG if scope["path"].startswith(_QUIET_PREFIXES) else logging.INFO
            logger.log(
                level,
                "%s %s -> %s (%.1f ms)",
                scope.get("method", "WS"),
                scope["path"],
                status,
                elapsed_ms,
            )
            request_id_var.reset(token)


class _BodyTooLargeError(Exception):
    """Internal signal raised while reading a body that exceeds the limit."""


class BodySizeLimitMiddleware:
    """Rejects request bodies larger than ``max_bytes`` with 413."""

    def __init__(self, app: ASGIApp, max_bytes: int = 16 * 1024) -> None:
        """Wrap ``app``; bodies above ``max_bytes`` are rejected."""
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Check ``Content-Length`` up front and count streamed bytes for chunked bodies.

        Bodyless methods (GET, HEAD, OPTIONS) pass through untouched.
        """
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send)
            return

        received = 0
        response_started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLargeError:
            if response_started:
                raise
            await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        """Send a minimal JSON 413 response and close the connection."""
        body = b'{"detail":"Request body too large"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
