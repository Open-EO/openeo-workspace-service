# feat: initial Python service implementation (Workspaces Extension v0.1.0)

## Summary

This PR introduces a complete reference implementation of the
[openEO Workspaces Extension](https://github.com/Open-EO/openeo-api/blob/master/extensions/workspaces/openapi.yaml)
(v0.1.0) as an async Python/FastAPI service.

## What's included

### API coverage

All six endpoints from the spec are implemented:

| Method | Path | Status |
|--------|------|--------|
| `GET` | `/workspace_providers` | ✅ |
| `GET` | `/workspaces` | ✅ |
| `POST` | `/workspaces` (create + register) | ✅ |
| `GET` | `/workspaces/{workspace_id}` | ✅ |
| `PATCH` | `/workspaces/{workspace_id}` | ✅ |
| `DELETE` | `/workspaces/{workspace_id}` | ✅ |

### Architecture

- **FastAPI** with full async support (Python 3.10+)
- **SQLAlchemy 2 async ORM** with **Alembic** migrations
- **Pydantic v2** request/response models that mirror the OpenAPI schema exactly
- **OIDC Bearer token validation** via `python-jose`; dev mode (token = user id) when no OIDC URL is set
- **Provider plugin system** — register new storage backends with a single `@register_provider("NAME")` decorator

### Built-in providers

| Provider | Intent | Notes |
|----------|--------|-------|
| Amazon S3 / S3-compatible | create + register | Uses `boto3`; bucket is **not** deleted on workspace removal |
| Azure Blob Storage | create + register | Uses `azure-storage-blob` |
| Google Cloud Storage | create + register | Uses `google-cloud-storage` |

All cloud SDKs are **optional runtime dependencies** — the service starts without them.

### Tests

- `tests/test_providers.py` — HTTP-level tests for `GET /workspace_providers`
- `tests/test_workspaces.py` — Full CRUD integration tests with a mocked provider
- `tests/test_providers_unit.py` — Unit tests for registry and parameter validation
- In-memory SQLite so no external services are needed to run the suite

### DevOps

- `Dockerfile` (multi-stage)
- `docker-compose.yml` with PostgreSQL
- GitHub Actions CI (lint + test on Python 3.10/3.11/3.12 + Docker build)

## How to review

```bash
pip install -e ".[dev]"
pytest tests/ -v
openeo-workspace-service   # → http://localhost:8000/docs
```

## Open questions / future work

- [ ] Background task provisioning (currently synchronous; could be moved to Celery/ARQ)
- [ ] Rate limiting per user
- [ ] Audit log for workspace lifecycle events
- [ ] Workspace sharing between users
