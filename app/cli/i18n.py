"""Translation workflow built on Babel (extract -> update -> check)."""

import os
from contextlib import chdir
from pathlib import Path

import typer
from babel.messages.frontend import CommandLineInterface
from babel.messages.pofile import read_po
from rich.console import Console

from app import __version__
from app.core.config import LOCALES, PROJECT_ROOT
from app.core.i18n import BABEL_LOCALES, LOCALES_DIR

POT = LOCALES_DIR / "messages.pot"
SOURCE_LOCALE = "en"

console = Console()
commands = typer.Typer(
    help="Translations (Babel catalogs under app/locales).", no_args_is_help=True
)


def _babel(*args: str) -> None:
    with chdir(PROJECT_ROOT):
        code = CommandLineInterface().run(["pybabel", *args])  # type: ignore[no-untyped-call]
    if code:
        raise typer.Exit(int(code))


def _po(locale: str) -> Path:
    return LOCALES_DIR / BABEL_LOCALES[locale] / "LC_MESSAGES" / "messages.po"


@commands.command("extract")
def extract() -> None:
    """Extract translatable strings from Python and Jinja sources into messages.pot."""
    _babel(
        "extract", "-F", "babel.cfg", "-o", os.fspath(POT.relative_to(PROJECT_ROOT)),
        "--project=resume-hub", f"--version={__version__}", "--add-location=file",
        "--sort-by-file", "--no-wrap", ".",
    )  # fmt: skip


@commands.command("update")
def update() -> None:
    """Extract, then create or update the .po catalog of every locale."""
    extract()
    for locale in LOCALES:
        babel_locale = BABEL_LOCALES[locale]
        command = "update" if _po(locale).is_file() else "init"
        _babel(
            command, "-i", os.fspath(POT.relative_to(PROJECT_ROOT)),
            "-d", os.fspath(LOCALES_DIR.relative_to(PROJECT_ROOT)), "-l", babel_locale, "--no-wrap",
        )  # fmt: skip


@commands.command("check")
def check() -> None:
    """Fail when a non-source catalog has untranslated or fuzzy messages (CI gate)."""
    problems = 0
    for locale in LOCALES:
        if locale == SOURCE_LOCALE:
            continue
        path = _po(locale)
        if not path.is_file():
            console.print(f"[red]missing catalog[/red] {path}")
            problems += 1
            continue
        with path.open("rb") as handle:
            catalog = read_po(handle, locale=BABEL_LOCALES[locale])
        for message in catalog:
            if not message.id:
                continue
            ids = message.id if isinstance(message.id, tuple) else (message.id,)
            strings = message.string if isinstance(message.string, tuple) else (message.string,)
            if message.fuzzy or not all(strings):
                state = "fuzzy" if message.fuzzy else "untranslated"
                console.print(f"[yellow]{locale}[/yellow] {state}: {ids[0]!r}")
                problems += 1
        for _message, errors in catalog.check():
            for error in errors:
                console.print(f"[red]{locale}[/red] {error}")
                problems += 1
    if problems:
        console.print(f"[red]{problems} translation problem(s)[/red]")
        raise typer.Exit(1)
    console.print("[green]translations are complete[/green]")
