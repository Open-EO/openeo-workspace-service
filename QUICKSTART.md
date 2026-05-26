# Quick Start Guide

Get the OpenEO Workspaces API running in minutes!

## 30-Second Setup (Docker)

```bash
# 1. Start all services
docker-compose up -d

# 2. Verify it's running
curl http://localhost:8000/health

# 3. Access the API
open http://localhost:8000/api/v1/docs
```

## What You Get

### Services Running
- **API**: http://localhost:8000
- **Elasticsearch**: http://localhost:9200
- **KeyCloak**: http://localhost:8080 (admin/admin)

### API Documentation
- Interactive Docs (Swagger): http://localhost:8000/api/v1/docs
- Alternative Docs (ReDoc): http://localhost:8000/api/v1/redoc

## Try It Out

### 1. Get Workspace Providers (No auth needed)

```bash
curl http://localhost:8000/api/v1/workspace_providers
```

### 2. Get a Token from KeyCloak

```bash
# Login to KeyCloak admin console
open http://localhost:8080/admin

# Or get token via API:
curl -X POST http://localhost:8080/realms/master/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=openeo-workspaces" \
  -d "client_secret=secret"
```

### 3. Create a Workspace (Requires auth)

```bash
TOKEN="your-token-here"

curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "create",
    "type": "s3",
    "title": "My First Workspace",
    "parameters": {
      "bucket_name": "my-bucket"
    }
  }'
```

### 4. List Your Workspaces

```bash
TOKEN="your-token-here"

curl http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer $TOKEN"
```

## Common Commands

```bash
# See all available make commands
make help

# Run the API with auto-reload
make dev

# Run tests
make test

# Format code
make format

# View logs
docker-compose logs -f openeo-workspaces-api
```

## Stop Everything

```bash
docker-compose down
```

## Next Steps

- 📖 Read [README.md](./README.md) for full documentation
- 🚀 Check [DEPLOYMENT.md](./DEPLOYMENT.md) for production setup
- 🔧 See [Makefile](./Makefile) for available commands
- 💻 Start coding with PyCharm/VS Code and `.vscode/` config

## Troubleshooting

### Port Already in Use?

```bash
# Stop the service on the port
docker-compose down

# Or use different ports in docker-compose.yml
```

### API Not Responding?

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs openeo-workspaces-api

# Ensure Elasticsearch is running
docker-compose logs elasticsearch
```

### Can't Connect to Elasticsearch?

```bash
# Verify Elasticsearch is healthy
curl http://localhost:9200/_cluster/health

# Restart it
docker-compose restart elasticsearch
```

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI application entry point |
| `app/routes/` | API endpoint implementations |
| `app/db.py` | Elasticsearch database layer |
| `app/auth.py` | KeyCloak authentication |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image definition |
| `chart/` | Kubernetes Helm chart |

## Docker Compose Services

| Service | Port | Purpose |
|---------|------|---------|
| openeo-workspaces-api | 8000 | The API service |
| elasticsearch | 9200 | Database for workspace metadata |
| keycloak | 8080 | OAuth2/OIDC authentication provider |

## API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/v1/workspace_providers` | Optional | List workspace providers |
| GET | `/api/v1/workspaces` | Required | List user's workspaces |
| POST | `/api/v1/workspaces` | Required | Create workspace |
| GET | `/api/v1/workspaces/{id}` | Required | Get workspace details |
| PATCH | `/api/v1/workspaces/{id}` | Required | Update workspace |
| DELETE | `/api/v1/workspaces/{id}` | Required | Delete workspace |

## For More Information

- **API Specification**: See `openapi.yaml`
- **Full README**: [README.md](./README.md)
- **Contributing**: [CONTRIBUTING.md](./CONTRIBUTING.md)
- **Deployment Guide**: [DEPLOYMENT.md](./DEPLOYMENT.md)

Happy coding! 🚀

