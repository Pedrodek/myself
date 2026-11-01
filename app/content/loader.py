"""Loads, validates and cross-checks the content files (fails fast with every problem listed)."""

import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, TypeVar

import frontmatter
import yaml
from pydantic import BaseModel, ValidationError

from app.content.markdown import render_markdown
from app.content.models import (
    SLUG_PATTERN,
    Education,
    Experience,
    Profile,
    Project,
    ProjectMeta,
    SkillGroup,
)
from app.content.store import ContentStore, LocaleContent
from app.core.config import LOCALES
from app.core.text import reading_minutes

T = TypeVar("T", bound=BaseModel)


class ContentError(Exception):
    """Raised when content is invalid. ``problems`` lists every issue found, not just the first."""

    def __init__(self, problems: list[str]) -> None:
        """Store the problems and join them into the exception message."""
        super().__init__("\n".join(problems))
        self.problems = problems


def _read_yaml(path: Path, problems: list[str], *, required: bool = True) -> Any:
    """Parse a YAML file safely; record a problem and return ``None`` if it is missing or broken.

    Read as ``utf-8-sig`` so files saved with a BOM (common on Windows) still load.
    """
    if not path.is_file():
        if required:
            problems.append(f"{path.as_posix()}: file not found")
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as error:
        problems.append(f"{path.as_posix()}: invalid YAML ({error})")
        return None


def _validate(model: type[T], data: Any, source: str, problems: list[str]) -> T | None:
    """Validate ``data`` against ``model``; on failure add one readable line per error."""
    try:
        return model.model_validate(data)
    except ValidationError as error:
        for item in error.errors():
            location = ".".join(str(part) for part in item["loc"]) or "<root>"
            problems.append(f"{source}: {location}: {item['msg']}")
        return None


def _validate_list(model: type[T], data: Any, source: str, problems: list[str]) -> tuple[T, ...]:
    """Validate every entry of a YAML list, keeping the valid ones and reporting the rest."""
    if data is None:
        return ()
    if not isinstance(data, list):
        problems.append(f"{source}: expected a list")
        return ()
    items = (
        _validate(model, entry, f"{source}[{index}]", problems) for index, entry in enumerate(data)
    )
    return tuple(item for item in items if item is not None)


def _load_projects(directory: Path, problems: list[str]) -> tuple[Project, ...]:
    """Load ``projects/*.md``: front matter is validated and the body rendered to HTML."""
    projects: list[Project] = []
    for path in sorted(directory.glob("*.md")):
        source = path.as_posix()
        if not re.match(SLUG_PATTERN, path.stem):
            problems.append(
                f"{source}: file name must be a slug (lowercase letters, digits, hyphens)"
            )
            continue
        try:
            post = frontmatter.loads(path.read_text(encoding="utf-8-sig"))
        except (yaml.YAMLError, UnicodeDecodeError) as error:
            problems.append(f"{source}: cannot parse front matter ({error})")
            continue
        meta = _validate(ProjectMeta, post.metadata, source, problems)
        if meta is None:
            continue
        html, toc = render_markdown(post.content)
        projects.append(
            Project(
                **meta.model_dump(),
                slug=path.stem,
                body_html=html,
                toc=toc,
                reading_minutes=reading_minutes(post.content),
            )
        )
    return tuple(sorted(projects, key=lambda project: (project.order, project.title.casefold())))


def _load_locale(root: Path, locale: str, problems: list[str]) -> LocaleContent | None:
    """Load one language folder. ``education.yaml`` is optional; the others are required."""
    base = root / locale
    profile = _validate(
        Profile, _read_yaml(base / "profile.yaml", problems), f"{locale}/profile.yaml", problems
    )
    experience = _validate_list(
        Experience,
        _read_yaml(base / "experience.yaml", problems),
        f"{locale}/experience.yaml",
        problems,
    )
    skill_groups = _validate_list(
        SkillGroup, _read_yaml(base / "skills.yaml", problems), f"{locale}/skills.yaml", problems
    )
    education = _validate_list(
        Education,
        _read_yaml(base / "education.yaml", problems, required=False),
        f"{locale}/education.yaml",
        problems,
    )
    projects = _load_projects(base / "projects", problems)
    if profile is None:
        return None
    return LocaleContent(locale, profile, experience, education, skill_groups, projects)


