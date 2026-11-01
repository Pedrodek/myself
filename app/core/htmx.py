"""Helpers for the HTMX request protocol."""

from starlette.requests import Request

VARY = "HX-Request, HX-History-Restore-Request"


def is_htmx(request: Request) -> bool:
    """True for any request issued by htmx (``HX-Request: true``)."""
    return request.headers.get("HX-Request") == "true"


def is_history_restore(request: Request) -> bool:
    """True when htmx is restoring a page after a history-cache miss."""
    return request.headers.get("HX-History-Restore-Request") == "true"


def wants_fragment(request: Request) -> bool:
    """True when the client swaps the response into the page.

    On a history cache miss htmx sends ``HX-Request`` *and* ``HX-History-Restore-Request``
    and expects the complete document, so that case is not a fragment.
    """
    return is_htmx(request) and not is_history_restore(request)
