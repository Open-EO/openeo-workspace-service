"""
Elasticsearch database client and operations
"""
import logging
from typing import Optional, List, Dict, Any
from elasticsearch import Elasticsearch, BadRequestError
from workspace_service.config import settings

logger = logging.getLogger(__name__)

class ElasticsearchClient:
    """Elasticsearch client wrapper"""

    def __init__(self):
        self.host = settings.elasticsearch_host
        self.port = settings.elasticsearch_port
        self.scheme = settings.elasticsearch_scheme
        self.user = settings.elasticsearch_user
        self.password = settings.elasticsearch_password
        self.index_prefix = settings.elasticsearch_index_prefix
        self.client = None

    async def initialize(self):
        """Initialize Elasticsearch connection"""
        try:
            # Build connection parameters
            hosts = [f"{self.scheme}://{self.host}:{self.port}"]
            auth = None
            if self.user and self.password:
                auth = (self.user, self.password)

            # Create client with SSL verification disabled for development
            self.client = Elasticsearch(
                hosts=hosts,
                basic_auth=auth,
                verify_certs=False,
                ca_certs=None,
                request_timeout=30
            )

            # Test connection
            info = self.client.info()
            logger.info(f"Connected to Elasticsearch: {info['version']['number']}")

            # Create indices if they don't exist
            await self._create_indices()

        except Exception as e:
            logger.error(f"Failed to initialize Elasticsearch: {e}")
            raise

    async def _create_indices(self):
        """Create required indices"""
        indices = {
            "workspaces": {
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "user_id": {"type": "keyword"},
                        "title": {"type": "text"},
                        "description": {"type": "text"},
                        "type": {"type": "keyword"},
                        "status": {"type": "keyword"},
                        "details": {"type": "text"},
                        "quota": {"type": "long"},
                        "url": {"type": "keyword"},
                        "properties": {"type": "object", "enabled": False},
                        "parameters": {"type": "object", "enabled": False},
                        "free": {"type": "long"},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"}
                    }
                }
            }
        }

        for index_name, config in indices.items():
            full_index_name = f"{self.index_prefix}-{index_name}"
            try:
                if not self.client.indices.exists(index=full_index_name):
                    self.client.indices.create(index=full_index_name, **config)
                    logger.info(f"Created index: {full_index_name}")
            except BadRequestError as e:
                if "already exists" not in str(e):
                    logger.error(f"Failed to create index {full_index_name}: {e}")

    async def close(self):
        """Close Elasticsearch connection"""
        if self.client:
            self.client.close()
            logger.info("Closed Elasticsearch connection")

    async def create_workspace(self, workspace_id: str, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new workspace document"""
        from datetime import datetime

        doc = {
            "id": workspace_id,
            "user_id": user_id,
            "title": data.get("title"),
            "description": data.get("description"),
            "type": data.get("type"),
            "status": "provisioning",
            "details": "Workspace is being provisioned",
            "quota": data.get("quota", settings.max_workspace_quota),
            "parameters": data.get("parameters", {}),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        result = self.client.index(
            index=f"{self.index_prefix}-workspaces",
            id=workspace_id,
            document=doc
        )

        logger.info(f"Created workspace: {workspace_id}")
        return doc

    async def get_workspace(self, workspace_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a workspace by ID (user must own it)"""
        try:
            result = self.client.get(
                index=f"{self.index_prefix}-workspaces",
                id=workspace_id
            )

            workspace = result["_source"]
            if workspace["user_id"] != user_id:
                return None

            return workspace
        except Exception as e:
            logger.error(f"Failed to get workspace {workspace_id}: {e}")
            return None

    async def list_workspaces(self, user_id: str, limit: int = 100, offset: int = 0) -> tuple[List[Dict[str, Any]], int]:
        """List all workspaces for a user"""
        try:
            result = self.client.search(
                index=f"{self.index_prefix}-workspaces",
                query={
                    "bool": {
                        "must": [
                            {"term": {"user_id": user_id}}
                        ]
                    }
                },
                size=limit,
                from_=offset,
                sort=["created_at"]
            )

            workspaces = [hit["_source"] for hit in result["hits"]["hits"]]
            total = result["hits"]["total"]["value"]

            return workspaces, total
        except Exception as e:
            logger.error(f"Failed to list workspaces: {e}")
            return [], 0

    async def update_workspace(self, workspace_id: str, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update workspace metadata"""
        from datetime import datetime

        # Check ownership
        existing = await self.get_workspace(workspace_id, user_id)
        if not existing:
            return None

        # Prepare update
        update_data = {
            "updated_at": datetime.utcnow().isoformat()
        }

        if "title" in data:
            update_data["title"] = data["title"]
        if "description" in data:
            update_data["description"] = data["description"]

        try:
            self.client.update(
                index=f"{self.index_prefix}-workspaces",
                id=workspace_id,
                doc=update_data
            )

            # Return updated workspace
            return await self.get_workspace(workspace_id, user_id)
        except Exception as e:
            logger.error(f"Failed to update workspace {workspace_id}: {e}")
            return None

    async def delete_workspace(self, workspace_id: str, user_id: str) -> bool:
        """Delete a workspace"""
        # Check ownership
        existing = await self.get_workspace(workspace_id, user_id)
        if not existing:
            return False

        try:
            self.client.delete(
                index=f"{self.index_prefix}-workspaces",
                id=workspace_id
            )
            logger.info(f"Deleted workspace: {workspace_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete workspace {workspace_id}: {e}")
            return False

# Global client instance
_client = ElasticsearchClient()

async def initialize():
    """Initialize database"""
    await _client.initialize()

async def close():
    """Close database connection"""
    await _client.close()

def get_client() -> ElasticsearchClient:
    """Get database client"""
    return _client
