import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import BaseModel

from workspace_service.provider_clients import registry


def test_discovery_does_not_import_provider():
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
from workspace_service.provider_clients.registry import PROVIDER_CLIENTS
assert "cloudferro" in list(PROVIDER_CLIENTS)
assert "CLOUDFERRO" in PROVIDER_CLIENTS
assert len(PROVIDER_CLIENTS) >= 1
assert "workspace_service.provider_clients.cloudferro" not in sys.modules
client = PROVIDER_CLIENTS["CLOUDFERRO"]
assert "workspace_service.provider_clients.cloudferro" in sys.modules
assert PROVIDER_CLIENTS["cloudferro"] is client
"""],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_new_provider_is_discovered_and_loaded_once(monkeypatch):
    class Parameters(BaseModel):
        pass

    class Client:
        workspace_parameters = Parameters
        provision_workspace = Mock()

    monkeypatch.setattr(registry, "iter_modules", lambda paths: [
        SimpleNamespace(name="new_provider", ispkg=False),
        SimpleNamespace(name="_helper", ispkg=False),
        SimpleNamespace(name="registry", ispkg=False),
        SimpleNamespace(name="subpackage", ispkg=True),
    ])
    importer = Mock(return_value=SimpleNamespace(PROVIDER_CLIENT=Client))
    monkeypatch.setattr(registry, "import_module", importer)
    clients = registry.ProviderClients()
    assert list(clients) == ["new_provider"]
    importer.assert_not_called()
    assert clients["NEW_PROVIDER"] is Client
    assert clients.get("new_provider") is Client
    importer.assert_called_once_with("workspace_service.provider_clients.new_provider")
    assert clients.get("../cloudferro") is None
    assert clients.get("unknown") is None
    assert importer.call_count == 1


def test_invalid_provider_export_is_an_error(monkeypatch):
    clients = registry.ProviderClients()
    monkeypatch.setattr(registry, "import_module", Mock(return_value=SimpleNamespace()))
    with pytest.raises(TypeError, match="must export PROVIDER_CLIENT"):
        clients["cloudferro"]


def test_provider_import_failure_is_not_hidden(monkeypatch):
    clients = registry.ProviderClients()
    monkeypatch.setattr(registry, "import_module", Mock(side_effect=ImportError("missing SDK")))
    with pytest.raises(ImportError, match="missing SDK"):
        clients.get("cloudferro")
