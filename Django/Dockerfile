# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

# Bring in the uv binary from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBCONF_NOWARNINGS=yes \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Keep the virtualenv outside the app dir so a bind-mount over the source
    # (docker-compose) does not shadow the installed dependencies.
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
