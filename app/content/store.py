"""Immutable in-memory content store, queried by the pages, the API and the terminal."""

from dataclasses import dataclass
from functools import cached_property

from app.content.models import Education, Experience, Profile, Project, Skill, SkillGroup


@dataclass(frozen=True)
class LocaleContent:
    locale: str
    profile: Profile
    experience: tuple[Experience, ...]
    education: tuple[Education, ...]
    skill_groups: tuple[SkillGroup, ...]
    projects: tuple[Project, ...]

    @cached_property
    def skills(self) -> dict[str, Skill]:
        return {skill.slug: skill for group in self.skill_groups for skill in group.skills}

    @cached_property
    def projects_by_slug(self) -> dict[str, Project]:
        return {project.slug: project for project in self.projects}

    @cached_property
    def featured_projects(self) -> tuple[Project, ...]:
        return tuple(project for project in self.projects if project.featured)

    @cached_property
    def all_tags(self) -> tuple[str, ...]:
        return tuple(sorted({tag for project in self.projects for tag in project.tags}))

    @cached_property
    def experience_tech(self) -> tuple[Skill, ...]:
        slugs = {slug for item in self.experience for slug in item.tech}
        return tuple(
            sorted(
                (self.skills[s] for s in slugs if s in self.skills), key=lambda s: s.name.casefold()
            )
        )

    def project(self, slug: str) -> Project | None:
        return self.projects_by_slug.get(slug)

    def skill(self, slug: str) -> Skill | None:
        return self.skills.get(slug)

    def search_projects(self, query: str | None = None, tag: str | None = None) -> list[Project]:
        needle = (query or "").strip().casefold()
        found: list[Project] = []
        for project in self.projects:
            if tag and tag not in project.tags:
                continue
            if needle:
                skill_names = (self.skills[s].name for s in project.skills if s in self.skills)
                haystack = " ".join((project.title, project.summary, *project.tags, *skill_names))
                if needle not in haystack.casefold():
                    continue
            found.append(project)
        return found

    def filter_experience(self, tech: str | None = None) -> list[Experience]:
        if not tech:
            return list(self.experience)
        return [item for item in self.experience if tech in item.tech]

    def projects_for_skill(self, slug: str) -> list[Project]:
        return [project for project in self.projects if slug in project.skills]


@dataclass(frozen=True)
class ContentStore:
    locales: dict[str, LocaleContent]

    def get(self, locale: str) -> LocaleContent:
        return self.locales[locale]

    @property
    def is_sample(self) -> bool:
        return any(content.profile.sample for content in self.locales.values())
