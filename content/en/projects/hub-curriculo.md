---
title: Interactive resume hub
summary: This very site, a résumé where every section demonstrates a Python skill.
repo: Pedrodek/myself
skills: [python, fastapi, pydantic, htmx, tailwind, pytest, docker, github-actions]
tags: [web, testing, devops]
featured: true
order: 1
year: 2026
---
## Problem

A PDF résumé lists technologies but proves nothing. I wanted reviewers to *use* what I built, read the code and check the quality instead of taking my word for it.

## Solution

A server-rendered site built with FastAPI and Jinja2, using HTMX for smooth navigation and Alpine.js for small interface details. The content lives in YAML and Markdown files validated by Pydantic, in Portuguese and English.

## Architecture

The core is an asynchronous application with a single responsibility per module. Content validation happens at startup, so a typo never reaches production:

```python
class Skill(BaseModel):
    slug: str
    name: str
    level: int = Field(ge=1, le=5)
```

The Content-Security-Policy is strict: no inline scripts and no `eval`.

## Results

- Pages work without JavaScript and are enhanced by HTMX.
- Test coverage above 85%, with strict type checking.
- Continuous integration on Linux and Windows.

## Lessons learned

Locking down the CSP from day one was cheap and avoided rework. Adopting heavy visual libraries, however, required page-specific policy profiles.
