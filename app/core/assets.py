"""Static assets: fingerprinted URLs through the build manifest and immutable caching."""

import json
import mimetypes
import re
from pathlib import Path

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

HASHED_NAME = re.compile(r"\.[0-9a-f]{10}\.[A-Za-z0-9]+$")
IMMUTABLE = "public, max-age=31536000, immutable"

# Windows registries sometimes map .js to text/plain, which `nosniff` turns into a blocked script.
for _suffix, _mime in {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
}.items():
    mimetypes.add_type(_mime, _suffix)


class Assets:
    def __init__(self, dist_dir: Path) -> None:
        self.dist_dir = dist_dir
        self._manifest: dict[str, str] = {}
        manifest = dist_dir / "manifest.json"
        if manifest.is_file():
            self._manifest = json.loads(manifest.read_text(encoding="utf-8"))

    @property
    def built(self) -> bool:
        return bool(self._manifest)

    def url(self, name: str) -> str:
        return "/static/" + self._manifest.get(name, name)


class ImmutableStaticFiles(StaticFiles):
    """Serves fingerprinted files as immutable and everything else as revalidate-always."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = (
                IMMUTABLE if HASHED_NAME.search(path) else "no-cache"
            )
        return response
