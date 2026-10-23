# OpenEO Workspaces API

A FastAPI implementation of the [openEO Workspaces Extension](https://github.com/Open-EO/openeo-api/tree/draft/extensions/workspaces) for managing cloud storage workspaces with KeyCloak authentication and Elasticsearch backend.

## Features

- **OpenEO API Compliance**: Full implementation of the openEO Workspaces Extension API
- **OAuth2/OIDC Auth**: Integration with KeyCloak for authentication and authorization
- **Elasticsearch Backend**: Scalable NoSQL database for workspace metadata
- **Container Ready**: Docker image and docker-compose for local development
- **Kubernetes Ready**: Complete Helm chart for production deployment
- **RESTful API**: FastAPI with automatic OpenAPI documentation

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for containerized deployment)
- Kubernetes 1.21+ (for Helm deployment)

### Local Development

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd openeo-workspaces-api
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your KeyCloak and Elasticsearch settings
   ```

4. **Run with docker-compose**
   ```bash
   docker-compose up -d
   ```

5. **Access the API**
   - API Docs: http://localhost:8000/api/v1/docs
   - API Root: http://localhost:8000/api/v1
   - Health Check: http://localhost:8000/health
   - KeyCloak Admin: http://localhost:8080/admin (admin/admin)

### Endpoints

#### Public Endpoints
- `GET /api/v1/workspace_providers` - List supported workspace providers
- `GET /health` - Health check

#### Protected Endpoints (Require Bearer Token)
- `GET /api/v1/workspaces` - List user's workspaces
- `POST /api/v1/workspaces` - Create a new workspace
- `GET /api/v1/workspaces/{workspace_id}` - Get workspace details
- `PATCH /api/v1/workspaces/{workspace_id}` - Update workspace metadata
- `DELETE /api/v1/workspaces/{workspace_id}` - Delete workspace

## Configuration

### Publishing the Python clients

The `Publish workspace clients` GitHub Actions workflow builds one PyPI
distribution, **`openeo-workspace-clients`**, containing `workspace_service_client`
and `workspace_service.provider_clients` (plus the minimal `workspace_service`
package initializer). It does not package the API server, Helm configuration,
`keys.json` or runtime data. Its metadata lives in
`packaging/clients/pyproject.toml`; the existing root `setup.py` remains the
API-service distribution.

Before the first publication, create a PyPI trusted publisher (or pending
publisher) for:

| Setting | Value |
|---------|-------|
| PyPI project | `openeo-workspace-clients` |
| GitHub owner | `Open-EO` |
| Repository | `openeo-workspace-service` |
| Workflow filename | `publish-clients.yml` |
| Environment | `pypi` |

Create the `pypi` GitHub repository environment and configure any desired
approval/release-branch restrictions. Publishing uses short-lived OIDC credentials;
no PyPI API-token secret is needed. The PyPI project name must be available or
under your control.

To publish, update the version in `packaging/clients/pyproject.toml`, commit it,
and publish a GitHub release with the matching tag, for example
`clients-v0.1.0`. Each version can only be published once. Other release tag
prefixes are ignored. A manual workflow run builds and checks artifacts but
**does not publish**. The workflow checks package contents and runs the client
tests against the installed wheel outside the source checkout before publishing.

Consumers install both clients with `pip install openeo-workspace-clients`.
Avoid installing it alongside the API-service distribution in the same
environment: both distributions own the `workspace_service` package.

### Workspace provider definitions

The `/workspace_providers` response is loaded from
`chart/files/workspace_providers.json`, a JSON object mapping provider identifiers
to their definitions. The Helm chart mounts it read-only at
`/app/config/workspace_providers.json` and sets `WORKSPACE_PROVIDERS_FILE`.
To supply deployment-specific definitions:

```bash
helm upgrade --install openeo-workspaces ./chart \
  --set-file config.workspaceProvidersJson=./providers.json
