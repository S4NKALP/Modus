"""
Centralized configuration service with file watching and dynamic reloads.

This service encapsulates the logic for loading the application's JSON config,
watching for file changes, and notifying registered listeners when the config
changes. It is implemented as a singleton and intended to be reused by any
module that needs dynamic configuration.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from fabric.utils import Gio, GLib, logger, os
from tomlkit import document as toml_document
from tomlkit import dump as toml_dump
from tomlkit import load as toml_load
from tomlkit.items import Integer, String, Bool, Array

from utils.utils import toml_file


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
        self._config: Any = {}
        self._reload_callbacks: List[
            Callable[[Dict[str, Any], Dict[str, Any]], None]
        ] = []
        self._config_file: str = toml_file("config.toml")
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

    def register_reload_callback(
        self, callback: Callable[[Dict[str, Any], Dict[str, Any]], None]
    ) -> None:
        if callback not in self._reload_callbacks:
            self._reload_callbacks.append(callback)

    @staticmethod
    def _dict_to_toml(d: dict) -> Any:
        doc = toml_document()
        for k, v in d.items():
            if isinstance(v, bool):
                doc[k] = Bool(v)
            elif isinstance(v, int):
                doc[k] = Integer(v)
            elif isinstance(v, str):
                doc[k] = String(v, String.STANDARD)
            elif isinstance(v, list):
                arr = Array()
                for item in v:
                    if isinstance(item, bool):
                        arr.append(Bool(item))
                    elif isinstance(item, int):
                        arr.append(Integer(item))
                    elif isinstance(item, str):
                        arr.append(String(item, String.STANDARD))
                    else:
                        arr.append(item)
                arr.set_multiline(True) if len(v) > 1 else None
                doc[k] = arr
            else:
                doc[k] = v
        return doc

    def _load_config(self) -> None:
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, "r") as f:
                    self._config = toml_load(f)
            else:
                try:
                    from utils.constants import DEFAULT

                    os.makedirs(os.path.dirname(self._config_file), exist_ok=True)
                    self._config = self._dict_to_toml(DEFAULT)
                    with open(self._config_file, "w") as f:
                        toml_dump(self._config, f)
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

    def _on_file_changed(self, monitor, file, _other_file, event_type, file_path: str):
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
