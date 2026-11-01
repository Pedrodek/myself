"""Shared fixtures. The app is built against the real (sample) content and the compiled assets."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import PROJECT_ROOT, Settings
from app.main import create_app


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    root = tmp_path_factory.mktemp("hub")
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="test",
        content_dir=PROJECT_ROOT / "content",
        data_dir=root / "data",
        downloads_dir=root / "downloads",
        site_url="https://example.test",
    )


@pytest.fixture(scope="session")
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), base_url="https://example.test") as test_client:
        yield test_client


@pytest.fixture
def content_tree(tmp_path: Path) -> Path:
    """A writable copy of the real content for tests that break it on purpose."""
    import shutil

    target = tmp_path / "content"
    shutil.copytree(PROJECT_ROOT / "content", target, ignore=shutil.ignore_patterns("demos"))
    return target
