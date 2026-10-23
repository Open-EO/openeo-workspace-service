# openEO Workspace Clients

Python clients for the [openEO Workspace Service](https://github.com/Open-EO/openeo-workspace-service).
Requires Python 3.11 or newer.

```bash
pip install openeo-workspace-clients
```

## Workspace API client

```python
import os

from workspace_service_client import WorkspaceServiceClient

with WorkspaceServiceClient(
    base_url="https://your-openeo-backend.example",
    token=os.environ["OPENEO_ACCESS_TOKEN"],
) as client:
    print(client.list_workspace_providers())
    print(client.list_workspaces())
```

## CloudFerro bucket client

```python
import os

from workspace_service.provider_clients.cloudferro import CloudFerroBucketProvisioner

with CloudFerroBucketProvisioner(
    access_key=os.environ["AWS_ACCESS_KEY_ID"],
    secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
) as buckets:
    buckets.create_bucket("my-unique-workspace-bucket")
```

Creating a bucket provisions real cloud resources. The default endpoint is
`https://s3.waw3-1.cloudferro.com`. Buckets are private by default, with lifecycle
rules to abort incomplete multipart uploads after one day and remove expired
delete markers. `delete_bucket` only deletes empty buckets.

The distribution includes the API client and storage-provider clients, not the
API server, deployment files or credentials. See the repository README for
provider configuration, provisioning options and instructions for adding clients.
