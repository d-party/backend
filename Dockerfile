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

# No system packages are needed: psycopg[binary] bundles libpq, and the former
# system-cron retention job has been removed (reactions are folded into
# ReactionStat on room end; see streamer/cron.py).

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
# autobahn (daphne 経由) は NVX CFFI 拡張のコンパイルに失敗すると pure-Python
# wheel へのフォールバックを拒否する。arm64 ネイティブビルドでこれに当たるため、
# pure-Python ビルドを明示する（NVX は UTF-8 検証の最適化にすぎず挙動は同じ）。
RUN --mount=type=cache,target=/root/.cache/uv \
    AUTOBAHN_USE_NVX=0 uv sync --frozen --no-install-project

COPY . .

EXPOSE 8000

CMD ["sh", "entrypoint.sh"]
