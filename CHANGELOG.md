# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- `GET /ready` deep readiness probe checking Elasticsearch cluster health and Keycloak JWKS reachability.
- `PUT /internal/workspaces/{id}/status` — internal endpoint for async provisioning workers to report workspace state changes (guarded by `INTERNAL_API_KEY`).
- `GET /admin/workspaces`, `GET /admin/workspaces/{id}`, `DELETE /admin/workspaces/{id}` — cross-user admin operations requiring the `workspace-admin` Keycloak role.
- `POST /admin/providers/{name}`, `DELETE /admin/providers/{name}` — admin provider catalogue management.
- `X-Request-ID` middleware — every request and response carries a trace ID; bound to structlog context automatically.
- Offset-based pagination with `next` / `prev` links on `GET /workspaces` (query params: `limit`, `offset`).
- `python -m openeo_workspace_service.db.migrations` CLI — `status`, `migrate` (zero-downtime reindex), and `delete` commands.
- Structured logging via `structlog` — JSON in production, colourised console in development.
- Global exception handlers returning openEO-shaped error bodies (`id`, `code`, `message`, `links`).
- PEP 561 `py.typed` marker.
- Pre-commit hooks (ruff lint + format, trailing whitespace, YAML/TOML validation).
- GitHub Actions CI workflow: lint, test matrix (Python 3.11 + 3.12), Docker build.
- Full test suite: 50+ tests across unit and integration layers, no real ES or Keycloak required.

---

## [0.1.0] – 2026-03-01

### Added
- Initial implementation of the [openEO Workspaces Extension API](https://github.com/Open-EO/openeo-api/blob/master/extensions/workspaces/openapi.yaml).
- `GET /workspace_providers` — list supported storage providers (S3, GCS, Azure Blob).
- `GET /workspaces` — list workspaces owned by the authenticated user.
- `POST /workspaces` — create (`intent: create`) or register (`intent: register`) a workspace.
- `GET /workspaces/{id}` — fetch full workspace metadata.
- `PATCH /workspaces/{id}` — update workspace title / description.
- `DELETE /workspaces/{id}` — remove a workspace.
- `GET /health` — liveness probe.
- Elasticsearch 8.x backing store with typed index mappings for workspaces and providers.
- Keycloak OIDC authentication via RS256 JWT validation with JWKS key caching (5 minute TTL).
- Per-user workspace isolation: `sub` claim stored as `owner_id`; all queries are owner-scoped.
- `RequireRole` FastAPI dependency factory for role-based access control.
- Automatic provider seeding on startup (S3, GCS, AZURE_BLOB).
- Multi-stage Docker build with non-root runtime user.
- `docker-compose.yml` dev stack with Elasticsearch, Keycloak (pre-imported realm), and the service.
- `scripts/get_token.sh` convenience script for fetching Keycloak tokens.
- `scripts/seed_providers.py` standalone provider seeding script.
- `pyproject.toml` with ruff, mypy, and pytest configuration.
