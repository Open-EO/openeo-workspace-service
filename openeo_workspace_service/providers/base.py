"""
openeo_workspace_service/providers/base.py
--------------------------------------------
Abstract workspace provider interface + registry.

Each concrete provider (S3, Azure, GCS, …) registers itself via
``@register_provider("MyName")``.  The router looks up providers through
``get_provider(name)`` and ``all_providers()``.
"""
from __future__ import annotations

import abc
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openeo_workspace_service.db.models import WorkspaceRecord
    from openeo_workspace_service.models.schemas import WorkspaceProvider

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, type["BaseWorkspaceProvider"]] = {}


def register_provider(name: str):
    """Class decorator that registers a provider under *name* (case-insensitive)."""

    def _decorator(cls: type[BaseWorkspaceProvider]):
        _REGISTRY[name.upper()] = cls
        logger.debug("Registered workspace provider %r", name)
        return cls

    return _decorator


def get_provider(name: str) -> "BaseWorkspaceProvider":
    cls = _REGISTRY.get(name.upper())
    if cls is None:
        raise KeyError(f"Unknown workspace provider: {name!r}")
    return cls()


def all_providers() -> dict[str, "BaseWorkspaceProvider"]:
    return {name: cls() for name, cls in _REGISTRY.items()}


class BaseWorkspaceProvider(abc.ABC):
    """All workspace providers must implement this interface."""

    # ── Metadata ─────────────────────────────────────────────────────────────

    @property
    @abc.abstractmethod
    def metadata(self) -> "WorkspaceProvider":
        """Return the provider metadata (title, description, parameters, intents)."""

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def provision(self, record: "WorkspaceRecord") -> None:
        """
        Called after the workspace DB record is created with status=provisioning.
        Implementations should:
        - Actually create/verify the remote storage resource.
        - Update ``record.status`` to ``ready`` (or ``unavailable`` on error).
        - Populate ``record.url``, ``record.properties``, ``record.free``.
        Changes are **not** committed here; the caller commits.
        """

    @abc.abstractmethod
    async def delete(self, record: "WorkspaceRecord") -> None:
        """
        Remove the workspace from the back-end.
        Raise an exception if deletion fails; the DB record is only removed
        on success.
        """

    # ── Optional ─────────────────────────────────────────────────────────────

    async def refresh_status(self, record: "WorkspaceRecord") -> None:
        """
        Optional: update ``record.status`` / ``record.free`` to reflect the
        current real-world state.  Called before returning workspace details.
        """

    def validate_parameters(self, parameters: dict[str, Any]) -> None:
        """
        Validate provider-specific parameters.  Raise ``ValueError`` with a
        human-readable message on failure.
        """