```

Provider configuration changes trigger a pod rollout. The application loads and
validates the file on startup; missing files or invalid definitions prevent
startup instead of falling back to hardcoded providers. For local or Docker runs,
the bundled JSON is the default; set `WORKSPACE_PROVIDERS_FILE` to use another
file. Provider definitions must not contain credentials or secrets.

### Creating provisioned workspaces

`POST /workspaces/api/v1/workspaces` with `intent: "create"` dispatches the
case-insensitive `type` to a discovered client in
`workspace_service/provider_clients`. Currently `cloudferro` is supported; a
provider must also be advertised with the `create` intent in the provider JSON.
Provider modules are discovered from the installed `provider_clients` package.
Each module exports `PROVIDER_CLIENT`, a class with a Pydantic
`workspace_parameters` model and a `provision_workspace` method. For example,
`cloudferro.py` exports `CloudFerroBucketProvisioner`. Modules are imported and
their client classes cached only on first use; credential-bearing SDK instances
are still created per request and closed afterwards. No central registration is
needed. Private modules (names starting with `_`) and `registry.py` are excluded.
Only discovered module names can be selected; arbitrary request strings are
never used as import paths.

```json
{
  "intent": "create",
  "type": "cloudferro",
  "parameters": {
    "aws_access_key_id": "<access-key>",
    "aws_secret_access_key": "<secret-key>",
    "bucket_name": "my-workspace-bucket"
  }
}
```

The optional bucket name defaults to `openeo-workspace-<workspace-id>`.
Provisioning runs outside the event loop. On success the response is a `ready`
workspace with `url` and `properties` containing `bucket_name`, `region`,
`endpoint_url` and `s3_url`, plus a `Location` header. These details are persisted
and available from the workspace detail endpoint. Request credentials are not
stored in the Git metadata or returned. Provisioning failures return HTTP 502 and
mark the metadata `unavailable`; partially created buckets are not automatically
deleted. Unknown create types return HTTP 400; invalid parameters return HTTP 422.
`intent: "register"` remains metadata-only and requires `type`, `url` and
`parameters`; it does not call a provider client.

### Adding your own provider client

Two pieces are required: a Python module that provisions storage and a JSON
definition that advertises it to API users. Adding only the JSON entry does not
install a client, and adding only the Python module does not expose it for
`create` requests.

#### Implement the client module

Create `workspace_service/provider_clients/my_storage.py`. Use a lowercase Python
module name: `my_storage.py` corresponds to the JSON key and request type
`my_storage`. Discovery scans direct `.py` modules, not subpackages, and ignores
`registry.py` and names starting with `_`.

Use the following skeleton, replacing the `NotImplementedError` with your SDK or
HTTP API calls:

```python
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class MyStorageParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aws_access_key_id: SecretStr = Field(min_length=1)
    aws_secret_access_key: SecretStr = Field(min_length=1)
    bucket_name: str | None = None
    region: str = "my-region"


class MyStorageClient:
    workspace_parameters = MyStorageParameters

    @classmethod
    def provision_workspace(
        cls, workspace_id: str, parameters: MyStorageParameters,
    ) -> dict[str, Any]:
        # Create storage using the validated parameters, then return metadata.
        raise NotImplementedError("Implement the provider's provisioning API calls")


