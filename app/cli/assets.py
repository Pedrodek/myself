"""Front-end asset pipeline without Node: vendored files, Tailwind CSS, fingerprinting."""

import base64
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Annotated, Any

import httpx2
import typer
from pygments.formatters import HtmlFormatter
from rich.console import Console

from app.core.config import PROJECT_ROOT

STATIC = PROJECT_ROOT / "app" / "web" / "static"
TEMPLATES = PROJECT_ROOT / "app" / "web" / "templates"
CSS_SOURCE = STATIC / "css" / "app.css"
PYGMENTS_CSS = STATIC / "css" / "_pygments.css"
VENDOR = STATIC / "vendor"
DIST = STATIC / "dist"
LOCK = PROJECT_ROOT / "assets.lock.json"
FINGERPRINTED_DIRS = ("js", "img", "vendor")
LIGHT_STYLE, DARK_STYLE = "default", "github-dark"

console = Console()
commands = typer.Typer(
    help="Front-end assets: vendored libraries, Tailwind CSS and fingerprinting.",
    no_args_is_help=True,
)


def sri(data: bytes) -> str:
    """Subresource Integrity value (sha384) for ``data``."""
    return "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode()


def _read_lock() -> dict[str, Any]:
    lock: dict[str, Any] = json.loads(LOCK.read_text(encoding="utf-8"))
    return lock


def _download(client: httpx2.Client, url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = client.get(url)
            response.raise_for_status()
            return response.content
        except httpx2.HTTPError as error:
            last_error = error
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"could not download {url}: {last_error}")


def _plotly_bundle() -> Path:
    import plotly

    return Path(plotly.__file__).resolve().parent / "package_data" / "plotly.min.js"


def sync_vendor(update: bool = False) -> None:
    """Download the vendored files and verify them against ``assets.lock.json``."""
    lock = _read_lock()
    VENDOR.mkdir(parents=True, exist_ok=True)
    with httpx2.Client(timeout=60, follow_redirects=True) as client:
        for name, spec in lock["vendor"].items():
            destination = VENDOR / name
            if (
                not update
                and destination.is_file()
                and sri(destination.read_bytes()) == spec["integrity"]
            ):
                continue
            data = _download(client, spec["url"])
            digest = sri(data)
            if update:
                spec["integrity"] = digest
            elif digest != spec["integrity"]:
                console.print(
                    f"[red]Integrity mismatch for {name}[/red]: "
                    f"expected {spec['integrity']}, got {digest}"
                )
                raise typer.Exit(1)
            destination.write_bytes(data)
            console.print(f"downloaded [green]{name}[/green] ({len(data) / 1024:.0f} KB)")

    # Plotly ships inside the wheel, so its version is pinned by requirements.txt.
    bundle = _plotly_bundle()
    data = bundle.read_bytes()
    if update:
        lock["plotly"]["integrity"] = sri(data)
    elif sri(data) != lock["plotly"]["integrity"]:
        console.print(
            "[red]plotly.min.js from the installed wheel does not match assets.lock.json[/red]"
        )
        raise typer.Exit(1)
    (VENDOR / "plotly.min.js").write_bytes(data)
    if update:
        LOCK.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        console.print(f"updated {LOCK.name}")


def _write_pygments_css() -> None:
    light = HtmlFormatter(style=LIGHT_STYLE).get_style_defs(".highlight")  # type: ignore[no-untyped-call]
    dark = HtmlFormatter(style=DARK_STYLE).get_style_defs(".dark .highlight")  # type: ignore[no-untyped-call]
    PYGMENTS_CSS.write_text(f"{light}\n{dark}\n", encoding="utf-8")


def _build_css(target: Path) -> None:
    from pytailwindcss import run

    version = _read_lock()["tailwindcss"]
    try:
        run(
            ["-i", str(CSS_SOURCE), "-o", str(target), "--minify"],
            cwd=PROJECT_ROOT,
            version=version,
            auto_install=True,
        )
    except subprocess.CalledProcessError as error:
        console.print(error.stderr.decode(errors="replace"))
        raise typer.Exit(1) from error


def _fingerprint(source: Path, relative: str) -> str:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:10]
    path = Path(relative)
    hashed = path.with_name(f"{path.stem}.{digest}{path.suffix}").as_posix()
    destination = DIST / hashed
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(source.read_bytes())
    return hashed


def build() -> dict[str, str]:
    """Compile the CSS, fingerprint every asset and write ``dist/manifest.json``."""
    DIST.mkdir(parents=True, exist_ok=True)
    _write_pygments_css()
    compiled = DIST / "_app.css"
    _build_css(compiled)
    manifest = {"css/app.css": _fingerprint(compiled, "css/app.css")}
    compiled.unlink()
    for directory in FINGERPRINTED_DIRS:
        base = STATIC / directory
        if not base.is_dir():
            continue
        for source in sorted(base.rglob("*")):
            if source.is_file():
                relative = source.relative_to(STATIC).as_posix()
                manifest[relative] = _fingerprint(source, relative)
    keep = {DIST / name for name in manifest.values()} | {DIST / "manifest.json"}
    for stale in DIST.rglob("*"):
        if stale.is_file() and stale not in keep:
            stale.unlink(missing_ok=True)
    (DIST / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def ensure_built() -> None:
    """Make sure vendored files and the build exist (used by ``dev`` and ``serve``)."""
    if not (VENDOR / "htmx.min.js").is_file():
        sync_vendor()
    build()


def _signature() -> tuple[int, float]:
    files = [CSS_SOURCE]
    for directory in (STATIC / "js", STATIC / "img", TEMPLATES):
        files += [path for path in directory.rglob("*") if path.is_file()]
    return len(files), max((path.stat().st_mtime for path in files), default=0.0)


def watch_forever(interval: float = 1.0) -> None:
    """Rebuild whenever a template, stylesheet, script or image changes."""
    seen = _signature()
    while True:
        time.sleep(interval)
        current = _signature()
        if current != seen:
            seen = current
            try:
                build()
                console.print("[green]assets rebuilt[/green]")
            except (typer.Exit, OSError, RuntimeError) as error:
                console.print(f"[red]asset build failed:[/red] {error}")


@commands.command("sync")
def sync_command(
    update: Annotated[
        bool,
        typer.Option(
            "--update", help="Recompute the hashes in assets.lock.json (deliberate upgrades only)."
        ),
    ] = False,
) -> None:
    """Download vendored libraries and verify their SHA-384 against assets.lock.json."""
    sync_vendor(update)
    console.print("[green]vendor files are in sync[/green]")


@commands.command("build")
def build_command() -> None:
    """Compile Tailwind CSS and write fingerprinted files plus the manifest."""
    manifest = build()
    console.print(
        f"[green]built {len(manifest)} assets[/green] -> {DIST.relative_to(PROJECT_ROOT)}"
    )


@commands.command("watch")
def watch_command() -> None:
    """Rebuild assets on every change (Ctrl+C to stop)."""
    ensure_built()
    console.print("watching templates, css, js and images...")
    watch_forever()
