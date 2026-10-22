"""
Tests for OpenEO Workspaces API
"""
import json
import dirty_equals
import mock
import pytest
from fastapi.testclient import TestClient
from mock.mock import AsyncMock

from main import app, route_prefix
from workspace_service.auth import TokenData
from workspace_service.routes.providers import load_workspace_providers
from workspace_service.routes import providers
from pydantic import ValidationError


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)

def test_health_check(client):
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_api_root(client):
    """Test API root endpoint"""
    response = client.get(route_prefix)
    assert response.status_code == 200
    data = response.json()
    assert "api_version" in data
    assert "title" in data

def test_workspace_providers_no_auth(client):
    """Test workspace providers endpoint without authentication"""
    response = client.get(f"{route_prefix}/workspace_providers")
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "cloudferro" in data["providers"]

def test_workspace_providers_structure(client):
    """Test workspace providers structure"""
    response = client.get(f"{route_prefix}/workspace_providers")
    assert response.status_code == 200
    data = response.json()

    for provider_name, provider_config in data["providers"].items():
        assert "title" in provider_config
        assert "description" in provider_config
        assert "intents" in provider_config
        assert "parameters" in provider_config
        assert len(provider_config["intents"]) > 0
        assert set(provider_config["intents"]).issubset({"create", "register"})


def test_workspace_providers_from_json(client, tmp_path, monkeypatch):
    path = tmp_path / "providers.json"
    path.write_text(json.dumps({
        "custom": {
            "title": "Custom storage",
            "intents": ["create"],
            "parameters": {},
        },
    }))
    monkeypatch.setattr(providers, "WORKSPACE_PROVIDERS", load_workspace_providers(path))
    response = client.get(f"{route_prefix}/workspace_providers")
    assert response.status_code == 200
    assert set(response.json()["providers"]) == {"custom"}
    assert response.json()["providers"]["custom"]["title"] == "Custom storage"


@pytest.mark.parametrize("content", ["not json", "[]", '{"s3": "invalid"}'])
def test_workspace_providers_rejects_invalid_json(tmp_path, content):
    path = tmp_path / "providers.json"
    path.write_text(content)
    with pytest.raises(ValidationError):
        load_workspace_providers(path)


def test_workspace_providers_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_workspace_providers(tmp_path / "missing.json")


def test_list_workspaces(client):
    with mock.patch("workspace_service.auth.oidc_auth_manager.verify_token",
                    return_value=TokenData(sub="", iat=0, exp=0, iss="")):
        response = client.get(f"{route_prefix}/workspaces", headers={"Authorization": f"Bearer ..."})

    assert response.status_code == 200

    data = response.json()

    assert "workspaces" in data
    assert data["workspaces"] == []


def test_register_workspace(client):
    token_data = TokenData(sub="johndoe", iat=0, exp=0, iss="")

    with (
        mock.patch("workspace_service.auth.oidc_auth_manager.verify_token", return_value=token_data),
        mock.patch("workspace_service.db.get_client", return_value=AsyncMock()) as get_db_client_mock
    ):
        db_client_mock = get_db_client_mock.return_value

        response = client.post(f"{route_prefix}/workspaces",
                               json={"intent": "register", "type": "s3", "url": "s3://existing",
                                     "title": "t", "description": "d", "parameters": {"bucket_name": "b"}, "quota": 42},
                               headers={"Authorization": f"Bearer ..."})

        db_client_mock.create_workspace.assert_called_once_with(
            dirty_equals.IsUUID(),
            "johndoe",
            {
                "title": "t",
                "description": "d",
                "type": "s3",
                "parameters": {"bucket_name": "b"},
                "quota": 42,
                "url": "s3://existing",
            }
        )

    assert response.status_code == 201, response.json()

    assert response.json() == {
        "id": dirty_equals.IsUUID(),
        "status": "provisioning",
        "message": "Workspace creation has been queued successfully"
    }