PROVIDER_CLIENT = MyStorageClient
```

The module-level `PROVIDER_CLIENT` export is mandatory; its class name is your
choice. `workspace_parameters` must be a Pydantic model class.
`provision_workspace` must be a synchronous callable accepting the workspace ID
and validated parameters. It runs in a worker thread and must return only after
the storage is ready, with a dictionary shaped like:

```json
{
  "url": "https://storage.example/my-bucket",
  "properties": {
    "bucket_name": "my-bucket",
    "region": "my-region",
    "endpoint_url": "https://storage.example",
    "s3_url": "s3://my-bucket"
  }
}
```

Use a URL appropriate for your storage service; the S3-specific properties are
examples, not mandatory fields. Do not return credentials or override workspace
identity/status fields. Exceptions must propagate so the route can mark the
workspace `unavailable` and return HTTP 502. Close SDK clients/connections before
returning, and avoid provisioning or network calls during module import.

**Current route constraints:** the parameter model must expose `bucket_name`.
If it is `None`, the route fills in `openeo-workspace-<workspace-id>`. The route
currently excludes only `aws_access_key_id` and `aws_secret_access_key` when
persisting parameters. Use these names for request credentials; any additional
secret fields require extending that exclusion before enabling the provider.
`SecretStr` alone is not a persistence exclusion. Providers needing other
parameter conventions require a corresponding route change.

Add SDK dependencies to `requirements.txt` if needed. Modules are discovered at
process startup and imported on first use; client classes are cached, not
credential-bearing instances. Rebuild the application image and restart the
service after adding or changing client code. No registry edit is needed.

#### Advertise the provider in JSON

Merge an entry with the same identifier into
`chart/files/workspace_providers.json`, preserving any existing providers:

```json
{
  "my_storage": {
    "title": "My storage",
    "description": "Workspace buckets provisioned by my storage service.",
    "intents": ["create"],
    "parameters": {
      "aws_access_key_id": {
        "type": "string",
        "required": true,
        "description": "Storage access key"
      },
      "aws_secret_access_key": {
        "type": "string",
        "required": true,
        "description": "Storage secret key"
      },
      "bucket_name": {
        "type": "string",
        "description": "Optional bucket name"
      },
      "region": {
        "type": "string",
        "description": "Storage region; defaults to my-region"
      }
    },
    "links": []
  }
}
```

The JSON parameters describe the public API; the Python model performs actual
validation. Keep their names, required fields and descriptions consistent.
Include `create` to allow provisioning; include `register` only if you also want
to advertise metadata-only registration. Never put credential values in this
file: it is served by the public provider endpoint.

Deploy the updated application image and chart. If using
`--set-file config.workspaceProvidersJson=./providers.json`, add the entry to
that replacement file instead; it replaces the entire bundled provider mapping.
Use `WORKSPACE_PROVIDERS_FILE` for a local replacement. Set
`config.defaultWorkspaceProvider` (or `DEFAULT_WORKSPACE_PROVIDER` locally) only
if the new provider should be selected when a request omits `type`.

Confirm `GET /workspaces/api/v1/workspace_providers` advertises `my_storage`,
then submit a create request with `"type": "my_storage"` and matching parameters.
Add tests for lazy discovery/export validation, parameter validation, successful
provisioning and returned metadata, failures, and exclusion of credentials from
responses and persisted Git history. Use mocked SDK calls or botocore `Stubber`
for unit tests; reserve live provisioning for explicitly requested integration
tests. Existing examples are in `tests/test_provider_registry.py`,
`tests/test_cloudferro.py` and `tests/test_api.py`.

### CloudFerro bucket provisioning

`workspace_service.provider_clients.cloudferro.CloudFerroBucketProvisioner` uses CloudFerro's
S3-compatible API directly, without Terraform, the AWS CLI or Vault. Supply
existing bucket-owner S3 credentials (not OpenStack login credentials). It is a
synchronous class usable directly or through the workspace creation endpoint.

```python
import os

from workspace_service.provider_clients.cloudferro import CloudFerroBucketProvisioner

with CloudFerroBucketProvisioner(
    access_key=os.environ["AWS_ACCESS_KEY_ID"],
    secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
) as buckets:
    buckets.create_bucket(
        "my-workspace-bucket",
        policies=[{
            "principal": "arn:aws:iam::project-id:user/user-id",
            "bucket_access": "LRWSAFE",
            "policy_vars": {"KEY": "*"},
        }],
        versioning="Enabled",
        cors_policy="get_head_from_anywhere_content_headers",
    )
```

The default endpoint is `https://s3.waw3-1.cloudferro.com`, region `waw3-1`.
Both can be overridden. WAW regions omit S3's location constraint.
To create and verify a private test bucket using a local JSON file containing
`aws_access_key` and `aws_secret_key`, run:

```bash
python -m workspace_service.provider_clients.cloudferro --keys keys.json
```

This generates a unique name, checks the default lifecycle configuration and
empty/private state, and leaves the bucket in place. Use `--bucket-name` to
specify a name. Failures propagate and do not automatically delete the bucket.
Keep the credentials file out of version control.

