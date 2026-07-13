import json
from pathlib import Path

from fabric.utils import logger

from window.spotlight.api.context import PluginContext
from window.spotlight.api.plugin import SpotlightPlugin
from window.spotlight.core.loader import PluginLoader
from window.spotlight.core.registry import PluginEntry, PluginRegistry


class PluginManager:
    """Manages plugin lifecycle: load, enable, disable, reload.

    Responsibilities:
      - Orchestrate discovery (loader) and storage (registry)
      - Instantiate and initialize enabled plugins
      - Persist disabled state via TOML config
      - Provide the active plugin set to the search pipeline
    """

    DISABLED_KEY = "disabled_plugins"

    def __init__(
        self,
        loader: PluginLoader,
        registry: PluginRegistry,
        context: PluginContext,
    ):
        self._loader = loader
        self._registry = registry
        self._context = context
        self._disabled_ids: set[str] = set()

    @property
    def registry(self) -> PluginRegistry:
        return self._registry

    def load_all(self) -> None:
        """Discover, register, and instantiate all plugins."""
        self._load_disabled_list()

        discovered = self._loader.discover()
        for dp in discovered:
            self._registry.register(dp)

        for entry in self._registry.get_all():
            if entry.id in self._disabled_ids:
                entry.enabled = False
                continue
            self._instantiate(entry)

        logger.info(
            f"[PluginManager] Loaded {len(self._registry.get_enabled())} plugins"
        )

    def enable(self, plugin_id: str) -> bool:
        entry = self._registry.get(plugin_id)
        if not entry or entry.enabled:
            return False

        entry.enabled = True
        self._disabled_ids.discard(plugin_id)

        if not entry.instance:
            self._instantiate(entry)

        self._save_disabled_list()
        return entry.instance is not None

    def disable(self, plugin_id: str) -> bool:
        entry = self._registry.get(plugin_id)
        if not entry or not entry.enabled:
            return False

        self._call_cleanup(entry)
        entry.enabled = False
        self._disabled_ids.add(plugin_id)
        self._save_disabled_list()
        return True

    def reload(self, plugin_id: str) -> bool:
        entry = self._registry.get(plugin_id)
        if not entry:
            return False

        if entry.instance:
            try:
                # Quick reload: just re-initialize same class instance
                entry.instance.reload()
                return True
            except Exception as e:
                logger.error(f"[PluginManager] Failed to reload {plugin_id}: {e}")
                return False

        # Not instantiated yet, just re-instantiate
        if entry.enabled:
            return self._instantiate(entry)
        return False

    def deep_reload(self, plugin_id: str) -> bool:
        """Full re-import from disk. Picks up code changes.

        Destroys the old instance, removes the module from sys.modules,
        re-discovers the plugin class, re-instantiates, and re-initializes.
        Use during plugin development to avoid restarting Modus.
        """
        entry = self._registry.get(plugin_id)
        if not entry:
            return False

        self._call_cleanup(entry)
        if entry.module_name:
            self._loader.unload_module(entry.module_name)

        fp = Path(entry.path) if entry.path else None
        if fp and fp.exists():
            source = entry.source
            if fp.is_file() and fp.suffix == ".py":
                dp = self._loader._load_file_plugin(fp, source)
            elif fp.is_dir():
                dp = self._loader._load_package_plugin(fp, source)
            else:
                dp = None
            if dp and dp.plugin_class.id == plugin_id:
                entry.plugin_class = dp.plugin_class
                return self._instantiate(entry)
        return False

    def reload_all(self) -> None:
        for entry in self._registry.get_enabled():
            if entry.instance:
                try:
                    entry.instance.reload()
                except Exception as e:
                    logger.error(f"[PluginManager] Failed to reload {entry.id}: {e}")

    def reload_all_full(self) -> None:
        """Reload all enabled plugins from disk. Accepts new classes, methods, etc."""
        for entry in self._registry.get_all():
            self.deep_reload(entry.id)

    def stop_all(self) -> None:
        for entry in self._registry.get_all():
            self._call_cleanup(entry)

    def release_memory_all(self) -> None:
        for entry in self._registry.get_enabled():
            if entry.instance:
                try:
                    entry.instance.release_memory()
                except Exception as e:
                    logger.error(
                        f"[PluginManager] Error releasing memory for {entry.id}: {e}"
                    )

    def get_active_plugins(self) -> list[SpotlightPlugin]:
        return [
            entry.instance for entry in self._registry.get_enabled() if entry.instance
        ]

    def get_plugin(self, plugin_id: str) -> SpotlightPlugin | None:
        entry = self._registry.get(plugin_id)
        if entry and entry.enabled and entry.instance:
            return entry.instance
        return None

    def _instantiate(self, entry: PluginEntry) -> bool:
        try:
            instance = entry.plugin_class(self._context)
            instance.initialize()
            entry.instance = instance
            logger.info(f"[PluginManager] Instantiated {entry.id} successfully")
            return True
        except Exception as e:
            logger.error(f"[PluginManager] Failed to instantiate {entry.id}: {e}")
            return False

    def _call_cleanup(self, entry: PluginEntry) -> None:
        if not entry.instance:
            return
        try:
            entry.instance.cleanup()
        except Exception as e:
            logger.error(f"[PluginManager] Error cleaning up {entry.id}: {e}")
        entry.instance = None

    def _config_path(self) -> Path:
        from utils.utils import toml_file

        return Path(toml_file("config.toml")).parent / "plugins.json"

    def _load_disabled_list(self) -> None:
        path = self._config_path()
        if not path.exists():
            self._disabled_ids = set()
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self._disabled_ids = set(data.get("disabled", []))
        except Exception as e:
            logger.error(f"[PluginManager] Failed to load disabled list: {e}")
            self._disabled_ids = set()

    def _save_disabled_list(self) -> None:
        path = self._config_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump({"disabled": sorted(self._disabled_ids)}, f, indent=2)
        except Exception as e:
            logger.error(f"[PluginManager] Failed to save disabled list: {e}")
