"""Build-time artifacts: résumé PDFs and the social preview image (never generated at runtime)."""

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
import uvicorn
from rich.console import Console

from app.core.config import LOCALES, PROJECT_ROOT, Settings, get_settings
from app.main import create_app

if TYPE_CHECKING:  # playwright is a dev-only dependency, absent from the production image
    from playwright.sync_api import ViewportSize

console = Console()
commands = typer.Typer(
    help="Generate the PDF résumés and the Open Graph image.", no_args_is_help=True
)

OG_SIZE: "ViewportSize" = {"width": 1200, "height": 630}


@contextmanager
def running_site(settings: Settings) -> Iterator[str]:
    """Serve the app on a free local port for the duration of the block."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    base = f"http://127.0.0.1:{port}"
    local = settings.model_copy(update={"site_url": base})
    server = uvicorn.Server(
        uvicorn.Config(create_app(local), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True, name="export-server")
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("the export server did not start in time")
        time.sleep(0.05)
    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def export_pdfs(settings: Settings, out_dir: Path) -> list[Path]:
    """Print each locale's ``/<locale>/resume`` page to an A4 PDF using the print stylesheet.

    Starts the site on a temporary local port and drives headless Chromium through Playwright
    (a dev-only dependency).

    Args:
        settings: Settings used to build the temporary app.
        out_dir: Destination folder; created if needed.

    Returns:
        The PDF files that were written.
    """
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with running_site(settings) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for locale in LOCALES:
                page = browser.new_page()
                page.goto(f"{base}/{locale}/resume", wait_until="networkidle")
                target = out_dir / f"resume.{locale}.pdf"
                page.pdf(
                    path=str(target), format="A4", print_background=False, prefer_css_page_size=True
                )
                page.close()
                written.append(target)
        finally:
            browser.close()
    return written


def og_markup(name: str, headline: str) -> str:
    """Return the HTML screenshotted as the Open Graph image (text is HTML-escaped)."""
    return (
        "<!doctype html><meta charset='utf-8'><style>"
        "*{box-sizing:border-box}body{margin:0;width:1200px;height:630px;display:flex;"
        "flex-direction:column;justify-content:center;padding:80px;color:#fff;"
        "font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "background:linear-gradient(135deg,#312e81,#4338ca 55%,#6366f1)}"
        "h1{font-size:92px;margin:0 0 24px;letter-spacing:-2px}"
        "p{font-size:44px;margin:0;opacity:.92}"
        ".tag{margin-top:56px;font:28px ui-monospace,Consolas,monospace;opacity:.75}"
        f"</style><h1>{escape(name)}</h1><p>{escape(headline)}</p>"
        "<div class='tag'>&gt;_ python &middot; fastapi &middot; htmx</div>"
    )


def export_og(settings: Settings, out_dir: Path) -> Path:
    """Render the 1200x630 social preview image (``og.png``) with the default-locale profile.

    Returns:
        The path of the written PNG.
    """
    from playwright.sync_api import sync_playwright

    from app.content import load_content

    profile = load_content(settings.content_dir).get(settings.default_locale).profile
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "og.png"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport=OG_SIZE)
            page.set_content(og_markup(profile.name, profile.headline))
            page.screenshot(path=str(target))
        finally:
            browser.close()
    return target


OutOption = Annotated[
    Path | None, typer.Option("--out", help="Output directory (default: HUB_DOWNLOADS_DIR).")
]


def _shown(path: Path) -> str:
    """Show a path relative to the project when possible, to keep console output short."""
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


@commands.command("pdf")
def pdf_command(out: OutOption = None) -> None:
    """Print /pt/resume and /en/resume to PDF with the print stylesheet."""
    settings = get_settings()
    for path in export_pdfs(settings, out or settings.downloads_dir):
        console.print(f"[green]wrote[/green] {_shown(path)}")


@commands.command("og")
def og_command(out: OutOption = None) -> None:
    """Render the 1200x630 social preview image."""
    settings = get_settings()
    path = export_og(settings, out or settings.downloads_dir)
    console.print(f"[green]wrote[/green] {_shown(path)}")


@commands.command("all")
def all_command(out: OutOption = None) -> None:
    """Generate every artifact."""
    pdf_command(out)
    og_command(out)
