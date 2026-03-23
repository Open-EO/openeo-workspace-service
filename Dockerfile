FROM python:3.12-slim AS base

WORKDIR /app

# System deps (for asyncpg native extensions).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

# ── Production image ──────────────────────────────────────────────────────────
FROM base AS production

ENV OPENEO_WS_LOG_LEVEL=INFO
EXPOSE 8000

CMD ["python", "-m", "openeo_workspace_service.main"]