`configure_bucket` accepts the same configuration options for existing buckets;
`set_versioning` enables or suspends versioning. `delete_bucket` only deletes
empty buckets and never removes objects, versions or multipart uploads.

Configuration mirrors the Terraform bucket module:

- Named access policies: `R`, `RW`, `LR`, `LRW`, `BucketInventory`,
  `BucketInventoryOBS`; versioned policies: `R`, `LR`, `LRW`, `LRWSAFE`.
  Unsupported template/versioning combinations fail before any API calls.
- Public access: `none` (default), `R`, or `DANGER_LR` (public listing and reads).
  `ip_restrictions` accepts CIDRs and denies access from other addresses.
- CORS presets: `none`, `get_from_anywhere_anyheader`, `get_from_apex`,
  `get_from_sonata`, `get_from_webeditor`, `get_head_from_anywhere_content_headers`.
- Lifecycle defaults abort incomplete multipart uploads after one day and clean
  expired delete markers. `lifecycle_rules` accepts the Terraform rule names
  `abort_multipart_after_1_day`, `expired_deletion_markers`, and
  `CAUTION_DANGER_expire_objects_param_prefix_days` (requires `Prefix` and positive
  integer `Days`). Append `@suffix` for multiple instances. **Expiration deletes
  normal objects** and disables the default delete-marker rule. Actions sharing
  a prefix are merged; conflicting actions are rejected.

Unlike bugs in the Terraform scripts, `Suspended` actually suspends versioning,
public/IP-only policies are applied even without explicit grants, and policy
checksums use standard base64 MD5. Versioning cannot be reset to `Unset`.
Lifecycle IDs are limited to 255 characters. All configuration is validated
before creation; API failures propagate, without automatic deletion of a
partially configured bucket. Policy/lifecycle updates replace the corresponding
configuration; an empty policy, `none` CORS or `Unset` versioning leaves those
settings untouched rather than removing existing configuration.

### Environment Variables

```bash
# API
DEBUG=false
API_VERSION=v1

# KeyCloak
KEYCLOAK_SERVER_URL=https://keycloak.example.com
KEYCLOAK_REALM=openeo
KEYCLOAK_CLIENT_ID=openeo-workspaces
KEYCLOAK_CLIENT_SECRET=your-secret
KEYCLOAK_ISSUER=
KEYCLOAK_VERIFY_TLS=true
KEYCLOAK_VERIFY_AUDIENCE=true
KEYCLOAK_JWKS_CACHE_TTL_SECONDS=300

# Elasticsearch
ELASTICSEARCH_HOST=localhost
ELASTICSEARCH_PORT=9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=password
ELASTICSEARCH_SCHEME=https
```

## Deployment

### Docker

Build and run the container:

```bash
docker build -t openeo-workspaces-api:0.1.0 .
docker run -p 8000:8000 \
  -e KEYCLOAK_SERVER_URL=https://keycloak.example.com \
  -e ELASTICSEARCH_HOST=elasticsearch.example.com \
  openeo-workspaces-api:0.1.0
```

### Kubernetes with Helm

1. **Add Helm repositories**
   ```bash
   helm repo add elastic https://helm.elastic.co
   helm repo add codecentric https://codecentric.github.io/helm-charts
   helm repo update
   ```

2. **Install the chart**
   ```bash
   helm install openeo-workspaces ./chart \
     --namespace openeo \
     --create-namespace \
     --values chart/values.yaml
   ```

3. **Configure external services** (if not using chart dependencies)
   ```bash
   helm install openeo-workspaces ./chart \
     --set keycloak.external.enabled=true \
     --set keycloak.external.serverUrl=https://keycloak.example.com \
     --set elasticsearch.external.enabled=true \
     --set elasticsearch.external.host=elasticsearch.example.com
   ```

4. **Verify deployment**
   ```bash
   kubectl get pods -n openeo
   kubectl logs -n openeo svc/openeo-workspaces-api
   ```

## Workspace Providers

The API supports the following workspace providers:

### S3
- **Intent**: create, register
- **Parameters**:
  - `aws_access_key_id`: AWS access key
  - `aws_secret_access_key`: AWS secret key
  - `bucket_name`: S3 bucket name

