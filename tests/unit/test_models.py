"""Unit tests for Pydantic workspace models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from openeo_workspace_service.models.workspace import (
    CreateWorkspaceRequest,
    RegisterWorkspaceRequest,
    UpdateWorkspaceRequest,
    WorkspaceIntent,
    WorkspaceReady,
    WorkspaceStatus,
    WorkspaceUnavailable,
)


class TestWorkspaceId:
    def test_valid_ids(self):
        for ws_id in ("my-workspace", "ws_001", "WS.alpha~1"):
            ws = WorkspaceReady(id=ws_id, type="S3", status=WorkspaceStatus.ready)
            assert ws.id == ws_id

    def test_invalid_id_with_slash(self):
        with pytest.raises(ValidationError):
            WorkspaceReady(id="bad/id", type="S3", status=WorkspaceStatus.ready)

    def test_invalid_id_with_space(self):
        with pytest.raises(ValidationError):
            WorkspaceReady(id="bad id", type="S3", status=WorkspaceStatus.ready)


class TestWorkspaceReady:
    def test_minimal(self):
        ws = WorkspaceReady(id="ws-1", type="S3", status=WorkspaceStatus.ready)
        assert ws.status == WorkspaceStatus.ready
        assert ws.url is None
        assert ws.properties is None

    def test_full(self):
        ws = WorkspaceReady(
            id="ws-1",
            title="My Workspace",
            description="A test workspace",
            type="S3",
            status=WorkspaceStatus.ready,
            url="https://bucket.s3.example.com",
            quota=10_000_000,
            free=5_000_000,
            properties={"region": "eu-west-1"},
        )
        assert ws.title == "My Workspace"
        assert ws.free == 5_000_000
        assert ws.properties == {"region": "eu-west-1"}


class TestWorkspaceUnavailable:
    def test_provisioning(self):
        ws = WorkspaceUnavailable(
            id="ws-2", type="GCS", status=WorkspaceStatus.provisioning
        )
        assert ws.status == WorkspaceStatus.provisioning

    def test_unavailable(self):
        ws = WorkspaceUnavailable(
            id="ws-2", type="GCS", status=WorkspaceStatus.unavailable, details="Lost connection"
        )
        assert ws.details == "Lost connection"


class TestCreateWorkspaceRequest:
    def test_defaults(self):
        req = CreateWorkspaceRequest()
        assert req.intent == WorkspaceIntent.create
        assert req.type is None

    def test_wrong_intent_raises(self):
        with pytest.raises(ValidationError):
            CreateWorkspaceRequest(intent=WorkspaceIntent.register)

    def test_with_type(self):
        req = CreateWorkspaceRequest(type="S3", parameters={"bucket_name": "my-bucket"})
        assert req.type == "S3"
        assert req.parameters == {"bucket_name": "my-bucket"}


class TestRegisterWorkspaceRequest:
    def test_valid(self):
        req = RegisterWorkspaceRequest(
            type="S3",
            url="https://bucket.s3.example.com",
            parameters={"aws_access_key_id": "KEY", "aws_secret_access_key": "SECRET"},
        )
        assert req.intent == WorkspaceIntent.register
        assert req.url == "https://bucket.s3.example.com"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            RegisterWorkspaceRequest(type="S3")  # url and parameters missing

    def test_wrong_intent_raises(self):
        with pytest.raises(ValidationError):
            RegisterWorkspaceRequest(
                intent=WorkspaceIntent.create,
                type="S3",
                url="https://bucket.example.com",
                parameters={},
            )


class TestUpdateWorkspaceRequest:
    def test_all_optional(self):
        req = UpdateWorkspaceRequest()
        assert req.title is None
        assert req.description is None

    def test_partial(self):
        req = UpdateWorkspaceRequest(title="New Title")
        assert req.title == "New Title"
        assert req.description is None
