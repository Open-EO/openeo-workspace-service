# ---------------------------------------------------------------------------
# Multi-stage Dockerfile for openeo-workspace-service
# ---------------------------------------------------------------------------

# ---- build stage -----------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --upgrade pip setuptools wheel

COPY pyproject.toml .
COPY src/ src/

RUN pip wheel --no-deps --wheel-dir /wheels .


# ---- runtime stage ---------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="openeo-workspace-service" \
      org.opencontainers.image.description="VITO openEO Workspace Service" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.licenses="Apache-2.0"

# Non-root user
RUN addgroup --system appgroup \
 && adduser --system --ingroup appgroup --no-create-home appuser

WORKDIR /app

# Install runtime dependencies (explicit – no extras that require src layout)
RUN pip install --no-cache-dir \
        "fastapi>=0.111.0" \
        "uvicorn[standard]>=0.29.0" \
        "pydantic>=2.7.0" \
        "pydantic-settings>=2.2.0" \
        "elasticsearch[async]>=8.13.0" \
        "python-jose[cryptography]>=3.3.0" \
        "httpx>=0.27.0" \
        "python-multipart>=0.0.9" \
        "structlog>=24.1.0" \
        "tenacity>=8.3.0"

# Install the application wheel built in the builder stage
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels openeo-workspace-service \
 && rm -rf /wheels

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c \
        "import urllib.request, sys; \
         r = urllib.request.urlopen('http://localhost:8000/health', timeout=4); \
         sys.exit(0 if r.status == 200 else 1)"

CMD ["openeo-workspace-service"]
