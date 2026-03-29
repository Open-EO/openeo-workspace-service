"""Unit tests for the pagination utility module."""
from __future__ import annotations

from openeo_workspace_service.api.pagination import (
    PagedResult,
    PaginationParams,
    build_pagination_links,
)


class TestBuildPaginationLinks:
    def test_no_links_when_only_page(self):
        links = build_pagination_links(
            "http://test/workspaces", limit=10, offset=0, returned=5
        )
        assert links == []

    def test_next_link_when_full_page(self):
        links = build_pagination_links(
            "http://test/workspaces", limit=10, offset=0, returned=10
        )
        rels = [lnk["rel"] for lnk in links]
        assert "next" in rels
        assert "prev" not in rels
        next_link = next(lnk for lnk in links if lnk["rel"] == "next")
        assert "offset=10" in next_link["href"]
        assert "limit=10" in next_link["href"]

    def test_prev_link_when_offset_positive(self):
        links = build_pagination_links(
            "http://test/workspaces", limit=10, offset=10, returned=3
        )
        rels = [lnk["rel"] for lnk in links]
        assert "prev" in rels
        assert "next" not in rels
        prev_link = next(lnk for lnk in links if lnk["rel"] == "prev")
        assert "offset=0" in prev_link["href"]

    def test_both_links_on_middle_page(self):
        links = build_pagination_links(
            "http://test/workspaces", limit=10, offset=10, returned=10
        )
        rels = [lnk["rel"] for lnk in links]
        assert "next" in rels
        assert "prev" in rels

    def test_prev_offset_clamps_to_zero(self):
        links = build_pagination_links(
            "http://test/workspaces", limit=10, offset=5, returned=5
        )
        prev_link = next(lnk for lnk in links if lnk["rel"] == "prev")
        assert "offset=0" in prev_link["href"]

    def test_extra_params_preserved(self):
        links = build_pagination_links(
            "http://test/workspaces",
            limit=5,
            offset=0,
            returned=5,
            extra_params={"type": "S3"},
        )
        next_link = next(lnk for lnk in links if lnk["rel"] == "next")
        assert "type=S3" in next_link["href"]


class TestPagedResult:
    def test_has_more_true_when_full_page(self):
        result = PagedResult(items=list(range(10)), limit=10, offset=0)
        assert result.has_more is True

    def test_has_more_false_when_partial_page(self):
        result = PagedResult(items=list(range(7)), limit=10, offset=0)
        assert result.has_more is False

    def test_has_more_false_when_empty(self):
        result = PagedResult(items=[], limit=10, offset=0)
        assert result.has_more is False


class TestPaginationParams:
    def test_from_query_defaults(self):
        params = PaginationParams.from_query()
        assert params.limit == 10
        assert params.offset == 0

    def test_from_query_custom(self):
        params = PaginationParams.from_query(limit=25, offset=50)
        assert params.limit == 25
        assert params.offset == 50
