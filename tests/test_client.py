import httpx
import pytest

from workspace_service_client import WorkspaceServiceClient


def test_list_workspace_providers():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/workspaces/api/v1/workspace_providers"
        return httpx.Response(
            200,
            json={
                "providers": {
                    "s3": {
                        "title": "S3",
                        "description": "Provider",
                        "intents": ["create", "register"],
                        "parameters": {},
                        "links": [],
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="https://example.test", transport=transport) as raw_client:
        client = WorkspaceServiceClient(base_url="https://example.test", client=raw_client)
        providers = client.list_workspace_providers()

    assert "s3" in providers.providers


def test_authenticated_endpoints_require_token():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    with httpx.Client(base_url="https://example.test", transport=transport) as raw_client:
        client = WorkspaceServiceClient(base_url="https://example.test", client=raw_client)
        with pytest.raises(ValueError, match="requires a bearer token"):
            client.list_workspaces()


def test_list_workspaces_sends_auth_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/workspaces/api/v1/workspaces"
        assert request.url.params["limit"] == "5"
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            json={"workspaces": [], "links": {"rel": [], "href": []}},
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(base_url="https://example.test", transport=transport) as raw_client:
        client = WorkspaceServiceClient(
            base_url="https://example.test",
            token="test-token",
            client=raw_client,
        )
        result = client.list_workspaces(limit=5)

    assert result.workspaces == []
