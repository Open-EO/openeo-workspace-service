# Contributing to openeo-workspace-service

Thank you for considering a contribution! This document explains how to set up
the development environment, the code conventions we follow, and the pull
request workflow.

---

## Table of Contents

- [Development Setup](#development-setup)
- [Project Architecture](#project-architecture)
- [Code Conventions](#code-conventions)
- [Running Tests](#running-tests)
- [Adding a New Endpoint](#adding-a-new-endpoint)
- [Elasticsearch Schema Changes](#elasticsearch-schema-changes)
- [Pull Request Checklist](#pull-request-checklist)

---

## Development Setup

### Prerequisites

- Python 3.11 or 3.12
- Docker + Docker Compose (for the local stack)
- `make` (optional but recommended)

### Install

```bash
git clone https://github.com/Open-EO/openeo-workspace-service.git
cd openeo-workspace-service

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

make install-dev                   # installs app + dev extras + pre-commit hooks
```

### Start the local stack

```bash
make up        # starts Elasticsearch + Keycloak + the service
make get-token # prints a Bearer token for alice (workspace-user role)
```

### Run with hot-reload (no image rebuild)

```bash
docker compose \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.override.yml \
  up workspace-svc
```

---

## Project Architecture

```
src/openeo_workspace_service/
│
├── api/              FastAPI routers and middleware
│   ├── workspaces.py       Public workspace CRUD (openEO spec)
│   ├── workspace_providers.py  Provider catalogue
│   ├── admin.py            Admin operations (workspace-admin role)
│   ├── internal.py         Provisioning worker callback endpoint
│   ├── health.py           Liveness + readiness probes
│   ├── middleware.py       X-Request-ID injection
│   ├── rate_limit.py       Per-user sliding-window rate limiter
│   ├── pagination.py       Offset pagination helpers + link builder
│   ├── exceptions.py       Global FastAPI exception handlers
│   └── openapi.py          Custom OpenAPI schema (security schemes, tags)
│
├── auth/
│   └── keycloak.py         JWKS caching, JWT validation, FastAPI deps
│
├── config/
│   ├── settings.py         All config via pydantic-settings
│   └── logging.py          structlog configuration (JSON / console)
│
├── db/
│   ├── elasticsearch.py    Async ES client, index mappings, repositories
│   ├── aliases.py          Index alias creation + zero-downtime swap
│   └── migrations.py       CLI: status / migrate / delete
│
└── models/
    ├── workspace.py        Pydantic v2 domain models (mirrors OpenAPI spec)
    └── id_generator.py     Human-readable workspace ID slug generation
```

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| **Per-user `owner_id` scoping** | Every workspace document stores the Keycloak `sub` claim as `owner_id`. All repository queries add an owner filter, preventing cross-user data leakage without a separate ACL system. |
| **Single-index per entity type** | One index for workspaces, one for providers. Simple to operate and sufficient for expected scale. Sharding can be tuned via `number_of_shards`. |
| **Index aliases** | Physical indices are versioned (`_v1`). Aliases provide a stable query target and enable zero-downtime re-indexing via atomic alias swap. |
| **Async throughout** | All I/O uses `async`/`await` (ES client, Keycloak JWKS fetch, route handlers) to maximise concurrency under uvicorn. |
| **No ORM** | Direct ES query construction keeps the code readable and avoids an abstraction layer over a document store that doesn't fit the relational ORM model. |
| **JWKS key cache** | 5-minute TTL in-process cache avoids hitting Keycloak on every request while still rotating automatically after key rollover. |
| **Slug IDs** | Workspace IDs derived from the title (e.g. `my-analysis-a1b2c3`) are more debuggable than raw UUIDs while remaining unique. |

---

## Code Conventions

- **Python 3.11+** — use `str | None` union syntax, `match` statements where appropriate.
- **`from __future__ import annotations`** at the top of every module.
- **Pydantic v2** — use `model_validate`, `model_dump`, `ConfigDict`. Do not use v1 aliases.
- **structlog** for all logging. Never use `print()` or `logging.getLogger()` directly.
- **Type annotations everywhere** — `mypy --strict` must pass.
- **ruff** for linting and formatting. Pre-commit hooks enforce this on every commit.
- **Docstrings** on all public functions and classes (Google style).
- **No late imports** inside function bodies (except unavoidable circular-import breaking).

---

## Running Tests

```bash
make test              # full suite (unit + integration), no real ES/Keycloak needed
make test-unit         # unit tests only
make test-integration  # integration tests only
make cov               # coverage with HTML report → htmlcov/index.html
```

All tests use in-memory fakes or `AsyncMock` — the CI pipeline never requires
a live Elasticsearch or Keycloak instance.

### Test layout

```
tests/
├── conftest.py            Shared fixtures: regular_user, admin_user, make_client
├── unit/
│   ├── test_models.py     Pydantic model validation
│   ├── test_auth.py       JWT validation (mocked JWKS)
│   ├── test_repositories.py  ES repository layer (AsyncMock ES client)
│   ├── test_aliases.py    Index alias management
│   ├── test_pagination.py Pagination link builder
│   ├── test_id_generator.py  Slug ID generation
│   ├── test_settings.py   Settings validation and derived URLs
│   ├── test_health.py     Liveness / readiness probes
│   ├── test_middleware.py Request ID propagation + error body shape
│   └── test_rate_limit.py Rate-limit bucket logic and 429 response
└── integration/
    ├── test_api.py        Full workspace CRUD routes
    ├── test_admin.py      Admin router (role enforcement)
    ├── test_pagination.py X-Total-Count header + next/prev links
    └── test_internal.py   Internal provisioning status endpoint
```

---

## Adding a New Endpoint

1. **Define the Pydantic model** in `models/workspace.py` (or a new file).
2. **Add the route** in the appropriate router file under `api/`.
3. **Add a repository method** in `db/elasticsearch.py` if the route needs a new ES query.
4. **Register the router** in `app.py` if it's a new file.
5. **Write tests**: at minimum one happy-path and one error-path integration test.
6. **Update `CHANGELOG.md`** under `[Unreleased]`.

---

## Elasticsearch Schema Changes

When you need to add or change an indexed field:

1. **Add the field** to the appropriate mapping dict in `db/elasticsearch.py`
   (`WORKSPACE_MAPPING` or `PROVIDER_MAPPING`).
2. **Create a new versioned index** (e.g. bump `_v1` → `_v2`).
3. **Migrate data** using the migration CLI:
   ```bash
   python -m openeo_workspace_service.db.migrations migrate \
     --source openeo_workspaces_v1 \
     --dest   openeo_workspaces_v2
   ```
4. **Swap the alias** atomically:
   ```python
   from openeo_workspace_service.db.aliases import swap_alias
   await swap_alias(es, "openeo_workspaces", "openeo_workspaces_v1", "openeo_workspaces_v2")
   ```
5. **Delete the old index** once you've verified the migration:
   ```bash
   python -m openeo_workspace_service.db.migrations delete \
     --index openeo_workspaces_v1
   ```
6. **Update `ELASTICSEARCH_INDEX_PREFIX`** in settings if the version bump
   changes the default index name.

---

## Pull Request Checklist

Before opening a PR, confirm:

- [ ] `make check` passes (ruff lint + format + mypy)
- [ ] `make test` passes with no failures
- [ ] New behaviour is covered by tests
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] Docstrings added / updated for public functions
- [ ] No secrets, credentials, or personal data committed
- [ ] PR description explains *why* (not just *what*) the change makes
