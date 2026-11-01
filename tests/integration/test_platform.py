"""Security headers, CSP profiles, request context, body limits, health and the JSON API."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.security import PROFILES, csp_for


def test_security_headers_on_every_response(client: TestClient) -> None:
    for path in ("/pt/", "/healthz", "/api/v1/profile", "/pt/nao-existe", "/robots.txt"):
        headers = client.get(path).headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert headers["cross-origin-opener-policy"] == "same-origin"
        assert "camera=()" in headers["permissions-policy"]
        assert headers["content-security-policy"].startswith("default-src 'none'")
        assert re.fullmatch(r"[0-9a-f]{16}", headers["x-request-id"])


def test_default_csp_is_strict(client: TestClient) -> None:
    csp = client.get("/pt/").headers["content-security-policy"]
    directives = dict(part.strip().split(" ", 1) for part in csp.split(";"))
    assert directives["script-src"] == "'self'"
    assert directives["style-src"] == "'self'"
    assert directives["frame-ancestors"] == "'none'"
    assert "unsafe" not in csp


def test_pages_have_no_inline_scripts_styles_or_handlers(client: TestClient) -> None:
    for path in ("/pt/", "/en/skills", "/pt/projects/hub-curriculo", "/pt/resume"):
        html = client.get(path).text
        for match in re.finditer(r"<script\b([^>]*)>", html):
            attrs = match.group(1)
            assert "src=" in attrs or 'type="application/ld+json"' in attrs, (
                f"inline script in {path}"
            )
        assert "<style" not in html
        assert not re.search(r'\sstyle="', html)
        assert not re.search(r'\son[a-z]+="', html)


def test_csp_profiles(settings: Settings) -> None:
    assert "'unsafe-inline'" not in csp_for("default", settings)
    for profile in ("charts", "terminal"):
        csp = csp_for(profile, settings)
        assert "style-src 'self' 'unsafe-inline'" in csp
        assert "script-src 'self';" in csp
    assert "wss://" not in csp_for("default", settings)
    terminal = csp_for("terminal", settings)
    assert "connect-src 'self' wss://example.test" in terminal
    assert csp_for("sandbox", settings).startswith("sandbox allow-scripts")
    assert "frame-src 'self'" in csp_for("playground", settings)
    assert "cdn.jsdelivr.net" in csp_for("apidocs", settings)
    assert set(PROFILES) >= {"default", "charts", "terminal", "playground", "sandbox", "apidocs"}
    with pytest.raises(ValueError, match="unknown CSP profile"):
        csp_for("nope", settings)


def test_hsts_only_when_configured(settings: Settings) -> None:
    from app.core.security import static_security_headers

    assert "Strict-Transport-Security" not in static_security_headers(settings)
    prod = settings.model_copy(update={"hsts_max_age": 31536000})
    assert static_security_headers(prod)["Strict-Transport-Security"].startswith("max-age=31536000")


def test_request_id_is_propagated_or_replaced(client: TestClient) -> None:
    assert (
        client.get("/healthz", headers={"X-Request-ID": "abc12345-xyz"}).headers["x-request-id"]
        == "abc12345-xyz"
    )
    assert (
        client.get("/healthz", headers={"X-Request-ID": "bad id\t"}).headers["x-request-id"]
        != "bad id\t"
    )


def test_oversized_bodies_are_rejected(settings: Settings) -> None:
    from starlette.requests import Request

    from app.main import create_app

    app = create_app(settings)

    @app.post("/echo-size")
    async def echo_size(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    with TestClient(app) as local:
        assert local.post("/echo-size", content=b"x" * 1000).json() == {"size": 1000}
        declared = local.post("/echo-size", content=b"x" * 20_000)
        assert declared.status_code == 413
        streamed = local.post("/echo-size", content=iter([b"x" * 10_000, b"x" * 10_000]))
        assert streamed.status_code == 413
        assert streamed.json() == {"detail": "Request body too large"}


def test_static_files_cache_policy(client: TestClient) -> None:
    html = client.get("/pt/").text
    hashed = re.search(r"/static/css/app\.[0-9a-f]{10}\.css", html)
    assert hashed
    response = client.get(hashed.group(0))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["content-type"].startswith("text/css")
    js = re.search(r"/static/js/app\.[0-9a-f]{10}\.js", html)
    assert js and client.get(js.group(0)).headers["content-type"].startswith("text/javascript")
    manifest = client.get("/static/manifest.json")
    assert manifest.headers["cache-control"] == "no-cache"


def test_health_probes(client: TestClient) -> None:
    assert client.get("/healthz").json()["status"] == "ok"
    ready = client.get("/readyz")
    assert ready.status_code == 200 and ready.json()["checks"] == {"content": True}
    assert client.head("/healthz").status_code == 200


def test_production_refuses_sample_content_unless_allowed(settings: Settings) -> None:
    from app.main import create_app

    prod = settings.model_copy(update={"env": "prod", "secret_key": SecretStr("k" * 40)})
    with pytest.raises(RuntimeError, match="Sample content is active"):
        create_app(prod)

    allowed = prod.model_copy(update={"allow_sample_content": True})
    with TestClient(create_app(allowed)) as local:
        assert local.get("/healthz").status_code == 200
        # Even when allowed, sample content must never be indexed.
        assert "Disallow: /\n" in local.get("/robots.txt").text


def test_production_real_content_is_indexable(settings: Settings, content_tree: Path) -> None:
    from app.main import create_app

    for locale in ("pt", "en"):
        profile = content_tree / locale / "profile.yaml"
        profile.write_text(
            profile.read_text(encoding="utf-8").replace("sample: true\n", ""), encoding="utf-8"
        )
    prod = settings.model_copy(
        update={"env": "prod", "secret_key": SecretStr("k" * 40), "content_dir": content_tree}
    )
    with TestClient(create_app(prod)) as local:
        robots = local.get("/robots.txt").text
    assert "Allow: /" in robots
    assert "Sitemap: https://example.test/sitemap.xml" in robots
    assert "Disallow: /api/" in robots


def test_readiness_reports_a_failing_probe(settings: Settings) -> None:
    from app.main import create_app

    app = create_app(settings)

    async def broken() -> bool:
        raise RuntimeError("db down")

    app.state.readiness_probes = {"database": broken}
    with TestClient(app) as local:
        response = local.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"content": True, "database": False},
    }


def test_unhandled_errors_become_a_logged_500_page(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    from app.main import create_app

    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as local:
        response = local.get("/boom")
    assert response.status_code == 500
    assert "kaboom" not in response.text
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    assert any("Unhandled error" in record.message for record in caplog.records)


def test_api_profile_and_language(client: TestClient) -> None:
    pt = client.get("/api/v1/profile").json()
    en = client.get("/api/v1/profile", params={"lang": "en"}).json()
    assert pt["name"] == "Seu Nome" and en["name"] == "Your Name"
    assert client.get("/api/v1/profile", params={"lang": "xx"}).status_code == 422
    assert client.get("/api/v1/profile").headers["cache-control"] == "public, max-age=300"


def test_api_collections(client: TestClient) -> None:
    assert len(client.get("/api/v1/projects").json()) == 4
    assert [p["slug"] for p in client.get("/api/v1/projects", params={"q": "cli"}).json()] == [
        "cli-automacao"
    ]
    assert len(client.get("/api/v1/skills").json()) == 4
    assert client.get("/api/v1/experience", params={"tech": "git"}).json()
    assert client.get("/api/v1/education").json()[0]["institution"]
    detail = client.get("/api/v1/projects/hub-curriculo").json()
    assert detail["slug"] == "hub-curriculo" and "<h2" in detail["body_html"]
    missing = client.get("/api/v1/projects/nope")
    assert missing.status_code == 404 and missing.json() == {"detail": "Project not found"}


def test_api_docs_page_and_openapi(client: TestClient) -> None:
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert "swagger-ui-bundle.js" in response.text and 'integrity="sha384-' in response.text
    assert "cdn.jsdelivr.net" in response.headers["content-security-policy"]
    assert "<script>" not in response.text
    assert client.get("/api/docs/init.js").headers["content-type"].startswith("text/javascript")
    schema = client.get("/api/openapi.json").json()
    assert "/api/v1/projects" in schema["paths"] and "/pt/" not in schema["paths"]
