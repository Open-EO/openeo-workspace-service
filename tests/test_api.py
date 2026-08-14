"""
Tests for OpenEO Workspaces API
"""
import dirty_equals
import mock
import pytest
from fastapi.testclient import TestClient
from mock.mock import AsyncMock

from main import app, route_prefix
from workspace_service.auth import TokenData


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
    assert "s3" in data["providers"]

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


def test_list_workspaces(client):
    with mock.patch("workspace_service.auth.oidc_auth_manager.verify_token",
                    return_value=TokenData(sub="", iat=0, exp=0, iss="")):
        response = client.get(f"{route_prefix}/workspaces", headers={"Authorization": f"Bearer ..."})

    assert response.status_code == 200

    data = response.json()

    assert "workspaces" in data
    assert data["workspaces"] == []


def test_create_workspace(client):
    token_data = TokenData(sub="johndoe", iat=0, exp=0, iss="")

    with (
        mock.patch("workspace_service.auth.oidc_auth_manager.verify_token", return_value=token_data),
        mock.patch("workspace_service.db.get_client", return_value=AsyncMock()) as get_db_client_mock
    ):
        db_client_mock = get_db_client_mock.return_value

        response = client.post(f"{route_prefix}/workspaces",
                               json={"title": "t", "description": "d", "parameters": {"bucket_name": "b"}, "quota": 42},
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
            }
        )

    assert response.status_code == 201, response.json()

    assert response.json() == {
        "id": dirty_equals.IsUUID(),
        "status": "provisioning",
        "message": "Workspace creation has been queued successfully"
    }
