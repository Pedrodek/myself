"""Pages, HTMX fragments, i18n, SEO and error handling."""

import re

import pytest
from fastapi.testclient import TestClient

from app.content import load_content

PAGES = [
    "/",
    "/experience",
    "/projects",
    "/projects/hub-curriculo",
    "/skills",
    "/resume",
    "/about-site",
]
HTMX = {"HX-Request": "true"}
RESTORE = {"HX-Request": "true", "HX-History-Restore-Request": "true"}


@pytest.mark.parametrize("locale", ["pt", "en"])
@pytest.mark.parametrize("path", PAGES)
def test_pages_render_as_full_documents(client: TestClient, locale: str, path: str) -> None:
    response = client.get(f"/{locale}{path}")
    assert response.status_code == 200
    html = response.text
    assert html.lower().startswith("<!doctype html>")
    assert f'<html lang="{"pt-BR" if locale == "pt" else "en"}"' in html
    assert len(re.findall(r"<h1[ >]", html)) == 1
    assert 'rel="canonical"' in html
    assert response.headers["vary"].startswith("HX-Request, HX-History-Restore-Request")


@pytest.mark.parametrize("path", PAGES)
def test_htmx_navigation_returns_only_title_and_content(client: TestClient, path: str) -> None:
    response = client.get(f"/pt{path}", headers=HTMX)
    assert response.status_code == 200
    body = response.text.lstrip()
    assert body.startswith("<title>")
    assert not re.search(r"<(html|head|body)[\s>]", body)
    assert 'id="site-nav"' in body and 'hx-swap-oob="true"' in body


def test_history_restore_gets_the_full_document(client: TestClient) -> None:
    restored = client.get("/pt/skills", headers=RESTORE).text
    assert restored.lower().startswith("<!doctype html>")


def test_unknown_page_is_a_localized_404(client: TestClient) -> None:
    response = client.get("/pt/nao-existe")
    assert response.status_code == 404
    assert "Página não encontrada" in response.text
    assert client.get("/en/nope").status_code == 404
    assert "Page not found" in client.get("/en/nope").text


def test_404_for_htmx_is_a_fragment(client: TestClient) -> None:
    response = client.get("/pt/nao-existe", headers=HTMX)
    assert response.status_code == 404
    assert "<html" not in response.text


def test_root_negotiates_language(client: TestClient) -> None:
    for header, expected in (
        ("en-US,en;q=0.9", "/en/"),
        ("pt-BR,pt;q=0.9", "/pt/"),
        ("fr", "/pt/"),
        ("", "/pt/"),
    ):
        response = client.get("/", headers={"Accept-Language": header}, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == expected
        assert response.headers["vary"] == "Accept-Language"


def test_translations_are_applied(client: TestClient) -> None:
    assert "Habilidades" in client.get("/pt/skills").text
    assert "Skills" in client.get("/en/skills").text
    assert "Pular para o conteúdo" in client.get("/pt/").text
    assert "Skip to content" in client.get("/en/").text


def test_language_switch_points_to_the_same_page(client: TestClient) -> None:
    html = client.get("/pt/projects/hub-curriculo").text
    assert 'href="/en/projects/hub-curriculo"' in html
    assert 'hreflang="en"' in html


def test_project_pages_have_rendered_markdown_with_anchors(client: TestClient) -> None:
    html = client.get("/pt/projects/hub-curriculo").text
    assert '<h2 id="problema">' in html
    assert 'class="highlight"' in html
    assert "<script" not in html.split('class="prose"')[1].split("</article>")[0]


def test_projects_filter_without_javascript(client: TestClient) -> None:
    html = client.get("/pt/projects", params={"q": "pipeline"}).text
    assert "Pipelines de dados versionados" in html
    assert "API de pedidos" not in html
    html = client.get("/pt/projects", params={"tag": "cli"}).text
    assert "CLI de automação" in html and "Pipelines de dados" not in html
    assert "Nenhum projeto corresponde" in client.get("/pt/projects", params={"q": "zzzz"}).text


def test_experience_filter_by_technology(client: TestClient) -> None:
    html = client.get("/en/experience", params={"tech": "fastapi"}).text
    assert "Example Company A" in html and "Example Company B" not in html
    assert client.get("/en/experience", params={"tech": "Not A Slug!"}).status_code == 422


def test_user_input_is_escaped(client: TestClient) -> None:
    html = client.get("/pt/projects", params={"q": '"><script>alert(1)</script>'}).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_sitemap_lists_every_page_in_both_locales(client: TestClient) -> None:
    xml = client.get("/sitemap.xml").text
    content = load_content(client.app.state.settings.content_dir)  # type: ignore[attr-defined]
    for locale in ("pt", "en"):
        assert f"https://example.test/{locale}/projects/hub-curriculo" in xml
    assert xml.count("<url>") == 2 * (6 + len(content.get("pt").projects))
    assert 'hreflang="pt-BR"' in xml


def test_every_sitemap_url_resolves_and_internal_links_work(client: TestClient) -> None:
    urls = re.findall(r"<loc>https://example\.test(/[^<]*)</loc>", client.get("/sitemap.xml").text)
    assert urls
    seen: set[str] = set()
    for path in urls:
        response = client.get(path)
        assert response.status_code == 200, path
        for link in re.findall(r'href="(/[^"#]*)"', response.text):
            if link.startswith(("/static/", "/api/")) or link in seen:
                continue
            seen.add(link)
            assert client.get(link, follow_redirects=True).status_code == 200, f"{path} -> {link}"


def test_robots_blocks_indexing_outside_production(client: TestClient) -> None:
    assert "Disallow: /" in client.get("/robots.txt").text
    assert "Sitemap:" not in client.get("/robots.txt").text


def test_security_txt_and_favicon(client: TestClient) -> None:
    assert "Contact: mailto:contato@example.com" in client.get("/.well-known/security.txt").text
    response = client.get("/favicon.ico", follow_redirects=False)
    assert response.status_code == 308 and response.headers["location"].startswith("/static/")


def test_missing_downloads_are_404(client: TestClient) -> None:
    assert client.get("/downloads/resume.pt.pdf").status_code == 404
    assert client.get("/downloads/resume.xx.pdf").status_code == 404
    assert client.get("/og.png").status_code == 404
