import pytest

from workspace_service.config import settings
from workspace_service.db import GitWorkspaceClient


@pytest.fixture
async def db(tmp_path):
    settings.git_repo_path = str(tmp_path)
    db = GitWorkspaceClient()
    await db.initialize()
    return db


async def test_default_workspace_quota(db):
    await db.create_workspace(
        workspace_id="810bb8cb-f543-4c2c-adc9-053663703285",
        user_id = "johndoe",
        data={},
    )
