"""
Centralized configuration service with file watching and dynamic reloads.

This service encapsulates the logic for loading the application's JSON config,
watching for file changes, and notifying registered listeners when the config
changes. It is implemented as a singleton and intended to be reused by any
module that needs dynamic configuration.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from fabric.utils import Gio, GLib, get_relative_path, logger, os


class ConfigService:
    """Singleton service handling config state and reload notifications."""

    _instance: Optional["ConfigService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        self._config: Dict[str, Any] = {}
        self._reload_callbacks: List[
            Callable[[Dict[str, Any], Dict[str, Any]], None]
        ] = []
        self._config_file: str = get_relative_path("../../config/config.json")
        self._monitors: List[Gio.FileMonitor] = []
        self._reload_pending: bool = False
        self.RELOAD_DELAY_MS: int = 100

        self._load_config()
        self._last_notified_config = self._config.copy()
        self._setup_monitors()

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        return self._config.copy()

    def has_changed(self, key: str, old_config: Dict[str, Any]) -> bool:
        return self._config.get(key) != old_config.get(key)

    def set(self, key: str, value: Any) -> None:
        """Set a config value (local state only)."""
        self._config[key] = value

    def save(self) -> bool:
        """Persist the current config state to disk and trigger reloads."""
        try:
            os.makedirs(os.path.dirname(self._config_file), exist_ok=True)
            with open(self._config_file, "w") as f:
                json.dump(self._config, f, indent=4)

            # Manually trigger a reload to notify listeners immediately
            GLib.idle_add(self._reload_config)
            return True
        except Exception as e:
            logger.error(f"[ConfigService] Failed to save config: {e}")
            return False

    def register_reload_callback(
        self, callback: Callable[[Dict[str, Any], Dict[str, Any]], None]
    ) -> None:
        if callback not in self._reload_callbacks:
            self._reload_callbacks.append(callback)

    def unregister_reload_callback(
        self, callback: Callable[[Dict[str, Any], Dict[str, Any]], None]
    ) -> None:
        if callback in self._reload_callbacks:
            self._reload_callbacks.remove(callback)

    def stop(self) -> None:
        for monitor in self._monitors:
            try:
                monitor.cancel()
            except Exception as e:
                logger.error(f"An error occurred: {e}")
        self._monitors.clear()

    def _load_config(self) -> None:
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, "r") as f:
                    self._config = json.load(f)
            else:
                try:
                    from utils.constants import DEFAULT

                    # Ensure the config directory exists
                    os.makedirs(os.path.dirname(self._config_file), exist_ok=True)
                    with open(self._config_file, "w") as f:
                        json.dump(DEFAULT, f, indent=4)

                    self._config = DEFAULT.copy()
                    logger.info(
                        f"[ConfigService] Generated default config at {self._config_file}"
                    )
                except ImportError as e:
                    logger.error(f"[ConfigService] Failed to import defaults: {e}")
                    self._config = {}
        except Exception as e:
            logger.error(f"[ConfigService] Failed to load config: {e}")
            self._config = {}

    def _setup_monitors(self) -> None:
        files_to_watch = [self._config_file, os.path.dirname(self._config_file)]
        for file_path in files_to_watch:
            if not os.path.exists(file_path):
                continue
            try:
                gio_file = Gio.File.new_for_path(file_path)
                monitor = gio_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
                monitor.connect("changed", self._on_file_changed, file_path)
                self._monitors.append(monitor)
            except Exception as e:
                logger.error(f"[ConfigService] Failed to monitor {file_path}: {e}")

    def _on_file_changed(self, monitor, file, other_file, event_type, file_path: str):
        # Trigger on various change events to be more robust across editors/OSs
        valid_events = [
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CHANGED,
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.DELETED,
        ]
        if event_type in valid_events and not self._reload_pending:
            self._reload_pending = True
            GLib.timeout_add(self.RELOAD_DELAY_MS, self._reload_config)

    def _reload_config(self) -> bool:
        try:
            self._reload_pending = False
            old_config = self._last_notified_config.copy()
            self._load_config()

            # Always notify listeners on reload request to be safe
            for callback in list(self._reload_callbacks):
                try:
                    callback(self._config, old_config)
                except Exception as e:
                    logger.error(f"[ConfigService] Callback failed: {e}")

            self._last_notified_config = self._config.copy()
            return False
        except Exception as e:
            logger.error(f"[ConfigService] Failed to reload configuration: {e}")
            self._reload_pending = False
            return False


_service: Optional[ConfigService] = None


def start_config_service() -> ConfigService:
    global _service
    if _service is None:
        _service = ConfigService()
    return _service


def stop_config_service() -> None:
    global _service
    if _service is not None:
        _service.stop()
        _service = None


# Convenience helpers for concise usage
def config() -> ConfigService:
    """Get the singleton service (concise alias)."""
    return start_config_service()


def get_config(key: str, default: Any = None) -> Any:
    """Get a single config value from the singleton service."""
    return start_config_service().get(key, default)


def get_config_all() -> Dict[str, Any]:
    """Get the entire current configuration state."""
    return start_config_service().get_all()


def on_config_change(
    callback: Callable[[Dict[str, Any], Dict[str, Any]], None],
) -> None:
    """Register a reload callback on the singleton service."""
    start_config_service().register_reload_callback(callback)
