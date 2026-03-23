# openeo-workspace-service

Reference Python implementation of the
[**openEO Workspaces Extension**](https://github.com/Open-EO/openeo-api/blob/master/extensions/workspaces/openapi.yaml)
(v0.1.0).

The service lets users connect external cloud storage (S3, Azure Blob, GCS) to
an openEO back-end so that batch-job results can be written directly to their
own buckets.

---

## API surface

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/workspace_providers` | List supported storage providers (public) |
| `GET` | `/workspaces` | List the caller's workspaces |
| `POST` | `/workspaces` | Create **or** register a workspace |
| `GET` | `/workspaces/{workspace_id}` | Full workspace metadata |
| `PATCH` | `/workspaces/{workspace_id}` | Update title / description |
| `DELETE` | `/workspaces/{workspace_id}` | Remove a workspace |

Interactive docs are available at `/docs` (Swagger UI) and `/redoc` once the
service is running.

---

## Quick-start (local SQLite, no cloud credentials needed)

```bash
git clone https://github.com/Open-EO/openeo-workspace-service
cd openeo-workspace-service
pip install -e ".[dev]"

# Run with auto-created SQLite database (dev mode – no OIDC validation)
openeo-workspace-service
# → http://localhost:8000
```

Try it out:

```bash
# List providers (no auth required)
curl http://localhost:8000/workspace_providers | python -m json.tool

# Create a workspace (dev mode: any Bearer token is treated as user id)
curl -s -X POST http://localhost:8000/workspaces \
  -H "Authorization: Bearer myuser" \
  -H "Content-Type: application/json" \
  -d '{"intent":"create","type":"S3","title":"My S3 workspace","parameters":{"aws_access_key_id":"KEY","aws_secret_access_key":"SECRET","bucket_name":"my-bucket"}}' \
  -D -

# List workspaces
curl http://localhost:8000/workspaces -H "Authorization: Bearer myuser" | python -m json.tool
```

---

## Production deployment (Docker Compose + PostgreSQL)

```bash
cp .env.example .env  # edit as needed
docker compose up --build
```

The service runs on `http://localhost:8000`.  Run database migrations once:

```bash
docker compose exec workspace-service alembic upgrade head
```

---

## Configuration

All settings are read from environment variables (prefix `OPENEO_WS_`) or a
`.env` file.

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENEO_WS_DATABASE_URL` | `sqlite+aiosqlite:///./workspaces.db` | Async SQLAlchemy URL |
| `OPENEO_WS_PUBLIC_URL` | `https://openeo.example/api/v1` | Base URL for Location headers |
| `OPENEO_WS_OIDC_DISCOVERY_URL` | *(empty)* | OIDC discovery URL; empty = dev mode |
| `OPENEO_WS_DEFAULT_WORKSPACE_PROVIDER` | *(empty)* | Provider used when `type` is omitted |
| `OPENEO_WS_PAGE_SIZE_DEFAULT` | `25` | Default page size for list endpoints |
| `OPENEO_WS_PAGE_SIZE_MAX` | `100` | Maximum page size |
| `OPENEO_WS_LOG_LEVEL` | `INFO` | Python logging level |

---

## Authentication

Bearer tokens are validated against the configured OIDC provider.  When
`OPENEO_WS_OIDC_DISCOVERY_URL` is **empty** (development mode) the token
string is used directly as the user identifier – no real IdP is required.

---

## Workspace providers

Three providers are built in.  All cloud SDK packages are optional runtime
dependencies; the service will start without them but will mark workspaces as
`unavailable` if the required SDK is missing.

### Amazon S3 / S3-compatible

| Parameter | Required | Description |
|-----------|----------|-------------|
| `aws_access_key_id` | ✓ | AWS access key ID |
| `aws_secret_access_key` | ✓ | AWS secret access key |
| `bucket_name` | ✓ | S3 bucket name |
| `region_name` | – | AWS region (default: `us-east-1`) |
| `endpoint_url` | – | Custom endpoint for MinIO / Ceph etc. |

> **Note:** deleting a workspace registration does **not** delete the S3
> bucket, to prevent accidental data loss.

### Azure Blob Storage

| Parameter | Required | Description |
|-----------|----------|-------------|
| `account_name` | ✓ | Storage account name |
| `account_key` | ✓ | Storage account key |
| `container_name` | ✓ | Blob container name |

### Google Cloud Storage

| Parameter | Required | Description |
|-----------|----------|-------------|
| `project_id` | ✓ | GCP project ID |
| `bucket_name` | ✓ | GCS bucket name |
| `service_account_json` | ✓ | JSON string of service-account credentials |
| `location` | – | Bucket location (default: `US`) |

### Adding a custom provider

```python
# my_package/providers/myprovider.py
from openeo_workspace_service.providers.base import BaseWorkspaceProvider, register_provider
from openeo_workspace_service.models.schemas import WorkspaceProvider

@register_provider("MYPROVIDER")
class MyProvider(BaseWorkspaceProvider):
    @property
    def metadata(self) -> WorkspaceProvider:
        return WorkspaceProvider(title="My Provider", intents=["create"], parameters={})

    async def provision(self, record): ...
    async def delete(self, record): ...
```

Then import your module before the app starts (e.g. in a startup hook or by
adding the import to `openeo_workspace_service/providers/__init__.py`).

---

## Running tests

```bash
pytest tests/ -v
# With coverage:
coverage run -m pytest tests/ && coverage report
```

---

## Project structure

```
openeo-workspace-service/
├── openeo_workspace_service/
│   ├── main.py              # FastAPI app factory + CLI entry point
│   ├── config.py            # Settings (pydantic-settings)
│   ├── auth.py              # Bearer token validation
│   ├── db/
│   │   ├── models.py        # SQLAlchemy ORM
│   │   └── session.py       # Async engine + session factory
│   ├── models/
│   │   └── schemas.py       # Pydantic request/response schemas
│   ├── providers/
│   │   ├── base.py          # Abstract provider + registry
│   │   ├── s3.py            # Amazon S3 provider
│   │   ├── azure.py         # Azure Blob Storage provider
│   │   └── gcs.py           # Google Cloud Storage provider
│   └── routers/
│       ├── providers.py     # GET /workspace_providers
│       └── workspaces.py    # /workspaces CRUD
├── alembic/                 # Database migrations
├── tests/                   # pytest test suite
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## Contributing

Pull requests are welcome.  Please ensure `ruff check` and `pytest` pass
before opening a PR.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
