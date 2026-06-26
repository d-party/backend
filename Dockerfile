# syntax=docker/dockerfile:1

# Bring in the uv binary from the official image as a named stage so the COPY
# below references a previously defined FROM alias (hadolint DL3022).
FROM ghcr.io/astral-sh/uv:0.9 AS uv

FROM python:3.14-slim-bookworm

COPY --from=uv /uv /uvx /bin/

# Keep UV_PROJECT_ENVIRONMENT (the virtualenv) outside the app dir so a
# bind-mount over the source (docker-compose) does not shadow the installed
# dependencies.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBCONF_NOWARNINGS=yes \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /usr/src/app

# cron drives the periodic retention cleanup (see entrypoint.sh).
# psycopg[binary] bundles libpq, so no system postgres client is required.
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY . .

EXPOSE 8000

CMD ["sh", "entrypoint.sh"]
