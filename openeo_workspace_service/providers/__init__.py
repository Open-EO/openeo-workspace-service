"""
openeo_workspace_service/providers/__init__.py
Import all built-in providers so their ``@register_provider`` decorators run.
"""
from openeo_workspace_service.providers import azure, gcs, s3  # noqa: F401
from openeo_workspace_service.providers.base import (  # noqa: F401
    all_providers,
    get_provider,
    register_provider,
)
