"""
Pagination utilities.

openEO list endpoints use link-based pagination.  This module provides:

- ``PaginationParams``  – reusable FastAPI dependency for ``limit`` / ``offset``
- ``build_pagination_links`` – generates ``next`` / ``prev`` link objects per spec
- ``PagedResult``       – typed container returned by repository list methods

Design
------
We use simple offset-based pagination backed by Elasticsearch's ``from``/``size``
parameters.  For very large datasets a search-after / pit approach would be
more efficient, but offset pagination is simpler to expose via the openEO links
convention and adequate for typical workspace counts per user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Generic, TypeVar
from urllib.parse import urlencode

from fastapi import Query

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


@dataclass
class PaginationParams:
    """
    Reusable FastAPI dependency injected into list endpoints.

    Usage::

        @router.get("/items")
        async def list_items(page: PaginationParams = Depends()):
            items = await repo.list(limit=page.limit, offset=page.offset)
    """

    limit: int = field(default=10)
    offset: int = field(default=0)

    @classmethod
    def from_query(
        cls,
        limit: Annotated[int, Query(ge=1, le=500, description="Page size")] = 10,
        offset: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
    ) -> PaginationParams:
        return cls(limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Link builder
# ---------------------------------------------------------------------------


def build_pagination_links(
    base_url: str,
    limit: int,
    offset: int,
    returned: int,
    extra_params: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """
    Build openEO-style pagination ``links`` list.

    Returns a ``next`` link when ``returned == limit`` (there *may* be more
    results), and a ``prev`` link when ``offset > 0``.

    Args:
        base_url:     Absolute URL of the list endpoint (no query string).
        limit:        Page size used for this request.
        offset:       Offset used for this request.
        returned:     Actual number of items returned in this page.
        extra_params: Any additional query parameters to preserve.
    """
    links: list[dict[str, str]] = []
    params = dict(extra_params or {})

    if returned == limit:
        next_params = {**params, "limit": limit, "offset": offset + limit}
        links.append(
            {
                "rel": "next",
                "href": f"{base_url}?{urlencode(next_params)}",
                "type": "application/json",
                "title": "Next page",
            }
        )

    if offset > 0:
        prev_offset = max(0, offset - limit)
        prev_params = {**params, "limit": limit, "offset": prev_offset}
        links.append(
            {
                "rel": "prev",
                "href": f"{base_url}?{urlencode(prev_params)}",
                "type": "application/json",
                "title": "Previous page",
            }
        )

    return links


# ---------------------------------------------------------------------------
# Typed page result
# ---------------------------------------------------------------------------


@dataclass
class PagedResult(Generic[T]):
    """Container for a page of results plus the raw pagination metadata."""

    items: list[T]
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return len(self.items) == self.limit
