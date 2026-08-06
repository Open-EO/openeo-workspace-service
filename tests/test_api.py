"""
Tests for OpenEO Workspaces API
"""
import pytest
from fastapi.testclient import TestClient
from main import app, route_prefix

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

# Note: Protected endpoints require bearer token testing
# This would require mocking KeyCloak authentication

