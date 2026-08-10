"""Minimal example for calling the workspace service with an openEO token."""

import openeo

from workspace_service_client import WorkspaceServiceClient


def main():
    backend_url = "https://openeo.dev.waw3-1.openeo-int.v1.dataspace.copernicus.eu"

    connection = openeo.connect(backend_url).authenticate_oidc()
    padded_token = connection.auth.bearer

    token = padded_token.rsplit("/", 1)[-1]

    print(token)

    with WorkspaceServiceClient(base_url=backend_url, token=token) as client:
        print(client.list_workspace_providers())
        result = client.list_workspaces(limit=5)
        print(result)


if __name__ == "__main__":
    main()
