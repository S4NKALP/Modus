from typing import Any


class PluginContext:
    """Dependency injection container passed to every plugin.

    Plugins access services through this instead of importing globals.
    """

    def __init__(self, services: dict[str, Any] | None = None):
        self._services: dict[str, Any] = services or {}

    def get_service(self, name: str) -> Any | None:
        return self._services.get(name)

    def register_service(self, name: str, service: Any) -> None:
        self._services[name] = service

    def has_service(self, name: str) -> bool:
        return name in self._services
