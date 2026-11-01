"""PDF and Open Graph generation (needs Chromium: playwright install chromium).

The CLI runs in a subprocess: pytest-playwright keeps a Playwright instance open in the test
process, and the sync API cannot be nested.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.cli.export import og_markup
from app.core.config import PROJECT_ROOT

pytestmark = pytest.mark.e2e


def run_cli(out: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "HUB_ENV": "test",
        "HUB_DOWNLOADS_DIR": str(out),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(  # noqa: S603 (fixed argument list, no user input)
        [sys.executable, "-m", "app", "export", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def test_pdfs_are_generated_for_every_locale(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "pdf")
    assert result.returncode == 0, result.stdout + result.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == ["resume.en.pdf", "resume.pt.pdf"]
    for path in tmp_path.iterdir():
        data = path.read_bytes()
        assert data.startswith(b"%PDF")
        assert len(data) > 5_000


def test_og_image_is_a_1200x630_png(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "og")
    assert result.returncode == 0, result.stdout + result.stderr
    data = (tmp_path / "og.png").read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert int.from_bytes(data[16:20], "big") == 1200
    assert int.from_bytes(data[20:24], "big") == 630


def test_export_all_writes_every_artifact(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "dl"
    result = run_cli(out, "all")
    assert result.returncode == 0, result.stdout + result.stderr
    assert {p.name for p in out.iterdir()} == {"resume.pt.pdf", "resume.en.pdf", "og.png"}
    assert "wrote" in result.stdout


def test_og_markup_escapes_profile_text() -> None:
    html = og_markup("<b>Ann</b>", "A & B")
    assert "<b>Ann</b>" not in html
    assert "&lt;b&gt;Ann" in html
    assert "A &amp; B" in html
