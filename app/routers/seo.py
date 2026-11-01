"""SEO and discovery endpoints: robots.txt, sitemap.xml, security.txt, favicon, downloads."""

from datetime import UTC, datetime, timedelta
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from starlette.requests import Request

from app.core.config import LOCALES
from app.core.i18n import HTML_LANG
from app.routers.deps import SettingsDep

router = APIRouter(include_in_schema=False)

# Section paths that exist for every locale (extended as features are added).
SITEMAP_SECTIONS: tuple[str, ...] = ("", "experience", "projects", "skills", "resume", "about-site")


def sitemap_paths(request: Request) -> list[str]:
    """Locale-independent paths (after the /<locale> prefix) that belong in the sitemap."""
    content = request.app.state.content.get(request.app.state.settings.default_locale)
    paths = [f"/{section}" if section else "/" for section in SITEMAP_SECTIONS]
    paths += [f"/projects/{project.slug}" for project in content.projects]
    extra: list[str] = getattr(request.app.state, "extra_sitemap_paths", [])
    return paths + extra


@router.api_route("/robots.txt", methods=["GET", "HEAD"])
async def robots(request: Request, settings: SettingsDep) -> PlainTextResponse:
    indexable = settings.is_prod and not request.app.state.content.is_sample
    lines = ["User-agent: *"]
    if indexable:
        lines += [
            "Allow: /",
            "Disallow: /api/",
            "Disallow: /ws/",
            f"Sitemap: {settings.site_url}/sitemap.xml",
        ]
    else:
        lines.append("Disallow: /")
    return PlainTextResponse(
        "\n".join(lines) + "\n", headers={"Cache-Control": "public, max-age=3600"}
    )


@router.api_route("/sitemap.xml", methods=["GET", "HEAD"])
async def sitemap(request: Request, settings: SettingsDep) -> Response:
    entries: list[str] = []
    for path in sitemap_paths(request):
        alternates = "".join(
            f'<xhtml:link rel="alternate" hreflang="{HTML_LANG[loc]}" '
            f'href="{escape(settings.site_url)}/{loc}{escape(path)}"/>'
            for loc in LOCALES
        )
        entries.extend(
            f"<url><loc>{escape(settings.site_url)}/{locale}{escape(path)}</loc>{alternates}</url>"
            for locale in LOCALES
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">' + "".join(entries) + "</urlset>"
    )
    return Response(
        body, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"}
    )


@router.api_route("/.well-known/security.txt", methods=["GET", "HEAD"])
async def security_txt(request: Request, settings: SettingsDep) -> PlainTextResponse:
    profile = request.app.state.content.get(settings.default_locale).profile
    if not profile.email:
        raise HTTPException(status_code=404)
    expires = (datetime.now(UTC) + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = (
        f"Contact: mailto:{profile.email}\n"
        f"Expires: {expires}\n"
        "Preferred-Languages: pt, en\n"
        f"Canonical: {settings.site_url}/.well-known/security.txt\n"
    )
    return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=86400"})


@router.api_route("/favicon.ico", methods=["GET", "HEAD"])
async def favicon(request: Request) -> RedirectResponse:
    return RedirectResponse(request.app.state.assets.url("img/favicon.svg"), status_code=308)


@router.get("/og.png")
async def og_image(settings: SettingsDep) -> FileResponse:
    path = settings.downloads_dir / "og.png"
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(
        path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"}
    )


@router.get("/downloads/resume.{locale}.pdf")
async def resume_pdf(locale: str, settings: SettingsDep) -> FileResponse:
    path = settings.downloads_dir / f"resume.{locale}.pdf"
    if locale not in LOCALES or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"resume-{locale}.pdf",
        headers={"Cache-Control": "public, max-age=3600"},
    )
