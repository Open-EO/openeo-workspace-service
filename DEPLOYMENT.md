# Deployment Guide

This guide covers different deployment scenarios for the OpenEO Workspaces API.

## Table of Contents

1. [Local Development](#local-development)
2. [Docker Deployment](#docker-deployment)
3. [Kubernetes with Helm](#kubernetes-with-helm)
4. [Production Configuration](#production-configuration)

## Local Development

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git

### Setup

1. **Clone and install**
   ```bash
   git clone <repo>
   cd openeo-workspaces-api
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   ```

3. **Start services**
   ```bash
   docker-compose up -d
   ```

4. **Verify**
   ```bash
   # API should be available
   curl http://localhost:8000/health
   
   # KeyCloak admin console
   open http://localhost:8080/admin (admin/admin)
   
   # Elasticsearch
   curl http://localhost:9200
   ```

### Development Workflow

1. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies for development**
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-asyncio black isort flake8
   ```

3. **Run with auto-reload**
   ```bash
   make dev
   ```

4. **Format code**
   ```bash
   make format
   ```

5. **Run tests**
   ```bash
   make test
   ```

## Docker Deployment

### Build Image

```bash
# Build with specific tag
docker build -t myregistry/openeo-workspaces-api:0.1.0 .

# Push to registry
docker push myregistry/openeo-workspaces-api:0.1.0
```

### Run Container

```bash
docker run -d \
  -p 8000:8000 \
  -e KEYCLOAK_SERVER_URL=https://keycloak.example.com \
  -e KEYCLOAK_REALM=openeo \
  -e KEYCLOAK_CLIENT_ID=openeo-workspaces \
  -e KEYCLOAK_CLIENT_SECRET=your-secret \
  -e ELASTICSEARCH_HOST=elasticsearch.example.com \
  -e ELASTICSEARCH_PORT=9200 \
  myregistry/openeo-workspaces-api:0.1.0
```

### Docker Compose Stack

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Stop and remove volumes (careful!)
docker-compose down -v
```

## Kubernetes with Helm

### Prerequisites

- Kubernetes 1.21+
- Helm 3.0+
- kubectl configured to access your cluster

### Installation

1. **Update Helm dependencies**
   ```bash
   helm dependency update ./chart
   ```

2. **Create namespace**
   ```bash
   kubectl create namespace openeo
   ```

3. **Install chart**
   ```bash
   helm install openeo-workspaces ./chart \
     --namespace openeo \
     --values chart/values.yaml
   ```

### Verify Installation

```bash
# Check deployments
kubectl get deployments -n openeo

# Check pods
kubectl get pods -n openeo

# View logs
kubectl logs -n openeo \
  deployment/openeo-workspaces-api

# Port forward to test
kubectl port-forward -n openeo \
  svc/openeo-workspaces-api 8000:80
```

### Using External Services

If you have existing Elasticsearch and KeyCloak instances:

```bash
helm install openeo-workspaces ./chart \
  --namespace openeo \
  --set keycloak.external.enabled=true \
  --set keycloak.external.serverUrl=https://keycloak.example.com \
  --set keycloak.external.realm=openeo \
  --set keycloak.external.clientId=openeo-workspaces \
  --set keycloak.external.clientSecret=your-secret \
  --set elasticsearch.external.enabled=true \
  --set elasticsearch.external.host=elasticsearch.example.com \
  --set elasticsearch.external.port=9200 \
  --set elasticsearch.external.username=elastic \
  --set elasticsearch.external.password=your-password \
  --values chart/values.yaml
```

### Upgrade Deployment

```bash
# Update dependencies first
helm dependency update ./chart

# Upgrade release
helm upgrade openeo-workspaces ./chart \
  --namespace openeo \
  --values chart/values.yaml
```

### Uninstall

```bash
helm uninstall openeo-workspaces -n openeo
```

## Production Configuration

### Security Considerations

1. **HTTPS/TLS**
   - Configure Ingress with TLS certificates
   - Set `ELASTICSEARCH_SCHEME=https`
   - Use HTTPS for KeyCloak connections

2. **Authentication**
   - Use strong secrets for `KEYCLOAK_CLIENT_SECRET`
   - Rotate secrets regularly
   - Use Kubernetes Secrets for credential storage

3. **Network Security**
   - Enable Network Policies
   - Use Ingress class restrictions
   - Implement Pod Network Policies

4. **Data Protection**
   - Enable Elasticsearch authentication
   - Encrypt Elasticsearch data at rest
   - Use encrypted persistent volumes

### Resource Configuration

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "1000m"
```

### High Availability

1. **Multiple Replicas**
   ```yaml
   replicaCount: 3
   ```

2. **Pod Disruption Budget**
   ```yaml
   podDisruptionBudget:
     enabled: true
     minAvailable: 1
   ```

3. **Horizontal Pod Autoscaling**
   ```yaml
   autoscaling:
     enabled: true
     minReplicas: 3
     maxReplicas: 10
     targetCPUUtilizationPercentage: 80
   ```

### Monitoring and Logging

1. **Prometheus Metrics** (optional)
   - Add Prometheus client to app
   - Configure service monitor

2. **Structured Logging**
   - Use structured JSON logs
   - Aggregate logs with ELK/Loki

3. **Health Checks**
   - Liveness probe configured
   - Readiness probe configured

### Backup and Disaster Recovery

1. **Database Backups**
   ```bash
   # Elasticsearch snapshots
   curl -X PUT "localhost:9200/_snapshot/my_backup"
   ```

2. **Configuration Backups**
   ```bash
   helm get values openeo-workspaces -n openeo > values-backup.yaml
   ```

### Scaling Considerations

1. **Vertical Scaling**
   - Increase resource limits
   - Use larger machine instances

2. **Horizontal Scaling**
   - Increase replicas
   - Configure HPA with metrics
   - Ensure database can handle connections

3. **Database Scaling**
   - Elasticsearch cluster with multiple nodes
   - Index sharding strategy
   - Query optimization

## Troubleshooting

### Pod Won't Start

```bash
# Check pod events
kubectl describe pod <pod-name> -n openeo

# Check logs
kubectl logs <pod-name> -n openeo

# Check resource availability
kubectl describe nodes
```

### Connection Issues

```bash
# Test Elasticsearch connectivity
kubectl exec -it <pod-name> -n openeo -- \
  python -c "from elasticsearch import Elasticsearch; \
  es = Elasticsearch(['http://elasticsearch:9200']); \
  print(es.info())"

# Test KeyCloak connectivity
kubectl exec -it <pod-name> -n openeo -- \
  curl -s http://keycloak:8080/health
```

### Performance Issues

1. **Check resource usage**
   ```bash
   kubectl top nodes
   kubectl top pods -n openeo
   ```

2. **Check Elasticsearch**
   ```bash
   curl http://elasticsearch:9200/_cat/health
   curl http://elasticsearch:9200/_cat/indices
   ```

3. **Scale up if needed**
   ```bash
   kubectl scale deployment openeo-workspaces-api -n openeo --replicas=5
   ```

## Related Documentation

- [Helm Values Reference](../chart/values.yaml)
- [OpenEO API Docs](https://openeo.org)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)

