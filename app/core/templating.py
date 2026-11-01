"""Jinja2 rendering: one Environment per locale, full-page or HTMX-fragment layout."""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from starlette.requests import Request

from app import __version__
from app.core.assets import Assets
from app.core.config import LOCALES, Settings
from app.core.htmx import VARY, wants_fragment
from app.core.i18n import HTML_LANG, _, format_date_for, load_translations
from app.core.security import csp_for

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "web" / "templates"

# (key, label, path segment). Labels are translated when a page is rendered.
NAV: tuple[tuple[str, str, str], ...] = (
    ("home", _("Home"), ""),
    ("experience", _("Experience"), "experience"),
    ("projects", _("Projects"), "projects"),
    ("skills", _("Skills"), "skills"),
    ("resume", _("Résumé"), "resume"),
)

HTMX_CONFIG: dict[str, Any] = {
    "allowEval": False,
    "allowScriptTags": False,
    "includeIndicatorStyles": False,
    "responseHandling": [
        {"code": "204", "swap": False},
        {"code": "[23]..", "swap": True},
        {"code": "404", "swap": True},
        {"code": "422", "swap": True},
        {"code": "429", "swap": True},
        {"code": "[45]..", "swap": False, "error": True},
    ],
}


class Renderer:
    def __init__(self, settings: Settings, assets: Assets) -> None:
        self.settings = settings
        self.assets = assets
        self.translations = {locale: load_translations(locale) for locale in LOCALES}
        self.envs = {locale: self._build_environment(locale) for locale in LOCALES}

    def t(self, request: Request, message: str) -> str:
        """Translate ``message`` into the locale of the request."""
        return self.translations[request.state.locale].gettext(message)

    def _duration(self, locale: str, start: date, end: date | None) -> str:
        finish = end or datetime.now(UTC).date()
        months = max(1, (finish.year - start.year) * 12 + finish.month - start.month + 1)
        years, rest = divmod(months, 12)
        translations = self.translations[locale]
        parts: list[str] = []
        if years:
            parts.append(translations.ngettext("%(n)d yr", "%(n)d yrs", years) % {"n": years})
        if rest:
            parts.append(translations.ngettext("%(n)d mo", "%(n)d mos", rest) % {"n": rest})
        return " ".join(parts)

    def _build_environment(self, locale: str) -> Environment:
        env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=select_autoescape(default=True),
            extensions=["jinja2.ext.i18n"],
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        cast("Any", env).install_gettext_translations(self.translations[locale], newstyle=True)
        env.globals.update(
            static=self.assets.url,
            locale=locale,
            locales=LOCALES,
            hreflang=HTML_LANG,
            html_lang=HTML_LANG[locale],
            site_url=self.settings.site_url,
            default_locale=self.settings.default_locale,
            app_version=__version__,
            htmx_config=HTMX_CONFIG,
        )
        env.filters["date_fmt"] = lambda value, pattern="MMM yyyy": format_date_for(
            locale, value, pattern
        )
        env.filters["duration"] = lambda start, end=None: self._duration(locale, start, end)
        env.filters["years"] = lambda value: self._years(locale, value)
        return env

    def _years(self, locale: str, value: float) -> str:
        # ngettext needs an integer to pick the plural form; the printed value can be fractional.
        plural_selector = 1 if value == 1 else 2
        template = self.translations[locale].ngettext("%(n)g year", "%(n)g years", plural_selector)
        return template % {"n": value}

    def build_context(self, request: Request, extra: Mapping[str, Any] | None) -> dict[str, Any]:
        locale: str = request.state.locale
        content = request.app.state.content.get(locale)
        profile = content.profile
        segments = request.url.path.split("/")
        prefixed = len(segments) > 1 and segments[1] in LOCALES
        rest = "/" + "/".join(segments[2:]) if prefixed else "/"
        section = segments[2] if prefixed and len(segments) > 2 and segments[2] else "home"
        translate = self.translations[locale].gettext
        og_file = self.settings.downloads_dir / "og.png"
        context: dict[str, Any] = {
            "request": request,
            "profile": profile,
            "content": content,
            "nav": [
                {"key": key, "label": translate(label), "href": f"/{locale}/{path}"}
                for key, label, path in NAV
            ],
            "current": section,
            "alt_urls": {loc: f"/{loc}{rest}" for loc in LOCALES},
            "canonical": f"{self.settings.site_url}{request.url.path}",
            "page_title": profile.name,
            "page_description": profile.headline,
            "now_year": datetime.now(UTC).year,
            "og_image": f"{self.settings.site_url}/og.png" if og_file.is_file() else None,
            "sample_banner": profile.sample,
            "jsonld": {
                "@context": "https://schema.org",
                "@type": "Person",
                "name": profile.name,
                "jobTitle": profile.headline,
                "url": self.settings.site_url,
                "sameAs": [link.url for link in profile.links if link.url.startswith("http")],
            },
        }
        context.update(extra or {})
        return context

    def render(
        self,
        request: Request,
        template: str,
        extra: Mapping[str, Any] | None = None,
        *,
        status_code: int = 200,
        csp: str = "default",
    ) -> HTMLResponse:
        """Render a page: the full document, or only title + content for HTMX navigation."""
        context = self.build_context(request, extra)
        context["layout"] = "fragment.html" if wants_fragment(request) else "base.html"
        body = self.envs[request.state.locale].get_template(template).render(context)
        headers = {"Vary": VARY}
        if csp != "default":
            headers["Content-Security-Policy"] = csp_for(csp, self.settings)
        return HTMLResponse(body, status_code=status_code, headers=headers)

    def render_partial(
        self,
        request: Request,
        template: str,
        extra: Mapping[str, Any] | None = None,
        *,
        status_code: int = 200,
    ) -> HTMLResponse:
        """Render a standalone fragment (form, counter...) that is swapped in by HTMX."""
        context = self.build_context(request, extra)
        body = self.envs[request.state.locale].get_template(template).render(context)
        return HTMLResponse(body, status_code=status_code)
