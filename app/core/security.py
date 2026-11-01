"""Security headers and Content-Security-Policy profiles.

The default policy is strict (no inline script, no inline style, no ``eval``). A few routes need a
profile with a relaxation, chosen explicitly by the route and verified in a real browser:

* ``charts``/``terminal``: Plotly and xterm.js inject ``<style>`` elements, so ``style-src`` also
  allows ``'unsafe-inline'`` (this does not affect ``script-src``).
* ``sandbox``: the Pyodide playground document, isolated in an opaque-origin iframe.
* ``apidocs``: the OpenAPI explorer loads Swagger UI from a CDN.
"""

from collections.abc import Mapping, Sequence

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings

PYODIDE_CDN = "https://cdn.jsdelivr.net"

DEFAULT_DIRECTIVES: dict[str, tuple[str, ...]] = {
    "default-src": ("'none'",),
    "script-src": ("'self'",),
    "style-src": ("'self'",),
    "img-src": ("'self'", "data:"),
    "font-src": ("'self'",),
    "connect-src": ("'self'",),
    "base-uri": ("'none'",),
    "form-action": ("'self'",),
    "frame-ancestors": ("'none'",),
    "object-src": ("'none'",),
}

SANDBOX_CSP = (
    "sandbox allow-scripts; default-src 'none'; "
    f"script-src 'self' 'wasm-unsafe-eval' {PYODIDE_CDN}; connect-src {PYODIDE_CDN}; "
    "worker-src blob:; frame-ancestors 'self'"
)

PROFILES = ("default", "charts", "terminal", "playground", "sandbox", "apidocs")


def _serialize(directives: Mapping[str, Sequence[str]]) -> str:
    return "; ".join(f"{name} {' '.join(values)}".strip() for name, values in directives.items())


def csp_for(profile: str, settings: Settings) -> str:
    if profile == "sandbox":
        return SANDBOX_CSP
    directives = {name: list(values) for name, values in DEFAULT_DIRECTIVES.items()}
    if profile == "default":
        pass
    elif profile == "charts":
        directives["style-src"].append("'unsafe-inline'")
    elif profile == "terminal":
        directives["style-src"].append("'unsafe-inline'")
        directives["connect-src"].append(settings.ws_url)
    elif profile == "playground":
        directives["frame-src"] = ["'self'"]
    elif profile == "apidocs":
        directives["script-src"].append(PYODIDE_CDN)
        directives["style-src"] += ["'unsafe-inline'", PYODIDE_CDN]
        directives["img-src"].append("https://fastapi.tiangolo.com")
    else:
        raise ValueError(f"unknown CSP profile: {profile}")
    return _serialize(directives)


def static_security_headers(settings: Settings) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        "Cross-Origin-Opener-Policy": "same-origin",
    }
    if settings.hsts_max_age > 0:
        headers["Strict-Transport-Security"] = f"max-age={settings.hsts_max_age}; includeSubDomains"
    return headers


class SecurityHeadersMiddleware:
    """Adds the security headers and the default CSP unless the route already chose a profile."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.static_headers = static_security_headers(settings)
        self.default_csp = csp_for("default", settings)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.static_headers.items():
                    headers.setdefault(name, value)
                headers.setdefault("Content-Security-Policy", self.default_csp)
                headers.setdefault("Cache-Control", "no-cache")
            await send(message)

        await self.app(scope, receive, send_with_headers)
