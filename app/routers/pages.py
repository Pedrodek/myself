"""Locale-prefixed HTML pages. Each is rendered as a full document or, for HTMX, a fragment."""

from functools import partial
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.requests import Request

from app.content.models import SLUG_PATTERN
from app.core.i18n import negotiate_locale
from app.routers.deps import ContentDep, RendererDep, SettingsDep

pages = APIRouter(include_in_schema=False)
root = APIRouter(include_in_schema=False)

page = partial(pages.api_route, methods=["GET", "HEAD"], response_class=HTMLResponse)

SlugQuery = Annotated[str | None, Query(max_length=64, pattern=SLUG_PATTERN)]
TextQuery = Annotated[str | None, Query(max_length=80)]


@root.api_route("/", methods=["GET", "HEAD"])
async def index(request: Request, settings: SettingsDep) -> RedirectResponse:
    locale = negotiate_locale(request.headers.get("accept-language"), settings.default_locale)
    return RedirectResponse(f"/{locale}/", status_code=302, headers={"Vary": "Accept-Language"})


@page("/")
async def home(request: Request, renderer: RendererDep, content: ContentDep) -> Response:
    profile = content.profile
    top_skills = sorted(
        content.skills.values(),
        key=lambda skill: (-skill.level, -(skill.years or 0), skill.name.casefold()),
    )[:8]
    return renderer.render(
        request,
        "pages/home.html",
        {
            "page_title": f"{profile.name} · {profile.headline}",
            "featured": content.featured_projects[:3],
            "top_skills": top_skills,
            "latest": content.experience[0] if content.experience else None,
        },
    )


@page("/experience")
async def experience(
    request: Request, renderer: RendererDep, content: ContentDep, tech: SlugQuery = None
) -> Response:
    return renderer.render(
        request,
        "pages/experience.html",
        {
            "page_title": f"{renderer.t(request, 'Experience')} · {content.profile.name}",
            "items": content.filter_experience(tech),
            "tech": tech,
            "tech_options": content.experience_tech,
        },
    )


@page("/projects")
async def projects(
    request: Request,
    renderer: RendererDep,
    content: ContentDep,
    q: TextQuery = None,
    tag: TextQuery = None,
) -> Response:
    return renderer.render(
        request,
        "pages/projects.html",
        {
            "page_title": f"{renderer.t(request, 'Projects')} · {content.profile.name}",
            "items": content.search_projects(q, tag),
            "q": q or "",
            "tag": tag or "",
            "tags": content.all_tags,
        },
    )


@page("/projects/{slug}")
async def project_detail(
    slug: str, request: Request, renderer: RendererDep, content: ContentDep
) -> Response:
    project = content.project(slug)
    if project is None:
        raise HTTPException(status_code=404)
    return renderer.render(
        request,
        "pages/project.html",
        {
            "page_title": f"{project.title} · {content.profile.name}",
            "page_description": project.summary,
            "project": project,
            "project_skills": [content.skills[s] for s in project.skills if s in content.skills],
        },
    )


@page("/skills")
async def skills(request: Request, renderer: RendererDep, content: ContentDep) -> Response:
    return renderer.render(
        request,
        "pages/skills.html",
        {
            "page_title": f"{renderer.t(request, 'Skills')} · {content.profile.name}",
            "groups": content.skill_groups,
        },
    )


@page("/resume")
async def resume(
    request: Request, renderer: RendererDep, content: ContentDep, settings: SettingsDep
) -> Response:
    pdf = settings.downloads_dir / f"resume.{request.state.locale}.pdf"
    return renderer.render(
        request,
        "pages/resume.html",
        {
            "page_title": f"{renderer.t(request, 'Résumé')} · {content.profile.name}",
            "pdf_url": f"/downloads/resume.{request.state.locale}.pdf" if pdf.is_file() else None,
        },
    )


@page("/about-site")
async def about_site(request: Request, renderer: RendererDep, content: ContentDep) -> Response:
    return renderer.render(
        request,
        "pages/about_site.html",
        {"page_title": f"{renderer.t(request, 'About this site')} · {content.profile.name}"},
    )
