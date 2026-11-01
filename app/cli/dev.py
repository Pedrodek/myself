"""Development and production servers."""

import threading
from typing import Annotated

import typer
import uvicorn

from app.cli import assets
from app.core.config import PROJECT_ROOT, get_settings

APP_FACTORY = "app.main:create_app"


def dev(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Bind port.")] = 8000,
    build: Annotated[
        bool, typer.Option(help="Build the assets and rebuild them on change.")
    ] = True,
) -> None:
    """Run the development server with auto-reload.

    Builds the assets first and, in a background thread, rebuilds them whenever a template,
    stylesheet, script or image changes. uvicorn restarts the app when Python, YAML,
    Markdown or translation files change.
    """
    if build:
        assets.ensure_built()
        threading.Thread(target=assets.watch_forever, daemon=True, name="assets-watch").start()
    uvicorn.run(
        APP_FACTORY,
        factory=True,
        host=host,
        port=port,
        reload=True,
        reload_dirs=[str(PROJECT_ROOT / "app"), str(PROJECT_ROOT / "content")],
        reload_includes=["*.py", "*.yaml", "*.md", "*.po", "manifest.json"],
        log_config=None,
    )


def serve(
    host: Annotated[
        str, typer.Option(help="Bind address (use 0.0.0.0 inside a container).")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Bind port.")] = 8000,
) -> None:
    """Run the production server (one worker; proxy headers only from HUB_TRUSTED_PROXIES)."""
    settings = get_settings()
    uvicorn.run(
        APP_FACTORY,
        factory=True,
        host=host,
        port=port,
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxies,
        server_header=False,
        ws_max_size=4096,
        timeout_keep_alive=5,
        access_log=False,
        log_config=None,
    )
