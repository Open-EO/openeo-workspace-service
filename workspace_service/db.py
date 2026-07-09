"""
Git-backed workspace persistence.

Workspaces are stored as JSON files under:
  {repo_path}/workspaces/{user_id}/{workspace_id}.json

Every mutating operation (create / update / delete) produces a git commit so
the full history of workspace changes is preserved in the repository.

Configuration (all via environment variables / .env):
  GIT_REPO_PATH      – path to the local git repository (default: ./data)
  GIT_REMOTE_URL     – optional remote URL; when set, changes are pushed after
                       every commit
  GIT_AUTHOR_NAME    – committer name written into git commits
  GIT_AUTHOR_EMAIL   – committer e-mail written into git commits
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import git
from workspace_service.config import settings

logger = logging.getLogger(__name__)


class GitWorkspaceClient:
    """Git-backed workspace persistence client."""

    def __init__(self):
        self.repo_path = Path(settings.git_repo_path).resolve()
        self.remote_url: Optional[str] = settings.git_remote_url or None
        self.author = git.Actor(settings.git_author_name, settings.git_author_email)
        self._repo: Optional[git.Repo] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self):
        """Ensure the git repository exists and is ready."""
        self.repo_path.mkdir(parents=True, exist_ok=True)
        workspaces_dir = self.repo_path / "workspaces"
        workspaces_dir.mkdir(exist_ok=True)

        try:
            self._repo = git.Repo(self.repo_path)
            logger.info("Opened existing git repository at %s", self.repo_path)
        except git.InvalidGitRepositoryError:
            self._repo = git.Repo.init(self.repo_path)
            logger.info("Initialised new git repository at %s", self.repo_path)
            # Initial commit so the repo has a valid HEAD
            gitkeep = workspaces_dir / ".gitkeep"
            gitkeep.touch()
            self._repo.index.add([str(gitkeep.relative_to(self.repo_path))])
            self._repo.index.commit(
                "chore: initialise workspace repository",
                author=self.author,
                committer=self.author,
            )

        if self.remote_url:
            if "origin" not in [r.name for r in self._repo.remotes]:
                self._repo.create_remote("origin", self.remote_url)
                logger.info("Added remote 'origin' → %s", self.remote_url)
            try:
                self._repo.remotes.origin.pull()
                logger.info("Pulled latest changes from remote")
            except Exception as exc:
                logger.warning("Could not pull from remote: %s", exc)

    async def close(self):
        """No persistent connection to close."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _workspace_path(self, user_id: str, workspace_id: str) -> Path:
        return self.repo_path / "workspaces" / user_id / f"{workspace_id}.json"

    def _user_dir(self, user_id: str) -> Path:
        return self.repo_path / "workspaces" / user_id

    def _write_and_commit(self, path: Path, doc: Optional[Dict], message: str):
        """Write (or delete) a workspace file and commit the change."""
        rel = str(path.relative_to(self.repo_path))
        if doc is None:
            path.unlink(missing_ok=True)
            self._repo.index.remove([rel])
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, indent=2, default=str))
            self._repo.index.add([rel])

        self._repo.index.commit(
            message,
            author=self.author,
            committer=self.author,
        )

        if self.remote_url:
            try:
                self._repo.remotes.origin.push()
            except Exception as exc:
                logger.warning("Failed to push to remote: %s", exc)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_workspace(
        self, workspace_id: str, user_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        doc: Dict[str, Any] = {
            "id": workspace_id,
            "user_id": user_id,
            "title": data.get("title"),
            "description": data.get("description"),
            "type": data.get("type"),
            "status": "provisioning",
            "details": "Workspace is being provisioned",
            "quota": data.get("quota", settings.max_workspace_quota),
            "parameters": data.get("parameters", {}),
            "created_at": now,
            "updated_at": now,
        }
        if "url" in data:
            doc["url"] = data["url"]

        self._write_and_commit(
            self._workspace_path(user_id, workspace_id),
            doc,
            f"feat: create workspace {workspace_id} for user {user_id}",
        )
        logger.info("Created workspace: %s", workspace_id)
        return doc

    async def get_workspace(
        self, workspace_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        path = self._workspace_path(user_id, workspace_id)
        if not path.exists():
            return None
        try:
            doc = json.loads(path.read_text())
            if doc.get("user_id") != user_id:
                return None
            return doc
        except Exception as exc:
            logger.error("Failed to read workspace %s: %s", workspace_id, exc)
            return None

    async def list_workspaces(
        self, user_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[List[Dict[str, Any]], int]:
        user_dir = self._user_dir(user_id)
        if not user_dir.exists():
            return [], 0
        try:
            files = sorted(user_dir.glob("*.json"))
            total = len(files)
            page = files[offset : offset + limit]
            workspaces = [json.loads(f.read_text()) for f in page]
            return workspaces, total
        except Exception as exc:
            logger.error("Failed to list workspaces for %s: %s", user_id, exc)
            return [], 0

    async def update_workspace(
        self, workspace_id: str, user_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        doc = await self.get_workspace(workspace_id, user_id)
        if doc is None:
            return None

        doc.update({k: v for k, v in data.items() if v is not None})
        doc["updated_at"] = datetime.utcnow().isoformat()

        self._write_and_commit(
            self._workspace_path(user_id, workspace_id),
            doc,
            f"feat: update workspace {workspace_id} for user {user_id}",
        )
        return doc

    async def delete_workspace(self, workspace_id: str, user_id: str) -> bool:
        doc = await self.get_workspace(workspace_id, user_id)
        if doc is None:
            return False

        self._write_and_commit(
            self._workspace_path(user_id, workspace_id),
            None,
            f"feat: delete workspace {workspace_id} for user {user_id}",
        )
        logger.info("Deleted workspace: %s", workspace_id)
        return True


# ---------------------------------------------------------------------------
# Module-level API (mirrors the previous Elasticsearch-backed interface)
# ---------------------------------------------------------------------------

_client = GitWorkspaceClient()


async def initialize():
    """Initialise the git-backed workspace store."""
    await _client.initialize()


async def close():
    """No-op; kept for interface compatibility."""
    await _client.close()


def get_client() -> GitWorkspaceClient:
    """Return the active workspace client."""
    return _client

