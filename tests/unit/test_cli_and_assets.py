"""CLI commands, the asset pipeline and logging."""

import json
import logging
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from app.cli import assets, cli
from app.cli import dev as dev_module
from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.core.logging import JsonFormatter, configure_logging, request_id_var

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh_settings() -> Any:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_content_validate_accepts_the_real_content() -> None:
    result = runner.invoke(cli, ["content", "validate", "--strict"])
    assert result.exit_code == 0, result.output


def test_content_validate_reports_sample_content(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.conftest import SAMPLE_CONTENT

    monkeypatch.setenv("HUB_CONTENT_DIR", str(SAMPLE_CONTENT))
    result = runner.invoke(cli, ["content", "validate"])
    assert result.exit_code == 0, result.output
    assert "content is valid" in result.output and "sample" in result.output
    assert runner.invoke(cli, ["content", "validate", "--strict"]).exit_code == 1


def test_content_validate_lists_problems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_CONTENT_DIR", str(tmp_path))
    result = runner.invoke(cli, ["content", "validate"])
    assert result.exit_code == 1
    assert "file not found" in result.output and "problem(s) found" in result.output


def test_i18n_check_passes_for_the_repository_catalogs() -> None:
    result = runner.invoke(cli, ["i18n", "check"])
    assert result.exit_code == 0, result.output


def test_i18n_check_flags_untranslated_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.cli import i18n

    po = tmp_path / "pt_BR" / "LC_MESSAGES" / "messages.po"
    po.parent.mkdir(parents=True)
    po.write_text(
        'msgid ""\nmsgstr ""\n"Language: pt_BR\\n"\n'
        '"Content-Type: text/plain; charset=utf-8\\n"\n\n'
        'msgid "Hello"\nmsgstr ""\n\n#, fuzzy\nmsgid "Bye"\nmsgstr "Tchau"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
    result = runner.invoke(cli, ["i18n", "check"])
    assert result.exit_code == 1
    assert "untranslated" in result.output and "fuzzy" in result.output


def test_serve_uses_hardened_uvicorn_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        dev_module.uvicorn, "run", lambda app, **kwargs: captured.update(app=app, **kwargs)
    )
    monkeypatch.setenv("HUB_TRUSTED_PROXIES", "10.0.0.1")
    result = runner.invoke(cli, ["serve", "--port", "9001"])
    assert result.exit_code == 0, result.output
    assert captured["app"] == "app.main:create_app" and captured["factory"] is True
    assert captured["workers"] == 1 and captured["port"] == 9001
    assert captured["proxy_headers"] is True and captured["forwarded_allow_ips"] == "10.0.0.1"
    assert captured["server_header"] is False and captured["ws_max_size"] <= 4096


def test_dev_builds_assets_then_reloads(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    built: list[bool] = []
    started: list[str] = []
    monkeypatch.setattr(dev_module.uvicorn, "run", lambda _app, **kwargs: captured.update(kwargs))
    monkeypatch.setattr(dev_module.assets, "ensure_built", lambda: built.append(True))

    class FakeThread:
        def __init__(self, **kwargs: Any) -> None:
            started.append(kwargs["name"])

        def start(self) -> None:
            started.append("started")

    monkeypatch.setattr(dev_module.threading, "Thread", FakeThread)
    assert runner.invoke(cli, ["dev"]).exit_code == 0
    assert built == [True] and started == ["assets-watch", "started"]
    assert captured["reload"] is True and captured["host"] == "127.0.0.1"
    started.clear()
    assert runner.invoke(cli, ["dev", "--no-build"]).exit_code == 0
    assert not started


class TestAssets:
    def test_sri_matches_a_known_digest(self) -> None:
        assert (
            assets.sri(b"")
            == "sha384-OLBgp1GsljhM2TJ+sbHjaiH9txEUvgdDTAzHv2P24donTt6/529l+9Ua0vFImLlb"
        )

    def test_build_fingerprints_and_cleans_up(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dist = tmp_path / "dist"
        monkeypatch.setattr(assets, "DIST", dist)
        manifest = assets.build()
        assert (dist / "manifest.json").is_file()
        css = manifest["css/app.css"]
        assert (
            css.startswith("css/app.")
            and css.endswith(".css")
            and (dist / css).stat().st_size > 5000
        )
        assert manifest["js/app.js"].startswith("js/app.") and "img/favicon.svg" in manifest
        stale = dist / "css" / "app.0000000000.css"
        stale.write_text("old", encoding="utf-8")
        assert assets.build() == manifest and not stale.exists()
        assert json.loads((dist / "manifest.json").read_text(encoding="utf-8")) == manifest

    def test_built_css_contains_the_design_system(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(assets, "DIST", tmp_path)
        css = (tmp_path / assets.build()["css/app.css"]).read_text(encoding="utf-8")
        for needle in (
            ".site-header",
            ".prose",
            ".dark",
            "prefers-reduced-motion",
            ".highlight",
            "@media print",
        ):
            assert needle in css, needle

    def test_vendor_sync_verifies_integrity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = b"console.log('vendored');"
        lock = tmp_path / "assets.lock.json"
        lock.write_text(
            json.dumps(
                {
                    "tailwindcss": "v4.3.3",
                    "vendor": {
                        "lib.js": {
                            "url": "https://cdn.example/lib.js",
                            "integrity": assets.sri(payload),
                        }
                    },
                    "plotly": {
                        "package": "plotly",
                        "version": "7.1.0",
                        "integrity": assets.sri(assets._plotly_bundle().read_bytes()),
                    },
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(assets, "LOCK", lock)
        monkeypatch.setattr(assets, "VENDOR", tmp_path / "vendor")
        downloads: list[str] = []

        def fake_download(_client: Any, url: str) -> bytes:
            downloads.append(url)
            return payload

        monkeypatch.setattr(assets, "_download", fake_download)
        assets.sync_vendor()
        assert (tmp_path / "vendor" / "lib.js").read_bytes() == payload
        assert (tmp_path / "vendor" / "plotly.min.js").is_file()
        assets.sync_vendor()
        assert downloads == ["https://cdn.example/lib.js"]

        monkeypatch.setattr(assets, "_download", lambda _c, _u: b"tampered")
        (tmp_path / "vendor" / "lib.js").unlink()
        import typer

        with pytest.raises(typer.Exit):
            assets.sync_vendor()
        assert not (tmp_path / "vendor" / "lib.js").exists()

    def test_lock_file_pins_every_vendored_asset(self) -> None:
        lock = json.loads((PROJECT_ROOT / "assets.lock.json").read_text(encoding="utf-8"))
        for name, spec in lock["vendor"].items():
            assert spec["integrity"].startswith("sha384-"), name
            assert "@" in spec["url"] and "latest" not in spec["url"], name
        assert lock["plotly"]["integrity"].startswith("sha384-")

    def test_change_detection_signature_changes_with_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = assets._signature()
        probe = assets.STATIC / "js" / "_probe.js"
        try:
            probe.write_text("//", encoding="utf-8")
            assert assets._signature() != first
        finally:
            probe.unlink(missing_ok=True)


class TestLogging:
    def test_json_lines_include_the_request_id(self) -> None:
        token = request_id_var.set("req-123")
        try:
            record = logging.LogRecord(
                "app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None
            )
            record.request_id = request_id_var.get()
            payload = json.loads(JsonFormatter().format(record))
        finally:
            request_id_var.reset(token)
        assert payload["message"] == "hello world" and payload["request_id"] == "req-123"
        assert payload["level"] == "INFO" and payload["ts"].endswith("+00:00")

    def test_exceptions_are_serialized(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                "x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
            )
        assert "ValueError: boom" in json.loads(JsonFormatter().format(record))["exc"]

    def test_configure_is_idempotent_and_selects_the_format(self) -> None:
        root = logging.getLogger()
        before = list(root.handlers)
        try:
            for fmt in ("json", "rich", "json"):
                configure_logging(Settings(_env_file=None, env="test", log_format=fmt))  # type: ignore[call-arg, arg-type]
            ours = [h for h in root.handlers if getattr(h, "_hub_handler", False)]
            assert len(ours) == 1 and isinstance(ours[0].formatter, JsonFormatter)
            assert root.level == logging.WARNING and logging.getLogger("uvicorn.access").disabled
        finally:
            root.handlers[:] = before