## API Examples

### Get Workspace Providers

```bash
curl https://openeo.example/api/v1/workspace_providers
```

### Create a Workspace

```bash
curl -X POST https://openeo.example/api/v1/workspaces \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "create",
    "type": "s3",
    "title": "My Workspace",
    "description": "A workspace for analysis results",
    "parameters": {
      "bucket_name": "my-bucket"
    }
  }'
```

### List Workspaces

```bash
curl https://openeo.example/api/v1/workspaces \
  -H "Authorization: Bearer {token}"
```

### Python Client

The repository includes a Python client in `workspace_service_client`:

```python
from workspace_service_client import WorkspaceServiceClient

with WorkspaceServiceClient(
    base_url="https://openeo.example",
    token="<bearer-token>",
) as client:
    providers = client.list_workspace_providers()
    workspaces = client.list_workspaces(limit=100)
```

### Get Workspace Details

```bash
curl https://openeo.example/api/v1/workspaces/{workspace_id} \
  -H "Authorization: Bearer {token}"
```

### Update Workspace

```bash
curl -X PATCH https://openeo.example/api/v1/workspaces/{workspace_id} \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Title",
    "description": "Updated description"
  }'
```

### Delete Workspace

```bash
curl -X DELETE https://openeo.example/api/v1/workspaces/{workspace_id} \
  -H "Authorization: Bearer {token}"
```

## Authentication Flow

The API uses OAuth2/OIDC via KeyCloak:

1. Client obtains a Bearer token from KeyCloak
2. Client includes token in `Authorization: Bearer {token}` header
3. API validates token signature with KeyCloak's public keys
4. User ID extracted from token's `sub` claim
5. All workspace operations scoped to authenticated user

Get an access token (client credentials flow):

```bash
TOKEN=$(curl -s -X POST "https://keycloak.example.com/realms/openeo/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=openeo-workspaces" \
  -d "client_secret=<client-secret>" | python -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')

curl https://openeo.example/api/v1/workspaces \
  -H "Authorization: Bearer ${TOKEN}"
```

## Project Structure

```
.
├── workspace_service/
│   ├── __init__.py
│   ├── config.py              # Configuration settings
│   ├── auth.py                # KeyCloak authentication
│   ├── db.py                  # Elasticsearch client
│   ├── models.py              # Pydantic models
│   └── routes/
│       ├── providers.py       # Workspace providers endpoints
│       └── workspaces.py      # Workspace CRUD endpoints
├── chart/
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/             # Kubernetes manifests
├── main.py                    # FastAPI application
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── setup.py
└── README.md
```

## Development

### Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/
```

### Code Formatting

```bash
pip install black isort
black workspace_service/ main.py
isort workspace_service/ main.py
```

### Linting

```bash
pip install flake8
flake8 workspace_service/ main.py
```

## Troubleshooting

### Connection Issues

**Elasticsearch cannot connect:**
- Verify `elasticsearch` service is running
- Check`ELASTICSEARCH_HOST` and `ELASTICSEARCH_PORT` settings
- Ensure network connectivity between containers

**KeyCloak certificate errors:**
- In development, SSL verification is disabled for convenience
- For production, ensure proper certificates and set `ELASTICSEARCH_SCHEME=https`

### API Errors

**401 Unauthorized:**
- Token has expired or is invalid
- Verify token is included in `Authorization` header
- Check KeyCloak settings in `.env`

**404 Not Found:**
- Workspace doesn't exist or doesn't belong to user
- Check workspace_id in URL

**500 Internal Server Error:**
- Check application logs with `docker-compose logs openeo-workspaces-api`
- Verify database connections

## License

Apache License 2.0 - See LICENSE file for details

## Contact

- OpenEO Consortium: https://openeo.org
- Email: openeo.psc@uni-muenster.de

## References

- [openEO API](https://openeo.org)
- [Workspaces Extension](https://github.com/Open-EO/openeo-api/tree/draft/extensions/workspaces)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [Elasticsearch Documentation](https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html)
- [KeyCloak Documentation](https://www.keycloak.org/documentation)
