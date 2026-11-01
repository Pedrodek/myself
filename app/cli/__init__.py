"""Command line interface (``python -m app --help``)."""

import typer

from app.cli import assets, content, dev, export, i18n

cli = typer.Typer(
    name="app",
    help="Interactive resume hub: development and operations tasks.",
    no_args_is_help=True,
    add_completion=False,
)
cli.command("dev")(dev.dev)
cli.command("serve")(dev.serve)
cli.add_typer(assets.commands, name="assets")
cli.add_typer(content.commands, name="content")
cli.add_typer(i18n.commands, name="i18n")
cli.add_typer(export.commands, name="export")
