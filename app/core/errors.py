"""Error pages (HTML/HTMX for browsers, JSON for the API) and the catch-all for unhandled errors."""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.i18n import _

logger = logging.getLogger(__name__)

JSON_PREFIXES = ("/api", "/healthz", "/readyz", "/csp-report")

ERROR_TEXT: dict[int, tuple[str, str]] = {
    404: (_("Page not found"), _("The page you are looking for does not exist or has moved.")),
    405: (_("Method not allowed"), _("This address does not accept that kind of request.")),
    422: (_("Invalid request"), _("Some of the submitted data is not valid.")),
    429: (_("Too many requests"), _("Please wait a little before trying again.")),
    500: (_("Something went wrong"), _("An unexpected error occurred and was logged.")),
}
DEFAULT_ERROR = (_("Request failed"), _("The request could not be completed."))


def error_response(
    request: Request,
    status_code: int,
    detail: Any = None,
    headers: Mapping[str, str] | None = None,
) -> Response:
    """Build the error response appropriate for the client.

    API, health and CSP-report paths get a JSON ``{"detail": ...}`` body. Everything else gets
    the localized HTML error page (a fragment for HTMX requests).

    Args:
        request: The failing request.
        status_code: HTTP status to return.
        detail: Optional detail for the JSON body; defaults to the status phrase.
        headers: Extra response headers (for example ``Allow`` on a 405).

    Returns:
        The response to send.
    """
    if request.url.path.startswith(JSON_PREFIXES):
        body = {"detail": detail if detail is not None else HTTPStatus(status_code).phrase}
        return JSONResponse(body, status_code=status_code, headers=dict(headers or {}))

    renderer = request.app.state.renderer
    if not hasattr(request.state, "locale"):
        request.state.locale = renderer.settings.default_locale
    title, message = ERROR_TEXT.get(status_code, DEFAULT_ERROR)
    translate = renderer.translations[request.state.locale].gettext
    response: Response = renderer.render(
        request,
        "errors/error.html",
        {
            "status_code": status_code,
            "heading": translate(title),
            "message": translate(message),
            "page_title": f"{status_code} · {translate(title)}",
            "request_id": getattr(request.state, "request_id", ""),
        },
        status_code=status_code,
    )
    response.headers.update(headers or {})
    return response


def install_error_handlers(app: FastAPI) -> None:
    """Route HTTP and validation errors through :func:`error_response`."""

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        """Render HTTP errors (404, 405, ...) raised by routes or the router."""
        return error_response(request, exc.status_code, exc.detail, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        """Render request-validation failures as a 422."""
        return error_response(request, 422, jsonable_encoder(exc.errors()))


class UnhandledErrorMiddleware:
    """Turns unexpected exceptions into a logged 500 page that still gets the security headers."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the next ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the app; on an exception before the response started, send a 500 page.

        If the response already started, headers are gone, so the exception is re-raised.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            logger.exception("Unhandled error on %s %s", scope["method"], scope["path"])
            if started:
                raise
            response = error_response(Request(scope, receive), 500)
            await response(scope, receive, send)