def test_create_workspace(client):
    token = TokenData(sub="johndoe", iat=0, exp=0, iss="")
    metadata = {
        "url": "https://s3.waw3-1.cloudferro.com/workspace-test",
        "properties": {"bucket_name": "workspace-test", "region": "waw3-1"},
    }
    store = AsyncMock()

    async def update(workspace_id, user_id, data):
        return {"id": workspace_id, "type": "cloudferro", **data}

    store.update_workspace.side_effect = update
    with (
        mock.patch("workspace_service.auth.oidc_auth_manager.verify_token", return_value=token),
        mock.patch("workspace_service.db.get_client", return_value=store),
        mock.patch(
            "workspace_service.provider_clients.cloudferro.CloudFerroBucketProvisioner.provision_workspace",
            return_value=metadata,
        ) as provision,
    ):
        response = client.post(
            f"{route_prefix}/workspaces",
            headers={"Authorization": "Bearer token"},
            json={"type": "CLOUDFERRO", "parameters": {
                "aws_access_key_id": "test-access",
                "aws_secret_access_key": "test-secret",
                "bucket_name": "workspace-test",
            }},
        )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "ready"
    assert data["url"] == metadata["url"]
    assert data["properties"] == metadata["properties"]
    assert response.headers["Location"].endswith("/workspaces/" + data["id"])
    provision.assert_called_once()
    assert provision.call_args.args[1].bucket_name == "workspace-test"
    saved = store.create_workspace.call_args.args[2]
    assert saved["parameters"] == {
        "bucket_name": "workspace-test",
        "region": "waw3-1",
        "endpoint_url": "https://s3.waw3-1.cloudferro.com",
    }
    assert saved["type"] == "cloudferro"
    assert "test-secret" not in response.text


@pytest.mark.parametrize("body,code", [
    ({"type": "unknown"}, 400),
    ({"type": "../cloudferro"}, 400),
    ({"type": "cloudferro"}, 422),
    ({"type": "cloudferro", "parameters": {
        "aws_access_key_id": "test-access", "aws_secret_access_key": "test-secret",
        "bucket_name": "INVALID",
    }}, 422),
    ({"intent": "register", "type": "cloudferro", "parameters": {}}, 422),
    ({"intent": "invalid", "type": "cloudferro"}, 422),
])
def test_invalid_workspace_create(client, body, code):
    with (
        mock.patch("workspace_service.auth.oidc_auth_manager.verify_token",
                   return_value=TokenData(sub="user", iat=0, exp=0, iss="")),
        mock.patch("workspace_service.db.get_client") as store,
    ):
        response = client.post(f"{route_prefix}/workspaces", json=body,
                               headers={"Authorization": "Bearer token"})
    assert response.status_code == code, response.text
    store.assert_not_called()


def test_provision_failure(client):
    store = AsyncMock()
    with (
        mock.patch("workspace_service.auth.oidc_auth_manager.verify_token",
                   return_value=TokenData(sub="user", iat=0, exp=0, iss="")),
        mock.patch("workspace_service.db.get_client", return_value=store),
        mock.patch(
            "workspace_service.provider_clients.cloudferro.CloudFerroBucketProvisioner.provision_workspace",
            side_effect=RuntimeError("do not expose test-secret"),
        ),
    ):
        response = client.post(
            f"{route_prefix}/workspaces",
            json={"type": "cloudferro", "parameters": {
                "aws_access_key_id": "test-access", "aws_secret_access_key": "test-secret",
            }},
            headers={"Authorization": "Bearer token"},
        )
    assert response.status_code == 502
    assert "test-secret" not in response.text
    assert store.update_workspace.call_args.args[2]["status"] == "unavailable"


def test_create_and_describe_persisted_workspace(client, tmp_path):
    from workspace_service.db import GitWorkspaceClient
    from git import Repo
    from git import Actor

    store = GitWorkspaceClient()
    store.repo_path = tmp_path
    store._repo = Repo.init(tmp_path)
    store.author = Actor("Test", "test@example.test")
    store.remote_url = None
    metadata = {
        "url": "https://s3.waw3-1.cloudferro.com/workspace-test",
        "properties": {
            "bucket_name": "workspace-test", "region": "waw3-1",
            "endpoint_url": "https://s3.waw3-1.cloudferro.com",
            "s3_url": "s3://workspace-test",
        },
    }
    headers = {"Authorization": "Bearer token"}
    with (
        mock.patch("workspace_service.auth.oidc_auth_manager.verify_token",
                   return_value=TokenData(sub="user", iat=0, exp=0, iss="")),
        mock.patch("workspace_service.db.get_client", return_value=store),
        mock.patch(
            "workspace_service.provider_clients.cloudferro.CloudFerroBucketProvisioner.provision_workspace",
            return_value=metadata,
        ),
    ):
        created = client.post(
            f"{route_prefix}/workspaces", headers=headers,
            json={"type": "cloudferro", "parameters": {
                "aws_access_key_id": "test-access", "aws_secret_access_key": "test-secret",
                "bucket_name": "workspace-test",
            }},
        )
        assert created.status_code == 201, created.text
        described = client.get(created.headers["Location"], headers=headers)
        assert described.status_code == 200
        assert described.json() == created.json()
        listed = client.get(f"{route_prefix}/workspaces", headers=headers)
        assert listed.json()["workspaces"][0]["url"] == metadata["url"]
    for commit in store._repo.iter_commits():
        content = (commit.tree / f"workspaces/user/{created.json()['id']}.json").data_stream.read()
        assert b"test-secret" not in content
        assert b"test-access" not in content
