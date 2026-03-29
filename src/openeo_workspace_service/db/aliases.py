"""
Elasticsearch index alias management.

openEO workspace service uses index aliases so the application always reads
and writes through a stable name (e.g. ``openeo_workspaces``) while the
physical index can be versioned and swapped transparently.

Layout
------
Write alias  →  physical index (e.g. openeo_workspaces_v1)
Read alias   →  same physical index (can fan-out to multiple during migration)

The alias names used by the application are the ``workspace_index`` and
``provider_index`` settings values – the physical versioned indices are
those names suffixed with the version number (already the case: ``_v1``).

This module provides helpers for:
  - Creating aliases pointing to the current physical index.
  - Performing a safe alias swap during zero-downtime migration.
  - Listing all physical indices managed by this service.
"""
from __future__ import annotations

from typing import Any

import structlog
from elasticsearch import AsyncElasticsearch

from openeo_workspace_service.config.settings import get_settings

logger = structlog.get_logger(__name__)


async def ensure_aliases(es: AsyncElasticsearch) -> None:
    """
    Ensure read/write aliases exist for each managed index.

    Each physical index (``openeo_workspaces_v1``) gets a matching alias
    without the version suffix (``openeo_workspaces``).  If the alias
    already exists it is left unchanged.
    """
    settings = get_settings()
    pairs = [
        # (physical_index, alias_name)
        (settings.workspace_index, _alias_name(settings.workspace_index)),
        (settings.provider_index, _alias_name(settings.provider_index)),
    ]

    for physical, alias in pairs:
        exists = await es.indices.exists_alias(name=alias)
        if exists:
            logger.debug("alias already exists", alias=alias)
            continue

        # Check the physical index exists before aliasing
        idx_exists = await es.indices.exists(index=physical)
        if not idx_exists:
            logger.warning(
                "physical index missing – cannot create alias",
                index=physical,
                alias=alias,
            )
            continue

        await es.indices.put_alias(index=physical, name=alias)
        logger.info("created alias", alias=alias, index=physical)


async def swap_alias(
    es: AsyncElasticsearch,
    alias: str,
    old_index: str,
    new_index: str,
) -> None:
    """
    Atomically swap *alias* from *old_index* to *new_index*.

    Uses the ES ``/_aliases`` actions API so the swap is atomic from the
    perspective of any concurrently running queries.

    Args:
        alias:      The alias name (e.g. ``openeo_workspaces``).
        old_index:  The physical index currently pointed to by the alias.
        new_index:  The new physical index to point the alias at.
    """
    actions: list[dict[str, Any]] = [
        {"remove": {"index": old_index, "alias": alias}},
        {"add": {"index": new_index, "alias": alias}},
    ]
    await es.indices.update_aliases(body={"actions": actions})
    logger.info(
        "alias swapped",
        alias=alias,
        old_index=old_index,
        new_index=new_index,
    )


async def list_managed_indices(es: AsyncElasticsearch) -> dict[str, Any]:
    """
    Return a dict of all physical indices whose names start with the
    configured index prefix, along with their alias mappings.

    Useful for operational tooling and the ``migrations status`` command.
    """
    prefix = get_settings().elasticsearch_index_prefix
    resp = await es.indices.get(index=f"{prefix}*", ignore_unavailable=True)
    return dict(resp)


def _alias_name(physical_index: str) -> str:
    """
    Derive the alias name from a physical index name by stripping the
    trailing ``_v<N>`` version suffix.

    Examples::

        _alias_name("openeo_workspaces_v1")      → "openeo_workspaces"
        _alias_name("openeo_workspaces_providers_v1") → "openeo_workspaces_providers"
    """
    import re
    return re.sub(r"_v\d+$", "", physical_index)
