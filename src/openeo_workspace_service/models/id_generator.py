"""
Workspace ID generation utilities.

The openEO spec allows workspace IDs matching the pattern ``^[\\w\\-\\.~]+$``.  Rather
than exposing raw UUIDs to users, we derive a readable slug from the
workspace title (when provided) and append a short random suffix to ensure
uniqueness.

Examples
--------
>>> make_workspace_id("My Analysis Workspace")
'my-analysis-workspace-a3f2'
>>> make_workspace_id(None)
'workspace-9b1c4e2d'
>>> make_workspace_id("S3 Bucket / prod!")
's3-bucket-prod-7d3a'
"""

from __future__ import annotations

import re
import secrets
import unicodedata


def _slugify(text: str) -> str:
    """
    Convert *text* to a URL-safe slug matching the openEO workspace ID pattern.

    Steps:
    1. NFKD normalise (decompose accented chars).
    2. Drop non-ASCII bytes.
    3. Lower-case.
    4. Replace whitespace and unsafe chars with hyphens.
    5. Collapse consecutive hyphens.
    6. Strip leading/trailing hyphens.
    7. Truncate to 48 chars.
    """
    # NFKD normalise + drop non-ASCII
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    # Replace anything not alphanumeric/hyphen/dot/tilde with hyphen
    text = re.sub(r"[^\w\-\.~]+", "-", text)
    # Collapse consecutive hyphens/underscores
    text = re.sub(r"[-_]{2,}", "-", text)
    text = text.strip("-_")
    return text[:48]


def _short_token(n_bytes: int = 3) -> str:
    """Return a URL-safe lowercase hex token of *n_bytes* bytes (6 hex chars)."""
    return secrets.token_hex(n_bytes)


def make_workspace_id(title: str | None) -> str:
    """
    Generate a workspace ID from an optional *title*.

    The returned string always satisfies ``^[\\w\\-\\.~]+$`` and is at most
    56 characters long (48 slug + hyphen + 6 hex chars).

    Args:
        title: Human-readable workspace title.  May be None.

    Returns:
        A lowercase slug with a random hex suffix, e.g. ``my-workspace-a1b2c3``.
    """
    if title:
        slug = _slugify(title)
        if slug:
            return f"{slug}-{_short_token()}"
    # Fallback: generic prefix + longer token
    return f"workspace-{_short_token(4)}"
