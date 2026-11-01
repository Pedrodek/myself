"""Read-only JSON API over the resume content, plus the OpenAPI explorer page."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from starlette.requests import Request

from app.content import LocaleContent
from app.content.models import SLUG_PATTERN, Education, Experience, Profile, Project, SkillGroup
from app.core.security import csp_for
from app.routers.deps import SettingsDep

CACHE = "public, max-age=300"

router = APIRouter(prefix="/api/v1", tags=["resume"])
docs_router = APIRouter(include_in_schema=False)


class ProjectSummary(BaseModel):
    slug: str
    title: str
    summary: str
    repo: str | None
    url: str | None
    skills: tuple[str, ...]
    tags: tuple[str, ...]
    featured: bool
    year: int | None

    @classmethod
    def of(cls, project: Project) -> "ProjectSummary":
        return cls(**project.model_dump(include=set(cls.model_fields)))


def api_content(
    request: Request,
    lang: Annotated[Literal["pt", "en"] | None, Query(description="Content language")] = None,
) -> LocaleContent:
    locale = lang or request.app.state.settings.default_locale
    content: LocaleContent = request.app.state.content.get(locale)
    return content


ApiContent = Annotated[LocaleContent, Depends(api_content)]


@router.get("/profile")
async def get_profile(content: ApiContent, response: Response) -> Profile:
    response.headers["Cache-Control"] = CACHE
    return content.profile


@router.get("/skills")
async def get_skills(content: ApiContent, response: Response) -> tuple[SkillGroup, ...]:
    response.headers["Cache-Control"] = CACHE
    return content.skill_groups


@router.get("/experience")
async def get_experience(
    content: ApiContent,
    response: Response,
    tech: Annotated[str | None, Query(max_length=64, pattern=SLUG_PATTERN)] = None,
) -> list[Experience]:
    response.headers["Cache-Control"] = CACHE
    return content.filter_experience(tech)


@router.get("/education")
async def get_education(content: ApiContent, response: Response) -> tuple[Education, ...]:
    response.headers["Cache-Control"] = CACHE
    return content.education


@router.get("/projects")
async def get_projects(
    content: ApiContent,
    response: Response,
    q: Annotated[str | None, Query(max_length=80)] = None,
    tag: Annotated[str | None, Query(max_length=40)] = None,
) -> list[ProjectSummary]:
    response.headers["Cache-Control"] = CACHE
    return [ProjectSummary.of(project) for project in content.search_projects(q, tag)]


@router.get("/projects/{slug}")
async def get_project(slug: str, content: ApiContent, response: Response) -> Project:
    project = content.project(slug)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    response.headers["Cache-Control"] = CACHE
    return project


# Pinned version with Subresource Integrity (recompute both hashes when bumping the version).
SWAGGER_UI = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.34.0"
SWAGGER_CSS_SRI = "sha384-4c3vsE5f+trhFyHrFrLM1fFGUn531NIaC7dcqEWIJdoRQJ5CkJbSuSCwXLpaS1KF"
SWAGGER_JS_SRI = "sha384-9Td7MKiIr2S83E1kZyyVi8KdJw/S8CpAvu0llLyMeg0xq/hDGiZJfVn0fV4llCmK"


@docs_router.get("/api/docs", response_class=HTMLResponse)
async def api_docs(settings: SettingsDep) -> HTMLResponse:
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>API reference</title>"
        f'<link rel="stylesheet" href="{SWAGGER_UI}/swagger-ui.css" '
        f'integrity="{SWAGGER_CSS_SRI}" crossorigin="anonymous"></head>'
        '<body><div id="swagger-ui"></div>'
        f'<script src="{SWAGGER_UI}/swagger-ui-bundle.js" integrity="{SWAGGER_JS_SRI}" '
        'crossorigin="anonymous"></script><script src="/api/docs/init.js"></script></body></html>'
    )
    return HTMLResponse(page, headers={"Content-Security-Policy": csp_for("apidocs", settings)})


@docs_router.get("/api/docs/init.js")
async def api_docs_init() -> Response:
    script = (
        "window.ui = SwaggerUIBundle({url: '/api/openapi.json', dom_id: '#swagger-ui', "
        "deepLinking: true, presets: [SwaggerUIBundle.presets.apis]});"
    )
    return Response(script, media_type="text/javascript")
