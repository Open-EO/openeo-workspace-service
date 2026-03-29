"""Unit tests for the workspace ID slug generator."""
from __future__ import annotations

import re

from openeo_workspace_service.models.id_generator import _slugify, make_workspace_id

# Pattern the openEO spec requires workspace IDs to satisfy
VALID_ID_RE = re.compile(r"^[\w\-\.~]+$")


class TestSlugify:
    def test_simple_lowercase(self):
        assert _slugify("hello world") == "hello-world"

    def test_strips_special_chars(self):
        slug = _slugify("S3 Bucket / prod!")
        assert "/" not in slug
        assert "!" not in slug
        assert VALID_ID_RE.match(slug)

    def test_collapses_consecutive_hyphens(self):
        assert "--" not in _slugify("foo  --  bar")

    def test_strips_leading_trailing_hyphens(self):
        slug = _slugify("  -- hello -- ")
        assert not slug.startswith("-")
        assert not slug.endswith("-")

    def test_accented_chars_transliterated(self):
        slug = _slugify("Ångström Analysis")
        assert "Å" not in slug
        assert VALID_ID_RE.match(slug)

    def test_max_length_48(self):
        long_title = "a" * 200
        assert len(_slugify(long_title)) <= 48

    def test_empty_string_returns_empty(self):
        assert _slugify("") == ""

    def test_only_special_chars_returns_empty_or_valid(self):
        result = _slugify("!!! ###")
        # Either empty (all chars stripped) or valid
        assert result == "" or VALID_ID_RE.match(result)


class TestMakeWorkspaceId:
    def test_returns_string_matching_spec(self):
        ws_id = make_workspace_id("My Workspace")
        assert VALID_ID_RE.match(ws_id), f"Invalid ID: {ws_id!r}"

    def test_contains_title_slug(self):
        ws_id = make_workspace_id("Analysis Bucket")
        assert "analysis" in ws_id
        assert "bucket" in ws_id

    def test_none_title_returns_workspace_prefix(self):
        ws_id = make_workspace_id(None)
        assert ws_id.startswith("workspace-")
        assert VALID_ID_RE.match(ws_id)

    def test_empty_title_falls_back_to_generic(self):
        ws_id = make_workspace_id("")
        assert ws_id.startswith("workspace-")

    def test_only_special_chars_falls_back_to_generic(self):
        ws_id = make_workspace_id("!!!###")
        assert ws_id.startswith("workspace-")

    def test_ids_are_unique(self):
        ids = {make_workspace_id("My Workspace") for _ in range(50)}
        # With a 6-hex-char suffix there should be no collisions in 50 samples
        assert len(ids) == 50

    def test_total_length_within_spec(self):
        # openEO spec does not cap workspace_id length explicitly,
        # but we keep it reasonable (max ~56 chars)
        for title in ["a" * 100, "My Workspace", None, "!!!", ""]:
            ws_id = make_workspace_id(title)
            assert len(ws_id) <= 60, f"ID too long: {ws_id!r}"
            assert VALID_ID_RE.match(ws_id), f"Invalid ID: {ws_id!r}"
