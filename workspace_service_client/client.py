"""Client for interacting with the OpenEO Workspace Service API."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from workspace_service_client.models import (
    Workspace,
    WorkspaceProvidersResponse,
    WorkspacesListResponse,
)


class WorkspaceServiceClientError(Exception):
    """Raised when the Workspace Service returns an error response."""

    def __init__(self, status_code: int, message: str, response: httpx.Response):
        super().__init__(f"{status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.response = response


class WorkspaceServiceClient:
    """Synchronous API client for the OpenEO Workspace Service."""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        api_prefix: str = "/workspaces/api/v1",
        timeout: float = 30.0,
        client: Optional[httpx.Client] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix.rstrip("/")
        self.token = token
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def __enter__(self) -> "WorkspaceServiceClient":
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        if self._owns_client:
            self._client.close()

    def set_token(self, token: Optional[str]):
        """Set or clear the bearer token used for authenticated requests."""
        self.token = token

    def health(self) -> Dict[str, Any]:
        response = self._request("GET", "/health", use_api_prefix=False)
        return response.json()

    def api_info(self) -> Dict[str, Any]:
        response = self._request("GET", "", use_api_prefix=True)
        return response.json()

    def list_workspace_providers(self) -> WorkspaceProvidersResponse:
        response = self._request("GET", "/workspace_providers")
        return WorkspaceProvidersResponse.model_validate(response.json())

    def list_workspaces(self, limit: int = 100) -> WorkspacesListResponse:
        response = self._request(
            "GET",
            "/workspaces",
            auth_required=True,
            params={"limit": limit},
        )
        return WorkspacesListResponse.model_validate(response.json())

    def create_workspace(
        self,
        intent: str = "create",
        title: Optional[str] = None,
        description: Optional[str] = None,
        workspace_type: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        quota: Optional[int] = None,
        url: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"intent": intent}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if workspace_type is not None:
            payload["type"] = workspace_type
        if parameters is not None:
            payload["parameters"] = parameters
        if quota is not None:
            payload["quota"] = quota
        if url is not None:
            payload["url"] = url

        response = self._request(
            "POST",
            "/workspaces",
            auth_required=True,
            json=payload,
        )
        return response.json()

    def describe_workspace(self, workspace_id: str) -> Workspace:
        response = self._request("GET", f"/workspaces/{workspace_id}", auth_required=True)
        return Workspace.model_validate(response.json())

    def update_workspace(
        self,
        workspace_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if not payload:
            raise ValueError("At least one of 'title' or 'description' must be provided.")

        self._request(
            "PATCH",
            f"/workspaces/{workspace_id}",
            auth_required=True,
            json=payload,
        )

    def delete_workspace(self, workspace_id: str) -> None:
        self._request("DELETE", f"/workspaces/{workspace_id}", auth_required=True)

    def _build_path(self, path: str, use_api_prefix: bool) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        if not use_api_prefix:
            return normalized_path
        return f"{self.api_prefix}{normalized_path}" if normalized_path != "/" else self.api_prefix

    def _request(
        self,
        method: str,
        path: str,
        auth_required: bool = False,
        use_api_prefix: bool = True,
        **kwargs,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif auth_required:
            raise ValueError("This operation requires a bearer token. Set token before calling it.")

        response = self._client.request(method, self._build_path(path, use_api_prefix), headers=headers, **kwargs)
        if response.is_error:
            message = self._extract_error_message(response)
            raise WorkspaceServiceClientError(response.status_code, message, response)
        return response

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or "Request failed"

        if isinstance(payload, dict):
            if payload.get("message"):
                return str(payload["message"])
            if payload.get("detail"):
                return str(payload["detail"])
        return response.text or "Request failed"
