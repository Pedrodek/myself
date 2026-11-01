# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-31

First release of the hub: phases F0-F3 of `PLANO_DE_IMPLEMENTACAO.md`.

### Added
- FastAPI application factory with server-rendered pages (Jinja2) and HTMX navigation that swaps only the
  title and content, with out-of-band updates for the navigation and language switcher.
- Pages: home, experience (filter by technology), projects and case studies (search and tags),
  skills, printable résumé (with PDF download), about the site, localized 404/500 pages.
- Content in YAML/Markdown validated with Pydantic, with cross-reference and pt/en parity checks
  (`python -m app content validate`).
- Portuguese (Brazil) and English through Babel catalogs, language negotiation at `/`, `hreflang` and sitemap.
- Strict Content-Security-Policy with named profiles, security headers, request ids, body-size limit and
  structured logging.
- Read-only JSON API under `/api/v1` and an OpenAPI explorer (Swagger UI pinned with SRI).
- Node-free asset pipeline: vendored htmx/Alpine (CSP build)/xterm verified by SHA-384, Tailwind CSS v4 with
  fingerprinted output.
- Light/dark theme without flash, mobile menu, skip link, focus management and screen reader announcements.
- SEO: canonical URLs, Open Graph, JSON-LD, `robots.txt`, `sitemap.xml`, `security.txt`.
- CLI (`python -m app`): `dev`, `serve`, `assets`, `content`, `i18n`, `export` (PDF and Open Graph image).
- Tests (unit, integration, browser), ruff, mypy strict, djlint, pre-commit, GitHub Actions matrix
  (Linux and Windows, Python 3.11-3.14), Dependabot, Dockerfile and Compose file.
