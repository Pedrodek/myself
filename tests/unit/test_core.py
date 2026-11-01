"""Settings, i18n helpers, text utilities, Markdown and the content loader."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.content import ContentError, load_content
from app.content.markdown import render_markdown
from app.core.config import DEV_SECRET, Settings
from app.core.htmx import wants_fragment
from app.core.i18n import load_translations, negotiate_locale, parse_accept_language
from app.core.text import reading_minutes, slugify


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg, arg-type]


class TestSettings:
    def test_defaults_are_safe_for_development(self) -> None:
        settings = make_settings()
        assert settings.env == "dev" and not settings.is_prod
        assert settings.secret_key.get_secret_value() == DEV_SECRET
        assert settings.resolved_log_format == "rich" and not settings.secure_cookies
        assert settings.sqlalchemy_url.startswith("sqlite+aiosqlite:///")

    def test_production_requires_a_real_secret(self) -> None:
        with pytest.raises(ValidationError, match="HUB_SECRET_KEY"):
            make_settings(env="prod")
        with pytest.raises(ValidationError, match="HUB_SECRET_KEY"):
            make_settings(env="prod", secret_key="short")
        prod = make_settings(env="prod", secret_key="x" * 40)
        assert prod.is_prod and prod.secure_cookies and prod.resolved_log_format == "json"

    def test_blank_values_are_treated_as_unset(self) -> None:
        settings = make_settings(
            github_token="  ", notify_webhook_url="", log_format="", secret_key=""
        )
        assert settings.github_token is None and settings.notify_webhook_url is None
        assert settings.secret_key.get_secret_value() == DEV_SECRET

    def test_site_url_validation_and_derived_values(self) -> None:
        assert make_settings(site_url="https://me.dev/").site_url == "https://me.dev"
        assert make_settings(site_url="https://me.dev").ws_url == "wss://me.dev"
        assert make_settings(site_url="http://127.0.0.1:8000").ws_url == "ws://127.0.0.1:8000"
        with pytest.raises(ValidationError):
            make_settings(site_url="me.dev")
        with pytest.raises(ValidationError):
            make_settings(notify_webhook_url="ftp://x")

    def test_environment_variables_use_the_hub_prefix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HUB_GITHUB_USER", "someone")
        monkeypatch.setenv("HUB_COOKIE_SECURE", "true")
        settings = make_settings()
        assert settings.github_user == "someone" and settings.secure_cookies


class TestI18n:
    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("en-US,en;q=0.9,pt;q=0.8", "en"),
            ("pt-BR,pt;q=0.9", "pt"),
            ("fr-FR,fr;q=0.9,en;q=0.5", "en"),
            ("en;q=0.1,pt;q=0.9", "pt"),
            ("de", "pt"),
            ("*;q=0.5", "pt"),
            ("en;q=abc", "pt"),
            ("en;q=0", "pt"),
            (None, "pt"),
            ("", "pt"),
        ],
    )
    def test_negotiation(self, header: str | None, expected: str) -> None:
        assert negotiate_locale(header, "pt") == expected

    def test_parse_orders_by_quality_then_position(self) -> None:
        assert parse_accept_language("a;q=0.5, b, c;q=0.5") == ["b", "a", "c"]

    def test_portuguese_catalog_translates_and_pluralizes(self) -> None:
        pt = load_translations("pt")
        assert pt.gettext("Skills") == "Habilidades"
        assert pt.ngettext("%(n)d yr", "%(n)d yrs", 1) == "%(n)d ano"
        assert pt.ngettext("%(n)d yr", "%(n)d yrs", 3) == "%(n)d anos"

    def test_english_falls_back_to_the_source_text(self) -> None:
        assert load_translations("en").gettext("Skills") == "Skills"

    def test_missing_catalog_is_not_fatal(self, tmp_path: Path) -> None:
        assert load_translations("pt", tmp_path).gettext("Skills") == "Skills"


def test_htmx_fragment_rules() -> None:
    from starlette.requests import Request

    def request(headers: dict[str, str]) -> Request:
        raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        return Request({"type": "http", "headers": raw})

    assert not wants_fragment(request({}))
    assert wants_fragment(request({"HX-Request": "true"}))
    assert not wants_fragment(request({"HX-Request": "true", "HX-History-Restore-Request": "true"}))


def test_slugify_and_reading_time() -> None:
    assert slugify("Solução & Arquitetura!") == "solucao-arquitetura"
    assert slugify("???") == "section"
    assert reading_minutes("palavra " * 450) == 3 and reading_minutes("") == 1


class TestMarkdown:
    def test_raw_html_is_not_rendered(self) -> None:
        html, _ = render_markdown("<script>alert(1)</script>\n\n<b>x</b>")
        assert "<script>" not in html and "<b>" not in html

    def test_headings_get_unique_anchors_and_a_toc(self) -> None:
        html, toc = render_markdown("## Resultados\n\ntexto\n\n## Resultados\n\n### Detalhe\n")
        assert [(t.level, t.id) for t in toc] == [
            (2, "resultados"),
            (2, "resultados-2"),
            (3, "detalhe"),
        ]
        assert 'id="resultados-2"' in html

    def test_code_is_highlighted_and_language_sanitized(self) -> None:
        html, _ = render_markdown("```python\nprint(1)\n```\n")
        assert 'class="highlight"' in html and "language-python" in html and "<span" in html
        hostile, _ = render_markdown('```"><img src=x>\ncode\n```\n')
        assert "<img" not in hostile
        unknown, _ = render_markdown("```nonexistentlang\nx = 1\n```\n")
        assert "<pre" in unknown

    def test_tables_and_strikethrough(self) -> None:
        html, _ = render_markdown("| a | b |\n|---|---|\n| 1 | ~~2~~ |\n")
        assert "<table>" in html and "<s>" in html


class TestContentLoader:
    def test_real_content_loads_with_cross_references(self, content_tree: Path) -> None:
        store = load_content(content_tree)
        pt, en = store.get("pt"), store.get("en")
        assert store.is_sample
        assert set(pt.skills) == set(en.skills) and set(pt.projects_by_slug) == set(
            en.projects_by_slug
        )
        assert [p.slug for p in pt.projects] == [
            "hub-curriculo",
            "api-pedidos",
            "pipeline-dados",
            "cli-automacao",
        ]
        assert pt.experience[0].end is None
        assert pt.search_projects(tag="cli")[0].slug == "cli-automacao"
        assert {p.slug for p in pt.projects_for_skill("pytest")} >= {"hub-curriculo"}

    def test_every_problem_is_reported_at_once(self, content_tree: Path) -> None:
        (content_tree / "pt" / "skills.yaml").write_text(
            "- category: X\n  skills:\n    - {slug: Bad Slug, name: B, level: 9}\n",
            encoding="utf-8",
        )
        (content_tree / "en" / "profile.yaml").write_text("name: Only a name\n", encoding="utf-8")
        with pytest.raises(ContentError) as caught:
            load_content(content_tree)
        text = "\n".join(caught.value.problems)
        assert "pt/skills.yaml" in text and "level" in text and "slug" in text
        assert "en/profile.yaml" in text and "headline" in text

    def test_missing_file_and_invalid_yaml(self, content_tree: Path) -> None:
        (content_tree / "pt" / "experience.yaml").unlink()
        (content_tree / "en" / "skills.yaml").write_text("- : [broken", encoding="utf-8")
        with pytest.raises(ContentError) as caught:
            load_content(content_tree)
        text = "\n".join(caught.value.problems)
        assert "file not found" in text and "invalid YAML" in text

    def test_unknown_references_are_rejected(self, content_tree: Path) -> None:
        path = content_tree / "pt" / "projects" / "cli-automacao.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "skills: [python, pytest, git]", "skills: [ghost]"
            ),
            encoding="utf-8",
        )
        with pytest.raises(ContentError, match="unknown skill 'ghost'"):
            load_content(content_tree)

    def test_pt_en_parity_is_enforced(self, content_tree: Path) -> None:
        (content_tree / "en" / "projects" / "cli-automacao.md").unlink()
        with pytest.raises(ContentError, match="projects only in pt"):
            load_content(content_tree)

    def test_dates_must_be_ordered_and_urls_safe(self, content_tree: Path) -> None:
        profile = content_tree / "pt" / "profile.yaml"
        profile.write_text(
            profile.read_text(encoding="utf-8").replace(
                "https://github.com/octocat", "javascript:alert(1)"
            ),
            encoding="utf-8",
        )
        with pytest.raises(ContentError, match="URL must be http"):
            load_content(content_tree)

    def test_files_saved_with_a_utf8_bom_still_load(self, content_tree: Path) -> None:
        # Windows editors (Notepad) add a BOM; it must not break YAML or Markdown front matter.
        targets = [
            content_tree / "pt" / "profile.yaml",
            content_tree / "pt" / "projects" / "cli-automacao.md",
        ]
        for target in targets:
            target.write_bytes(b"\xef\xbb\xbf" + target.read_bytes())
        store = load_content(content_tree)
        assert store.get("pt").profile.name == "Seu Nome"
        assert store.get("pt").project("cli-automacao") is not None

    def test_non_ascii_text_survives(self, content_tree: Path) -> None:
        profile = load_content(content_tree).get("pt").profile
        assert profile.headline == "Pessoa desenvolvedora Python · Backend e dados"

    def test_end_before_start_is_rejected(self, content_tree: Path) -> None:
        path = content_tree / "pt" / "experience.yaml"
        path.write_text(
            path.read_text(encoding="utf-8").replace("end: 2023-01", "end: 2019-01"),
            encoding="utf-8",
        )
        with pytest.raises(ContentError, match="ends before it starts"):
            load_content(content_tree)
