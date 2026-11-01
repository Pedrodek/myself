# syntax=docker/dockerfile:1

# ---- builder: installs dependencies and builds the front-end assets (Tailwind binary stays here) ----
FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TAILWINDCSS_BIN_DIR=/opt/tailwind

WORKDIR /src
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt requirements-dev.txt ./
# The build-only tool is read from requirements-dev.txt so there is a single pin.
RUN pip install --retries 10 --timeout 120 -r requirements.txt \
    && pip install --retries 10 --timeout 120 "$(grep -E '^pytailwindcss==' requirements-dev.txt | cut -d' ' -f1)"

COPY . .
RUN mkdir -p build/downloads \
    && python -m app assets sync \
    && python -m app assets build \
    && python -m app content validate

# ---- runtime: only the virtualenv and the application, running as an unprivileged user ----
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    HUB_ENV=prod \
    HUB_DATA_DIR=/data

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /app /data \
    && chown app:app /data

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --from=builder --chown=app:app /src/app ./app
COPY --from=builder --chown=app:app /src/content ./content
COPY --from=builder --chown=app:app /src/build ./build
COPY --from=builder --chown=app:app /src/assets.lock.json ./assets.lock.json

USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]

CMD ["python", "-m", "app", "serve", "--host", "0.0.0.0", "--port", "8000"]
