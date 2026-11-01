"""Browser tests against a live server. Run with: pytest -m e2e tests/e2e

Every test fails on any console error, page error or Content-Security-Policy violation.
"""

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from playwright.sync_api import Page, expect

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.e2e

CSP_PROBE = """
window.__csp = [];
document.addEventListener('securitypolicyviolation', (e) =>
  window.__csp.push(e.violatedDirective + ' | ' + e.blockedURI));
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def live_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    port = _free_port()
    root = tmp_path_factory.mktemp("e2e")
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="test",
        content_dir=Path(__file__).parents[1] / "fixtures" / "content",
        data_dir=root / "data",
        downloads_dir=root / "downloads",
        site_url=f"http://127.0.0.1:{port}",
    )
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def watched(page: Page) -> Iterator[Page]:
    problems: list[str] = []
    page.on(
        "console",
        lambda msg: (
            problems.append(f"console.{msg.type}: {msg.text}")
            if msg.type in {"error", "warning"}
            else None
        ),
    )
    page.on("pageerror", lambda error: problems.append(f"pageerror: {error}"))
    page.add_init_script(CSP_PROBE)
    yield page
    violations: list[Any] = page.evaluate("window.__csp || []")
    assert violations == [], f"CSP violations: {violations}"
    assert problems == [], f"browser problems: {problems}"


@pytest.mark.parametrize(
    "path", ["/pt/", "/en/", "/pt/experience", "/en/projects", "/pt/skills", "/en/resume"]
)
def test_pages_load_cleanly(watched: Page, live_url: str, path: str) -> None:
    watched.goto(live_url + path, wait_until="networkidle")
    expect(watched.locator("h1")).to_have_count(1)
    assert watched.evaluate(
        "typeof window.htmx !== 'undefined' && typeof window.Alpine !== 'undefined'"
    )


def test_boosted_navigation_swaps_only_the_main_area(watched: Page, live_url: str) -> None:
    watched.goto(live_url + "/pt/", wait_until="networkidle")
    watched.evaluate("document.querySelector('.site-header').dataset.kept = 'yes'")
    watched.locator("#site-nav").get_by_role("link", name="Habilidades").click()
    watched.wait_for_url("**/pt/skills")
    expect(watched.locator("h1")).to_have_text("Habilidades")
    expect(watched).to_have_title("Habilidades · Seu Nome")
    assert watched.evaluate("document.querySelector('.site-header').dataset.kept") == "yes"
    expect(watched.locator("#site-nav a[aria-current='page']")).to_have_text("Habilidades")
    assert watched.evaluate("document.activeElement.id") == "main"


def test_back_button_restores_the_previous_page(watched: Page, live_url: str) -> None:
    watched.goto(live_url + "/pt/", wait_until="networkidle")
    watched.locator("#site-nav").get_by_role("link", name="Projetos").click()
    watched.wait_for_url("**/pt/projects")
    watched.locator("#site-nav").get_by_role("link", name="Experiência").click()
    watched.wait_for_url("**/pt/experience")
    watched.go_back()
    watched.wait_for_url("**/pt/projects")
    expect(watched.locator("h1")).to_have_text("Projetos")
    expect(watched.locator(".site-header")).to_have_count(1)


def test_language_switch_keeps_the_page(watched: Page, live_url: str) -> None:
    watched.goto(live_url + "/pt/projects/hub-curriculo", wait_until="networkidle")
    watched.locator("#lang-switch").get_by_role("link", name="EN").click()
    watched.wait_for_url("**/en/projects/hub-curriculo")
    expect(watched).to_have_title("Interactive resume hub · Your Name")
    assert watched.evaluate("document.documentElement.lang") == "en"


def test_theme_toggle_persists(watched: Page, live_url: str) -> None:
    watched.emulate_media(color_scheme="light")
    watched.goto(live_url + "/pt/", wait_until="networkidle")
    assert not watched.evaluate("document.documentElement.classList.contains('dark')")
    watched.get_by_role("button", name="Modo escuro").click()
    assert watched.evaluate("document.documentElement.classList.contains('dark')")
    watched.reload(wait_until="networkidle")
    assert watched.evaluate("document.documentElement.classList.contains('dark')")
    assert watched.evaluate("localStorage.getItem('theme')") == "dark"


def test_mobile_menu_opens(watched: Page, live_url: str) -> None:
    watched.set_viewport_size({"width": 390, "height": 800})
    watched.goto(live_url + "/pt/", wait_until="networkidle")
    expect(watched.locator("#site-nav")).to_be_hidden()
    watched.get_by_role("button", name="Menu").click()
    expect(watched.locator("#site-nav")).to_be_visible()
    expect(watched.get_by_role("button", name="Menu")).to_have_attribute("aria-expanded", "true")


def test_project_search_filters_live_and_updates_the_url(watched: Page, live_url: str) -> None:
    watched.goto(live_url + "/pt/projects", wait_until="networkidle")
    watched.locator("#q").fill("pipeline")
    expect(watched.locator("#results article")).to_have_count(1)
    assert "q=pipeline" in watched.url


def test_experience_filter(watched: Page, live_url: str) -> None:
    watched.goto(live_url + "/en/experience", wait_until="networkidle")
    watched.locator("#tech").select_option("fastapi")
    expect(watched.locator("#timeline .timeline-item")).to_have_count(1)
    assert "tech=fastapi" in watched.url


def test_error_pages_render_with_a_way_back(page: Page, live_url: str) -> None:
    # The browser itself logs the deliberate 404 as a console error, so only CSP is checked here.
    page.add_init_script(CSP_PROBE)
    response = page.goto(live_url + "/pt/nao-existe", wait_until="networkidle")
    assert response is not None
    assert response.status == 404
    expect(page.locator("h1")).to_have_text("Página não encontrada")
    expect(page.get_by_role("link", name="Voltar para a página inicial")).to_be_visible()
    assert page.evaluate("window.__csp") == []


def test_resume_is_printable(watched: Page, live_url: str) -> None:
    watched.goto(live_url + "/en/resume", wait_until="networkidle")
    watched.emulate_media(media="print")
    expect(watched.locator(".site-header")).to_be_hidden()
    expect(watched.locator(".resume-name")).to_be_visible()


def test_without_javascript_the_content_is_still_there(browser: Any, live_url: str) -> None:
    context = browser.new_context(java_script_enabled=False)
    try:
        page = context.new_page()
        page.goto(live_url + "/pt/projects?q=cli")
        expect(page.locator("#results article")).to_have_count(1)
        page.get_by_role("link", name="Habilidades").first.click()
        expect(page.locator("h1")).to_have_text("Habilidades")
    finally:
        context.close()
