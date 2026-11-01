"""Liveness and readiness probes."""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app import __version__

router = APIRouter(tags=["health"], include_in_schema=False)


@router.api_route("/healthz", methods=["GET", "HEAD"])
async def healthz() -> dict[str, str]:
    """The process is up."""
    return {"status": "ok", "version": __version__}


@router.api_route("/readyz", methods=["GET", "HEAD"])
async def readyz(request: Request) -> JSONResponse:
    """The app can serve: content is loaded (and, later, the database answers)."""
    checks: dict[str, Any] = {"content": bool(request.app.state.content.locales)}
    for name, probe in getattr(request.app.state, "readiness_probes", {}).items():
        try:
            checks[name] = bool(await probe())
        except Exception:
            checks[name] = False
    ready = all(checks.values())
    return JSONResponse(
        {"status": "ready" if ready else "unavailable", "checks": checks},
        status_code=200 if ready else 503,
    )
