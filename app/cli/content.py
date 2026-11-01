"""Content tasks."""

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from app.content import ContentError, load_content
from app.core.config import get_settings

console = Console()
commands = typer.Typer(help="Resume content (YAML/Markdown under content/).", no_args_is_help=True)


@commands.command("validate")
def validate(
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Also fail while the content is still marked as sample."),
    ] = False,
) -> None:
    """Validate every content file, cross references and pt/en parity."""
    settings = get_settings()
    try:
        store = load_content(settings.content_dir)
    except ContentError as error:
        for problem in error.problems:
            console.print(f"[red]x[/red] {problem}")
        console.print(f"[red]{len(error.problems)} problem(s) found[/red]")
        raise typer.Exit(1) from error

    table = Table("locale", "experience", "skills", "projects", "education")
    for locale, content in store.locales.items():
        table.add_row(
            locale,
            str(len(content.experience)),
            str(len(content.skills)),
            str(len(content.projects)),
            str(len(content.education)),
        )
    console.print(table)
    if store.is_sample:
        console.print(
            "[yellow]content is still marked as sample (sample: true in profile.yaml)[/yellow]"
        )
        if strict:
            raise typer.Exit(1)
    console.print("[green]content is valid[/green]")
