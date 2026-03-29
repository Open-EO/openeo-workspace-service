"""
Elasticsearch integration layer.

Provides:
  - Async client factory (context manager + FastAPI dependency)
  - Index creation with mappings
  - WorkspaceRepository  – CRUD against the workspace index
  - ProviderRepository   – read-only access to the provider catalogue
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import structlog
from elasticsearch import AsyncElasticsearch, NotFoundError
from tenacity import retry, stop_after_attempt, wait_exponential

from openeo_workspace_service.config.settings import get_settings
from openeo_workspace_service.models.workspace import (
    WorkspaceReady,
    WorkspaceStatus,
    WorkspaceUnavailable,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Index mappings
# ---------------------------------------------------------------------------

WORKSPACE_MAPPING: dict[str, Any] = {
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "id": {"type": "keyword"},
            "owner_id": {"type": "keyword"},  # Keycloak subject claim
            "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "description": {"type": "text"},
            "type": {"type": "keyword"},
            "status": {"type": "keyword"},
            "details": {"type": "text"},
            "quota": {"type": "long"},
            "url": {"type": "keyword"},
            "free": {"type": "long"},
            "properties": {"type": "object", "dynamic": True},
            "parameters": {"type": "object", "dynamic": True},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
        },
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 1,
    },
}

PROVIDER_MAPPING: dict[str, Any] = {
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "name": {"type": "keyword"},
            "title": {"type": "text"},
            "description": {"type": "text"},
            "deprecated": {"type": "boolean"},
            "experimental": {"type": "boolean"},
            "intents": {"type": "keyword"},
            "parameters": {"type": "object", "dynamic": True},
            "links": {"type": "object", "dynamic": True},
        },
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 1,
    },
}


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def _build_client() -> AsyncElasticsearch:
    settings = get_settings()

    kwargs: dict[str, Any] = {"hosts": [settings.elasticsearch_url]}

    if settings.elasticsearch_username and settings.elasticsearch_password:
        kwargs["basic_auth"] = (
            settings.elasticsearch_username,
            settings.elasticsearch_password,
        )

    if settings.elasticsearch_ca_certs:
        kwargs["ca_certs"] = settings.elasticsearch_ca_certs

    kwargs["verify_certs"] = settings.elasticsearch_verify_certs

    return AsyncElasticsearch(**kwargs)


@asynccontextmanager
async def get_es_client() -> AsyncIterator[AsyncElasticsearch]:
    """Async context manager that yields a connected Elasticsearch client."""
    client = _build_client()
    try:
        yield client
    finally:
        await client.close()


async def get_es() -> AsyncIterator[AsyncElasticsearch]:
    """FastAPI dependency that provides an Elasticsearch client per request."""
    async with get_es_client() as client:
        yield client


# ---------------------------------------------------------------------------
# Index initialisation
# ---------------------------------------------------------------------------


@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=10))
async def init_indices(es: AsyncElasticsearch) -> None:
    """Create indices if they do not already exist.  Retries on connection errors."""
    settings = get_settings()

    for index, mapping in (
        (settings.workspace_index, WORKSPACE_MAPPING),
        (settings.provider_index, PROVIDER_MAPPING),
    ):
        exists = await es.indices.exists(index=index)
        if not exists:
            await es.indices.create(index=index, body=mapping)
            logger.info("created elasticsearch index", index=index)
        else:
            logger.debug("elasticsearch index already exists", index=index)


# ---------------------------------------------------------------------------
# WorkspaceRepository
# ---------------------------------------------------------------------------


class WorkspaceRepository:
    """
    Thin async repository wrapping Elasticsearch for workspace documents.

    Each document stored in ES keeps an extra `owner_id` field that maps to
    the Keycloak subject so that authorisation checks can be enforced.
    """

    def __init__(self, es: AsyncElasticsearch) -> None:
        self._es = es
        self._index = get_settings().workspace_index

    # ---------------------------------------------------------------- helpers

    def _doc_to_workspace(self, doc: dict[str, Any]) -> WorkspaceReady | WorkspaceUnavailable:
        src = doc["_source"]
        status = WorkspaceStatus(src["status"])
        if status == WorkspaceStatus.ready:
            return WorkspaceReady(**{k: v for k, v in src.items() if k != "owner_id"})
        return WorkspaceUnavailable(**{k: v for k, v in src.items() if k != "owner_id"})

    # ----------------------------------------------------------------- CRUD

    async def get(self, workspace_id: str, owner_id: str) -> WorkspaceReady | WorkspaceUnavailable | None:
        try:
            resp = await self._es.get(index=self._index, id=workspace_id)
        except NotFoundError:
            return None
        src = resp["_source"]
        if src.get("owner_id") != owner_id:
            return None  # treat as not found for unauthorised access
        return self._doc_to_workspace(resp)

    def _build_filter_query(
        self,
        owner_id: str,
        status_filter: WorkspaceStatus | None = None,
        type_filter: str | None = None,
    ) -> dict[str, Any]:
        """Build an ES bool query scoped to owner_id with optional filters."""
        must: list[dict[str, Any]] = [{"term": {"owner_id": owner_id}}]
        if status_filter is not None:
            must.append({"term": {"status": status_filter.value}})
        if type_filter is not None:
            must.append({"term": {"type": type_filter.upper()}})
        if len(must) == 1:
            return must[0]  # simple term query — no bool wrapper needed
        return {"bool": {"must": must}}

    async def list(
        self,
        owner_id: str,
        limit: int = 10,
        offset: int = 0,
        status_filter: WorkspaceStatus | None = None,
        type_filter: str | None = None,
    ) -> list[WorkspaceReady | WorkspaceUnavailable]:
        query = self._build_filter_query(owner_id, status_filter, type_filter)
        resp = await self._es.search(
            index=self._index,
            body={
                "query": query,
                "from": offset,
                "size": limit,
                "sort": [{"created_at": "desc"}],
            },
        )
        return [self._doc_to_workspace(hit) for hit in resp["hits"]["hits"]]

    async def create(
        self,
        workspace_id: str,
        owner_id: str,
        doc: dict[str, Any],
    ) -> WorkspaceReady | WorkspaceUnavailable:
        now = datetime.now(UTC).isoformat()
        document = {
            **doc,
            "id": workspace_id,
            "owner_id": owner_id,
            "created_at": now,
            "updated_at": now,
        }
        await self._es.index(index=self._index, id=workspace_id, document=document)
        await self._es.indices.refresh(index=self._index)

        stored = await self._es.get(index=self._index, id=workspace_id)
        return self._doc_to_workspace(stored)

    async def update(self, workspace_id: str, owner_id: str, partial: dict[str, Any]) -> bool:
        existing = await self.get(workspace_id, owner_id)
        if existing is None:
            return False

        from datetime import datetime

        partial["updated_at"] = datetime.now(UTC).isoformat()
        await self._es.update(index=self._index, id=workspace_id, doc=partial)
        return True

    async def delete(self, workspace_id: str, owner_id: str) -> bool:
        existing = await self.get(workspace_id, owner_id)
        if existing is None:
            return False
        await self._es.delete(index=self._index, id=workspace_id)
        return True

    async def exists(self, workspace_id: str) -> bool:
        return bool(await self._es.exists(index=self._index, id=workspace_id))

    async def count(
        self,
        owner_id: str,
        status_filter: WorkspaceStatus | None = None,
        type_filter: str | None = None,
    ) -> int:
        """Return total workspace count for *owner_id*, respecting optional filters."""
        query = self._build_filter_query(owner_id, status_filter, type_filter)
        resp = await self._es.count(
            index=self._index,
            body={"query": query},
        )
        return int(resp.get("count", 0))


# ---------------------------------------------------------------------------
# ProviderRepository
# ---------------------------------------------------------------------------


class ProviderRepository:
    """
    Read (and seed) workspace provider definitions from Elasticsearch.

    On first startup, default providers from settings / config are seeded.
    """

    def __init__(self, es: AsyncElasticsearch) -> None:
        self._es = es
        self._index = get_settings().provider_index

    async def list_all(self) -> dict[str, dict[str, Any]]:
        resp = await self._es.search(
            index=self._index,
            body={"query": {"match_all": {}}, "size": 100},
        )
        result: dict[str, dict[str, Any]] = {}
        for hit in resp["hits"]["hits"]:
            src = hit["_source"]
            name: str = src.pop("name")
            result[name] = src
        return result

    async def get(self, name: str) -> dict[str, Any] | None:
        try:
            resp = await self._es.get(index=self._index, id=name.upper())
        except NotFoundError:
            return None
        src = dict(resp["_source"])
        src.pop("name", None)
        return src

    async def upsert(self, name: str, provider_doc: dict[str, Any]) -> None:
        doc = {"name": name.upper(), **provider_doc}
        await self._es.index(index=self._index, id=name.upper(), document=doc)


async def seed_default_providers(es: AsyncElasticsearch) -> None:
    """Seed built-in provider definitions if the index is empty."""
    repo = ProviderRepository(es)
    existing = await repo.list_all()
    if existing:
        return  # already seeded

    defaults = {
        "S3": {
            "title": "Amazon S3",
            "description": (
                "Amazon Simple Storage Service. Provides scalable object storage via S3-compatible buckets."
            ),
            "intents": ["create", "register"],
            "parameters": {
                "aws_access_key_id": {
                    "description": "AWS access key ID",
                    "type": "string",
                },
                "aws_secret_access_key": {
                    "description": "AWS secret access key",
                    "type": "string",
                },
                "bucket_name": {
                    "description": "S3 bucket name",
                    "type": "string",
                },
                "region": {
                    "description": "AWS region, e.g. eu-west-1",
                    "type": "string",
                },
            },
            "links": [],
        },
        "GCS": {
            "title": "Google Cloud Storage",
            "description": "Google Cloud Storage provides object storage via GCS buckets.",
            "intents": ["create", "register"],
            "parameters": {
                "project_id": {"description": "GCP project ID", "type": "string"},
                "bucket_name": {"description": "GCS bucket name", "type": "string"},
                "service_account_key": {
                    "description": "Service account JSON key (base64 encoded)",
                    "type": "string",
                },
            },
            "links": [],
        },
        "AZURE_BLOB": {
            "title": "Azure Blob Storage",
            "description": "Microsoft Azure Blob Storage containers.",
            "intents": ["register"],
            "parameters": {
                "account_name": {
                    "description": "Azure storage account name",
                    "type": "string",
                },
                "account_key": {
                    "description": "Azure storage account key",
                    "type": "string",
                },
                "container_name": {
                    "description": "Blob container name",
                    "type": "string",
                },
            },
            "links": [],
        },
    }

    for name, doc in defaults.items():
        await repo.upsert(name, doc)
    logger.info("seeded default workspace providers", count=len(defaults))
