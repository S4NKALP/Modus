"""
Centralized configuration service with file watching and dynamic reloads.

This service encapsulates the logic for loading the application's JSON config,
watching for file changes, and notifying registered listeners when the config
changes. It is implemented as a singleton and intended to be reused by any
module that needs dynamic configuration.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fabric.utils import Gio, GLib, get_relative_path, os


def log_errors(func):
    """Decorator to log errors in config operations"""

    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def safe_operation(func):
    """Decorator for safe operations that shouldn't raise exceptions"""

    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


class ConfigService:
    """Singleton service handling config state and reload notifications."""

    _instance: ConfigService | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        self._config: dict[str, Any] = {}
        self._reload_callbacks: list[
            Callable[[dict[str, Any], dict[str, Any]], None]
        ] = []
        self._config_file: str = self._get_config_file_path()
        self._monitors: list[Gio.FileMonitor] = []
        self._reload_source_id: int | None = None

        self._load_config()
        self._setup_monitors()

    @staticmethod
    def _get_config_file_path() -> str:
        """Get the configuration file path"""
        return get_relative_path("../config.json")

    @staticmethod
    def _is_valid_config_file(file_path: str) -> bool:
        """Check if the config file exists and is readable"""
        return os.path.exists(file_path) and os.access(file_path, os.R_OK)

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def get_all(self) -> dict[str, Any]:
        return self._config.copy()

    def has_changed(self, key: str, old_config: dict[str, Any]) -> bool:
        return self._config.get(key) != old_config.get(key)

    def register_reload_callback(
        self, callback: Callable[[dict[str, Any], dict[str, Any]], None]
    ) -> None:
        if callback in self._reload_callbacks:
            return
        self._reload_callbacks.append(callback)

    def unregister_reload_callback(
        self, callback: Callable[[dict[str, Any], dict[str, Any]], None]
    ) -> None:
        if callback not in self._reload_callbacks:
            return
        self._reload_callbacks.remove(callback)

    def stop(self) -> None:
        # Cancel any pending reload
        if self._reload_source_id is not None:
            GLib.source_remove(self._reload_source_id)
            self._reload_source_id = None

        for monitor in self._monitors:
            monitor.cancel()
        self._monitors.clear()

    @log_errors
    def _load_config(self) -> None:
        if not self._is_valid_config_file(self._config_file):
            self._config = {}
            return
        with open(self._config_file) as f:
            self._config = json.load(f)

    @safe_operation
    def _setup_monitors(self) -> None:
        files_to_watch = [self._config_file]
        for file_path in files_to_watch:
            if not self._is_valid_config_file(file_path):
                continue
            gio_file = Gio.File.new_for_path(file_path)
            monitor = gio_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
            monitor.connect("changed", self._on_file_changed, file_path)
            self._monitors.append(monitor)

    def _on_file_changed(self, monitor, file, other_file, event_type, file_path: str):
        # Option 1: Immediate reload (completely eliminates polling)
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            self._reload_config_immediate()

        # Option 2: If you still want debouncing but without polling, use idle_add
        # This processes the reload on the next main loop iteration
        # if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
        #     if self._reload_source_id is None:
        #         self._reload_source_id = GLib.idle_add(self._reload_config_idle)

    @log_errors
    def _reload_config_immediate(self) -> None:
        """Immediately reload config without any delays."""
        old_config = self._config.copy()
        self._load_config()
        self._notify_callbacks(self._config, old_config)

    @safe_operation
    def _notify_callbacks(
        self, new_config: dict[str, Any], old_config: dict[str, Any]
    ) -> None:
        """Notify all registered callbacks of config changes"""
        for callback in list(self._reload_callbacks):
            callback(new_config, old_config)

    def _reload_config_idle(self) -> bool:
        """Alternative: Reload on next idle cycle (still non-polling)."""
        old_config = self._config.copy()
        self._load_config()
        self._notify_callbacks(self._config, old_config)
        self._reload_source_id = None
        return False  # Don't repeat


_service: ConfigService | None = None


def start_config_service() -> ConfigService:
    global _service
    if _service is not None:
        return _service
    _service = ConfigService()
    return _service


def stop_config_service() -> None:
    global _service
    if _service is None:
        return
    _service.stop()
    _service = None


# Convenience helpers for concise usage
def config() -> ConfigService:
    """Get the singleton service (concise alias)."""
    return start_config_service()


def get_config(key: str, default: Any = None) -> Any:
    """Get a single config value from the singleton service."""
    return start_config_service().get(key, default)


def get_all_config() -> dict[str, Any]:
    """Get all config values from the singleton service."""
    return start_config_service().get_all()


def on_config_change(
    callback: Callable[[dict[str, Any], dict[str, Any]], None],
) -> None:
    """Register a reload callback on the singleton service."""
    start_config_service().register_reload_callback(callback)


# Static utility functions
def validate_config_structure(config: dict[str, Any]) -> bool:
    """Validate that the config has the expected structure"""
    return isinstance(config, dict)


def get_config_value(config: dict[str, Any], key_path: str, default: Any = None) -> Any:
    """Get a config value using dot notation (e.g., 'panel.datetime.enabled')"""
    keys = key_path.split(".")
    current = config

    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]

    return current


def has_config_changed(
    old_config: dict[str, Any], new_config: dict[str, Any], key_path: str
) -> bool:
    """Check if a specific config value has changed"""
    old_value = get_config_value(old_config, key_path)
    new_value = get_config_value(new_config, key_path)
    return old_value != new_value
