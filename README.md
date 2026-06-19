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
