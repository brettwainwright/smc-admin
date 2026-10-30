# syntax=docker/dockerfile:1

# ---- Build: install dependencies into /app/.venv with uv ----
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project


# ---- Runtime: slim image with just the venv and app code ----
FROM python:3.12-slim

RUN useradd --create-home --uid 1000 app \
    # SQLite lives here; compose mounts the app-data volume over it so the DB survives rebuilds
    && mkdir -p /app/data && chown app:app /app/data

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY manage.py ./
COPY smc ./smc
COPY schedule ./schedule

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/db.sqlite3

# Admin CSS/JS (and photos) into /app/staticfiles, which runbolt serves at /static.
# Settings are required at import time; these build-only placeholders never reach the runtime image env.
RUN SIGNUP_KEY=build USERNAME=build PASSWORD=build SECRET_KEY=build DB_PATH=/tmp/build.sqlite3 \
    python manage.py collectstatic --noinput

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# Settings come from environment variables at runtime (compose.yaml: env_file: .env).
# Apply migrations and sync the admin user from .env on every start, then serve.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py ensure_admin && exec python manage.py runbolt --host 0.0.0.0 --port 8000"]
