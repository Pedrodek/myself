"""Application factory: wires settings, content, assets, middleware and routers together."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware

from app import __version__
from app.content import load_content
from app.core.assets import Assets, ImmutableStaticFiles
from app.core.config import LOCALES, Settings, get_settings
from app.core.errors import UnhandledErrorMiddleware, install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.core.security import SecurityHeadersMiddleware
from app.core.templating import Renderer
from app.routers import api, health, pages, seo

logger = logging.getLogger(__name__)

STATIC_DIST = Path(__file__).resolve().parent / "web" / "static" / "dist"
MAX_FORM_BYTES = 16 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Content is loaded and validated here, so a broken content file stops the process at
    startup instead of failing a request later. Shared objects (settings, content, assets,
    renderer) are stored on ``app.state`` and reached from routes through ``app.routers.deps``.

    Args:
        settings: Configuration to use. Defaults to the cached environment-based settings;
            tests pass their own instance.

    Returns:
        The configured application, ready to be served by an ASGI server.

    Raises:
        RuntimeError: In production when the sample content is still active and
            ``HUB_ALLOW_SAMPLE_CONTENT`` is not set.
        ContentError: When a file in the content directory is invalid.
    """
    settings = settings or get_settings()
    configure_logging(settings)

    content = load_content(settings.content_dir)
    if content.is_sample:
        message = "Sample content is active: edit content/<locale>/*.yaml and remove 'sample: true'"
        if settings.is_prod and not settings.allow_sample_content:
            raise RuntimeError(
                f"{message} (or set HUB_ALLOW_SAMPLE_CONTENT=true to deploy it anyway)"
            )
        logger.warning(message)

    assets = Assets(STATIC_DIST)
    if not assets.built:
        logger.warning(
            "Static assets are not built; run: python -m app assets sync "
            "&& python -m app assets build"
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Log one startup line; there is no other state to open or close in this version."""
        logger.info(
            "Starting %s v%s (env=%s)",
            content.get(settings.default_locale).profile.name,
            __version__,
            settings.env,
        )
        yield

    app = FastAPI(
        title="Resume hub API",
        summary="Read-only JSON API over the resume content.",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.content = content
    app.state.assets = assets
    app.state.renderer = Renderer(settings, assets)

    # The last middleware added is the outermost one. Body limit is innermost so its signal
    # exception is handled before the generic 500 handler sees it.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_FORM_BYTES)
    app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware, default_locale=settings.default_locale)

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(seo.router)
    app.include_router(api.router)
    app.include_router(api.docs_router)
    app.include_router(pages.root)
    for locale in LOCALES:
        app.include_router(pages.pages, prefix=f"/{locale}")
    app.mount(
        "/static", ImmutableStaticFiles(directory=STATIC_DIST, check_dir=False), name="static"
    )
    return app
