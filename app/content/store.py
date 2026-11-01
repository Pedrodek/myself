"""Immutable in-memory content store, queried by the pages, the API and the terminal."""

from dataclasses import dataclass
from functools import cached_property

from app.content.models import Education, Experience, Profile, Project, Skill, SkillGroup


@dataclass(frozen=True)
class LocaleContent:
    """All content for one language, plus the lookups and filters the pages and API need.

    Attributes:
        locale: Language code (``pt`` or ``en``).
        profile: Name, headline, summary, contact and links.
        experience: Work history, in file order.
        education: Education and certificates, in file order.
        skill_groups: Skills grouped by category, in file order.
        projects: Case studies, sorted by ``order`` and then title.
    """

    locale: str
    profile: Profile
    experience: tuple[Experience, ...]
    education: tuple[Education, ...]
    skill_groups: tuple[SkillGroup, ...]
    projects: tuple[Project, ...]

    @cached_property
    def skills(self) -> dict[str, Skill]:
        """Every skill indexed by slug."""
        return {skill.slug: skill for group in self.skill_groups for skill in group.skills}

    @cached_property
    def projects_by_slug(self) -> dict[str, Project]:
        """Every project indexed by slug."""
        return {project.slug: project for project in self.projects}

    @cached_property
    def featured_projects(self) -> tuple[Project, ...]:
        """Projects marked ``featured: true`` (shown on the home page)."""
        return tuple(project for project in self.projects if project.featured)

    @cached_property
    def all_tags(self) -> tuple[str, ...]:
        """Distinct project tags, sorted (used by the project filter)."""
        return tuple(sorted({tag for project in self.projects for tag in project.tags}))

    @cached_property
    def experience_tech(self) -> tuple[Skill, ...]:
        """Skills used in at least one job, sorted by name (used by the experience filter)."""
        slugs = {slug for item in self.experience for slug in item.tech}
        return tuple(
            sorted(
                (self.skills[s] for s in slugs if s in self.skills), key=lambda s: s.name.casefold()
            )
        )

    def project(self, slug: str) -> Project | None:
        """Return the project with this slug, or ``None``."""
        return self.projects_by_slug.get(slug)

    def skill(self, slug: str) -> Skill | None:
        """Return the skill with this slug, or ``None``."""
        return self.skills.get(slug)

    def search_projects(self, query: str | None = None, tag: str | None = None) -> list[Project]:
        """Filter projects by tag and by a case-insensitive text query.

        The query is matched against the title, summary, tags and the names of the skills
        the project uses.

        Args:
            query: Text to look for; empty or ``None`` matches everything.
            tag: Exact tag the project must have; empty or ``None`` matches everything.

        Returns:
            Matching projects in their original order.
        """
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
        """Return the jobs that used the skill ``tech`` (all jobs when it is empty)."""
        if not tech:
            return list(self.experience)
        return [item for item in self.experience if tech in item.tech]

    def projects_for_skill(self, slug: str) -> list[Project]:
        """Return the projects that list the given skill."""
        return [project for project in self.projects if slug in project.skills]


@dataclass(frozen=True)
class ContentStore:
    """The validated content of every locale. Built once at startup and never mutated."""

    locales: dict[str, LocaleContent]

    def get(self, locale: str) -> LocaleContent:
        """Return the content for ``locale`` (``KeyError`` if it was not loaded)."""
        return self.locales[locale]

    @property
    def is_sample(self) -> bool:
        """Whether any locale still carries the ``sample: true`` marker."""
        return any(content.profile.sample for content in self.locales.values())
