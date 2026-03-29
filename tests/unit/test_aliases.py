"""Unit tests for the Elasticsearch alias management module."""
from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest

from openeo_workspace_service.db.aliases import (
    _alias_name,
    ensure_aliases,
    swap_alias,
)


class TestAliasName:
    def test_strips_v1_suffix(self):
        assert _alias_name("openeo_workspaces_v1") == "openeo_workspaces"

    def test_strips_v2_suffix(self):
        assert _alias_name("openeo_workspaces_v2") == "openeo_workspaces"

    def test_strips_providers_v1(self):
        assert _alias_name("openeo_workspaces_providers_v1") == "openeo_workspaces_providers"

    def test_no_version_suffix_unchanged(self):
        assert _alias_name("openeo_workspaces") == "openeo_workspaces"

    def test_high_version_number(self):
        assert _alias_name("openeo_workspaces_v123") == "openeo_workspaces"


class TestEnsureAliases:
    @pytest.mark.asyncio
    async def test_creates_alias_when_missing(self):
        es = AsyncMock()
        es.indices = AsyncMock()
        es.indices.exists_alias = AsyncMock(return_value=False)
        es.indices.exists = AsyncMock(return_value=True)
        es.indices.put_alias = AsyncMock()

        await ensure_aliases(es)

        assert es.indices.put_alias.await_count == 2  # workspace + provider

    @pytest.mark.asyncio
    async def test_skips_existing_alias(self):
        es = AsyncMock()
        es.indices = AsyncMock()
        es.indices.exists_alias = AsyncMock(return_value=True)
        es.indices.put_alias = AsyncMock()

        await ensure_aliases(es)

        es.indices.put_alias.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_physical_index_missing(self):
        es = AsyncMock()
        es.indices = AsyncMock()
        es.indices.exists_alias = AsyncMock(return_value=False)
        es.indices.exists = AsyncMock(return_value=False)
        es.indices.put_alias = AsyncMock()

        await ensure_aliases(es)

        es.indices.put_alias.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_only_missing_alias(self):
        """First alias exists, second doesn't – only second should be created."""
        es = AsyncMock()
        es.indices = AsyncMock()
        # First call (workspace alias): exists. Second call (provider alias): missing.
        es.indices.exists_alias = AsyncMock(side_effect=[True, False])
        es.indices.exists = AsyncMock(return_value=True)
        es.indices.put_alias = AsyncMock()

        await ensure_aliases(es)

        assert es.indices.put_alias.await_count == 1


class TestSwapAlias:
    @pytest.mark.asyncio
    async def test_swap_calls_update_aliases_with_correct_actions(self):
        es = AsyncMock()
        es.indices = AsyncMock()
        es.indices.update_aliases = AsyncMock()

        await swap_alias(
            es,
            alias="openeo_workspaces",
            old_index="openeo_workspaces_v1",
            new_index="openeo_workspaces_v2",
        )

        es.indices.update_aliases.assert_awaited_once()
        body = es.indices.update_aliases.call_args.kwargs["body"]
        actions = body["actions"]
        assert {"remove": {"index": "openeo_workspaces_v1", "alias": "openeo_workspaces"}} in actions
        assert {"add": {"index": "openeo_workspaces_v2", "alias": "openeo_workspaces"}} in actions

    @pytest.mark.asyncio
    async def test_swap_is_atomic_single_call(self):
        """Both remove and add must be in a single API call."""
        es = AsyncMock()
        es.indices = AsyncMock()
        es.indices.update_aliases = AsyncMock()

        await swap_alias(es, "my_alias", "idx_v1", "idx_v2")

        assert es.indices.update_aliases.await_count == 1
