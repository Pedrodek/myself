"""Pydantic models for the resume content (YAML and Markdown files under ``content/``)."""

import re
from datetime import date
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
REPO_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
_PRESENT = {"", "present", "presente", "atual", "now"}


def _parse_month(value: Any) -> Any:
    """Accept ``YYYY-MM``, ``YYYY-MM-DD``, a date, or null/"present" (-> None)."""
    if value is None or (isinstance(value, str) and value.strip().lower() in _PRESENT):
        return None
    if isinstance(value, str):
        text = value.strip()
        return date.fromisoformat(f"{text}-01" if re.fullmatch(r"\d{4}-\d{2}", text) else text)
    return value


def _check_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme in {"http", "https"} and parts.netloc:
        return value
    if parts.scheme == "mailto" and parts.path:
        return value
    raise ValueError("URL must be http(s) or mailto")


Slug = Annotated[str, Field(pattern=SLUG_PATTERN, max_length=64)]
SafeUrl = Annotated[str, AfterValidator(_check_url)]
MonthDate = Annotated[date, BeforeValidator(_parse_month)]
OptionalMonthDate = Annotated[date | None, BeforeValidator(_parse_month)]


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Link(ContentModel):
    label: str
    url: SafeUrl
    icon: str | None = None


class Profile(ContentModel):
    sample: bool = False
    name: str
    headline: str
    summary: str
    location: str | None = None
    email: EmailStr | None = None
    availability: str | None = None
    github_user: str | None = None
    links: tuple[Link, ...] = ()


class Experience(ContentModel):
    company: str
    role: str
    location: str | None = None
    start: MonthDate
    end: OptionalMonthDate = None
    summary: str | None = None
    highlights: tuple[str, ...] = ()
    tech: tuple[Slug, ...] = ()


class Skill(ContentModel):
    slug: Slug
    name: str
    level: Annotated[int, Field(ge=1, le=5)]
    years: Annotated[float, Field(ge=0, le=60)] | None = None
    tags: tuple[str, ...] = ()
    evidence: tuple[Slug, ...] = ()


class SkillGroup(ContentModel):
    category: str
    skills: tuple[Skill, ...]


class Education(ContentModel):
    institution: str
    degree: str
    start: MonthDate
    end: OptionalMonthDate = None
    notes: str | None = None


class ProjectMeta(ContentModel):
    """Front matter of ``content/<locale>/projects/<slug>.md``."""

    title: str
    summary: str
    repo: Annotated[str, Field(pattern=REPO_PATTERN)] | None = None
    url: SafeUrl | None = None
    skills: tuple[Slug, ...] = ()
    tags: tuple[str, ...] = ()
    featured: bool = False
    order: int = 100
    year: Annotated[int, Field(ge=1990, le=2100)] | None = None


class TocItem(ContentModel):
    level: int
    id: str
    text: str


class Project(ProjectMeta):
    slug: Slug
    body_html: str
    toc: tuple[TocItem, ...] = ()
    reading_minutes: int = 1
