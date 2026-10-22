"""Discover provider modules without importing them until first use."""

from collections.abc import Iterator, Mapping
from importlib import import_module
from pkgutil import iter_modules
from threading import RLock

from pydantic import BaseModel

from workspace_service import provider_clients


class ProviderClients(Mapping[str, type]):
    """Read-only registry of installed provider modules and lazily loaded clients."""

    def __init__(self) -> None:
        self._modules = {
            module.name: f"{provider_clients.__name__}.{module.name}"
            for module in iter_modules(provider_clients.__path__)
            if not module.ispkg and not module.name.startswith("_")
            and module.name != "registry"
        }
        self._clients: dict[str, type] = {}
        self._lock = RLock()

    def __iter__(self) -> Iterator[str]:
        return iter(self._modules)

    def __len__(self) -> int:
        return len(self._modules)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.lower() in self._modules

    def __getitem__(self, name: str) -> type:
        module_name = self._modules[name.lower()]
        with self._lock:
            if module_name not in self._clients:
                module = import_module(module_name)
                client = getattr(module, "PROVIDER_CLIENT", None)
                parameters = getattr(client, "workspace_parameters", None)
                if (
                    not isinstance(client, type)
                    or not isinstance(parameters, type)
                    or not issubclass(parameters, BaseModel)
                    or not callable(getattr(client, "provision_workspace", None))
                ):
                    raise TypeError(
                        f"{module_name} must export PROVIDER_CLIENT with a Pydantic "
                        "workspace_parameters model and provision_workspace method"
                    )
                self._clients[module_name] = client
            return self._clients[module_name]


PROVIDER_CLIENTS = ProviderClients()