def _check_references(content: LocaleContent) -> list[str]:
    """Check cross references inside one locale.

    Skill slugs must be unique, and every slug cited by a project, a job or a skill's
    ``evidence`` must exist. A job must not end before it starts.
    """
    locale = content.locale
    problems: list[str] = []
    counts = Counter(skill.slug for group in content.skill_groups for skill in group.skills)
    problems += [f"{locale}: duplicate skill slug '{slug}'" for slug, n in counts.items() if n > 1]
    project_slugs = set(content.projects_by_slug)
    for skill in content.skills.values():
        problems += [
            f"{locale}: skill '{skill.slug}' cites unknown project '{slug}'"
            for slug in skill.evidence
            if slug not in project_slugs
        ]
    for project in content.projects:
        problems += [
            f"{locale}: project '{project.slug}' uses unknown skill '{slug}'"
            for slug in project.skills
            if slug not in content.skills
        ]
    for item in content.experience:
        problems += [
            f"{locale}: experience at '{item.company}' uses unknown skill '{slug}'"
            for slug in item.tech
            if slug not in content.skills
        ]
        if item.end and item.end < item.start:
            problems.append(f"{locale}: experience at '{item.company}' ends before it starts")
    return problems


def _check_parity(reference: LocaleContent, other: LocaleContent) -> list[str]:
    """Check that two languages describe the same facts.

    Text may differ, but skills, projects, levels, years, evidence and the dates and
    technologies of jobs and education must match, so the translations cannot drift apart.
    """
    tag = f"parity {reference.locale}/{other.locale}"
    problems: list[str] = []
    for label, left, right in (
        ("skills", set(reference.skills), set(other.skills)),
        ("projects", set(reference.projects_by_slug), set(other.projects_by_slug)),
    ):
        problems += (
            [f"{tag}: {label} only in {reference.locale}: {sorted(left - right)}"]
            if left - right
            else []
        )
        problems += (
            [f"{tag}: {label} only in {other.locale}: {sorted(right - left)}"]
            if right - left
            else []
        )
    for slug in set(reference.skills) & set(other.skills):
        a, b = reference.skills[slug], other.skills[slug]
        if (a.level, a.years, a.evidence) != (b.level, b.years, b.evidence):
            problems.append(f"{tag}: skill '{slug}' differs in level, years or evidence")
    if _experience_shape(reference) != _experience_shape(other):
        problems.append(f"{tag}: experience entries differ in count, dates or tech")
    if _education_shape(reference) != _education_shape(other):
        problems.append(f"{tag}: education entries differ in count or dates")
    return problems


def _experience_shape(content: LocaleContent) -> list[tuple[date, date | None, tuple[str, ...]]]:
    return [(item.start, item.end, item.tech) for item in content.experience]


def _education_shape(content: LocaleContent) -> list[tuple[date, date | None]]:
    return [(item.start, item.end) for item in content.education]


def load_content(content_dir: Path) -> ContentStore:
    """Load and validate all content, failing with every problem found.

    Args:
        content_dir: Folder containing one sub-folder per locale (``pt/``, ``en/``).

    Returns:
        The immutable store.

    Raises:
        ContentError: If any file is missing or invalid, a reference is unknown, or the
            languages are out of parity.
    """
    problems: list[str] = []
    loaded: dict[str, LocaleContent] = {}
    for locale in LOCALES:
        content = _load_locale(content_dir, locale, problems)
        if content is not None:
            loaded[locale] = content
    for content in loaded.values():
        problems += _check_references(content)
    if len(loaded) == len(LOCALES):
        reference, *others = loaded.values()
        for other in others:
            problems += _check_parity(reference, other)
    if problems:
        raise ContentError(problems)
    return ContentStore(loaded)
