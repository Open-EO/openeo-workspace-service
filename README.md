# openeo-workspace-service

**VITO implementation of the [openEO Workspaces Extension API](https://github.com/Open-EO/openeo-api/blob/master/extensions/workspaces/openapi.yaml)**

Built with **FastAPI**, backed by **Elasticsearch**, and secured with **Keycloak** (OIDC / Bearer JWT).

---

## Table of Contents

- [Architecture](#architecture)
- [API Overview](#api-overview)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Development](#local-development)
- [Configuration Reference](#configuration-reference)
- [Authentication & Authorisation](#authentication--authorisation)
- [Project Layout](#project-layout)
- [Running Tests](#running-tests)
- [Seeding Providers](#seeding-providers)

---

## Architecture

```
┌─────────────────────────────────────┐
│           openEO Client             │
│  (openeo-python-client / curl / …)  │
└────────────────┬────────────────────┘
                 │  HTTPS  Bearer JWT
                 ▼
┌─────────────────────────────────────┐
│      openeo-workspace-service       │
│  FastAPI · Pydantic v2 · structlog  │
│                                     │
│  ┌──────────────┐ ┌──────────────┐  │
│  │  /workspace_ │ │  /workspaces │  │
│  │  providers   │ │  (CRUD)      │  │
│  └──────────────┘ └──────────────┘  │
└──────────┬──────────────┬───────────┘
           │              │
           ▼              ▼
┌──────────────┐  ┌──────────────────┐
│ Elasticsearch│  │     Keycloak     │
│  (documents) │  │  (JWKS / OIDC)   │
└──────────────┘  └──────────────────┘
```

Every request to a protected endpoint must carry a valid **Bearer** JWT issued by Keycloak.
The service validates the token against Keycloak's JWKS endpoint (keys are cached for 5 minutes).
The `sub` claim is used as the workspace `owner_id` to enforce per-user access control.

---

## API Overview

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/workspace_providers` | Optional | List available storage providers |
| `GET` | `/workspaces` | Required | List the caller's workspaces |
| `POST` | `/workspaces` | Required | Create or register a workspace |
| `GET` | `/workspaces/{id}` | Required | Full workspace metadata |
| `PATCH` | `/workspaces/{id}` | Required | Update title / description |
| `DELETE` | `/workspaces/{id}` | Required | Delete a workspace |
| `GET` | `/health` | None | Liveness probe |

Interactive docs are available at **`/docs`** (Swagger UI) and **`/redoc`**.

### POST /workspaces – intents

The body must include an `intent` discriminator:

**`intent: create`** – ask the back-end to provision a new workspace:
```json
{
  "intent": "create",
  "title": "My Analysis Workspace",
  "type": "S3",
  "parameters": { "region": "eu-west-1" }
}
```

**`intent: register`** – attach an existing external storage location:
```json
{
  "intent": "register",
  "type": "S3",
  "url": "https://my-bucket.s3.eu-west-1.amazonaws.com",
  "parameters": {
    "aws_access_key_id": "AKIAI…",
    "aws_secret_access_key": "…",
    "bucket_name": "my-bucket"
  }
}
```

---

## Quick Start (Docker)

```bash
# 1. Clone
git clone https://github.com/Open-EO/openeo-workspace-service.git
cd openeo-workspace-service

# 2. Configure
cp .env.example .env
# Edit .env if needed (defaults work out-of-the-box with docker compose)

# 3. Start all services
docker compose -f docker/docker-compose.yml up -d

# 4. Check health
curl http://localhost:8000/health
# {"status":"ok"}

# 5. Get a token (pre-seeded user: alice / alice123)
./scripts/get_token.sh alice alice123

# 6. Call the API
TOKEN=<paste token here>
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/workspaces
```

**Services started:**

| Service | URL |
|---------|-----|
| Workspace API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| Keycloak admin | http://localhost:8080 (admin / admin) |
| Elasticsearch | http://localhost:9200 |

> **Kibana** (ES UI) is available with `docker compose --profile debug up`.

---

## Local Development

### Prerequisites

- Python 3.11+
- A running Elasticsearch (≥ 8.x) and Keycloak (≥ 24) – use Docker for convenience

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run

```bash
cp .env.example .env
# Edit .env to point to your ES + Keycloak instances
openeo-workspace-service
# or: uvicorn openeo_workspace_service.main:app --reload
```

### Code quality

```bash
# Lint + format
ruff check src tests
ruff format src tests

# Type-check
mypy src
```

---

## Configuration Reference

All settings are loaded from environment variables or a `.env` file.

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `production` | Deployment environment label |
| `DEBUG` | `false` | Enable debug logging and hot-reload |
| `SERVER_HOST` | `0.0.0.0` | Bind address |
| `SERVER_PORT` | `8000` | Listen port |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `ELASTICSEARCH_URL` | `http://localhost:9200` | ES cluster URL |
| `ELASTICSEARCH_USERNAME` | *(none)* | ES basic auth username |
| `ELASTICSEARCH_PASSWORD` | *(none)* | ES basic auth password |
| `ELASTICSEARCH_CA_CERTS` | *(none)* | Path to CA bundle for TLS |
| `ELASTICSEARCH_VERIFY_CERTS` | `true` | Verify ES TLS certificates |
| `ELASTICSEARCH_INDEX_PREFIX` | `openeo_workspaces` | Prefix for ES index names |
| `KEYCLOAK_URL` | `http://localhost:8080` | Keycloak base URL |
| `KEYCLOAK_REALM` | `openeo` | Keycloak realm |
| `KEYCLOAK_CLIENT_ID` | `workspace-service` | OIDC client ID |
| `KEYCLOAK_CLIENT_SECRET` | *(none)* | OIDC client secret (confidential clients) |
| `JWT_ALGORITHMS` | `RS256` | Accepted JWT signing algorithms |
| `JWT_AUDIENCE` | *(keycloak_client_id)* | Expected `aud` claim |
| `DEFAULT_WORKSPACE_PROVIDER` | *(none)* | Fallback provider for `intent=create` |

---

## Authentication & Authorisation

### Token validation

1. The service reads `KEYCLOAK_URL` + `KEYCLOAK_REALM` to derive the JWKS URI:
   `{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs`
2. On each request the JWT header is decoded (without verification) to extract `kid`.
3. The matching public key is looked up in the JWKS cache (TTL 5 min) and used to verify the signature, expiry, issuer, and audience.
4. The `sub` claim becomes the `owner_id` stored alongside every workspace document.

### Role-based access

Keycloak realm roles are extracted from the `realm_access.roles` claim.
The `RequireRole` dependency factory can be used in any route:

```python
from openeo_workspace_service.auth.keycloak import RequireRole

@router.delete("/admin/workspaces/{id}")
async def admin_delete(user = Depends(RequireRole("workspace-admin"))):
    ...
```

Pre-seeded roles (see `docker/keycloak/realm-export.json`):

| Role | Description |
|------|-------------|
| `workspace-user` | Manage own workspaces |
| `workspace-admin` | Manage all workspaces |

---

## Project Layout

```
openeo-workspace-service/
├── src/openeo_workspace_service/
│   ├── main.py               # uvicorn entry point
│   ├── app.py                # FastAPI factory + lifespan hooks
│   ├── config/
│   │   └── settings.py       # pydantic-settings configuration
│   ├── models/
│   │   └── workspace.py      # Pydantic v2 domain models (mirrors OpenAPI spec)
│   ├── db/
│   │   └── elasticsearch.py  # Client, index mappings, repositories
│   ├── auth/
│   │   └── keycloak.py       # JWKS caching, JWT validation, FastAPI deps
│   └── api/
│       ├── workspace_providers.py   # GET /workspace_providers
│       └── workspaces.py            # /workspaces CRUD
├── tests/
│   ├── unit/
│   │   ├── test_models.py    # Pydantic model validation tests
│   │   └── test_auth.py      # Auth unit tests (mocked JWKS)
│   └── integration/
│       └── test_api.py       # Full route tests (in-memory ES + auth overrides)
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── keycloak/
│       └── realm-export.json # Pre-seeded realm, clients, and users
├── scripts/
│   ├── seed_providers.py     # Seed provider catalogue into ES
│   └── get_token.sh          # Get a Keycloak token for manual testing
├── .env.example
└── pyproject.toml
```

---

## Running Tests

```bash
# All tests (unit + integration) — no real ES or Keycloak required
pytest

# With coverage report
pytest --cov=openeo_workspace_service --cov-report=html
open htmlcov/index.html
```

---

## Seeding Providers

On startup the service automatically seeds three built-in providers (`S3`, `GCS`, `AZURE_BLOB`) into Elasticsearch if the provider index is empty.

To re-seed manually (e.g. after clearing the index):

```bash
python scripts/seed_providers.py --reset
```

To add a custom provider, upsert it directly via the `ProviderRepository`:

```python
from openeo_workspace_service.db.elasticsearch import ProviderRepository, get_es_client

async with get_es_client() as es:
    repo = ProviderRepository(es)
    await repo.upsert("MY_PROVIDER", {
        "title": "My Custom Provider",
        "intents": ["register"],
        "parameters": {
            "endpoint": {"description": "Storage endpoint URL", "type": "string"},
        },
        "links": [],
    })
```

---

## License

Apache 2.0 – see [LICENSE](LICENSE).
