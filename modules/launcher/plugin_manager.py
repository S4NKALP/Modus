import importlib
import importlib.util
import os
from typing import Dict, List, Type

from modules.launcher.plugin_base import PluginBase


class PluginManager:
    """
    Manages launcher plugins with lazy loading support.
    """

    def __init__(self):
        self.plugins: Dict[str, PluginBase] = {}  # Actually loaded plugin instances
        self.plugin_classes: Dict[str, Type[PluginBase]] = {}  # Available plugin classes
        self.active_plugins: List[str] = []  # List of loaded plugin names
        self.trigger_map: Dict[str, str] = {}  # Maps triggers to plugin names

        # Load built-in plugins (discover classes only)
        self._load_builtin_plugins()

        # Load external plugins (discover classes only)
        self._load_external_plugins()

        # Build trigger mapping without activating plugins
        self._build_trigger_map()

    def _load_builtin_plugins(self):
        """Load built-in plugins from the plugins directory."""
        plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")

        if not os.path.exists(plugins_dir):
            return

        for filename in os.listdir(plugins_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                plugin_name = filename[:-3]  # Remove .py extension
                self._load_plugin_from_file(plugins_dir, plugin_name)

    def _load_external_plugins(self):
        """Load external plugins from user directory."""
        # Could be implemented to load from ~/.config/launcher/plugins/
        pass

    def _load_plugin_from_file(self, plugins_dir: str, plugin_name: str):
        """Load a plugin from a Python file."""
        try:
            plugin_path = os.path.join(plugins_dir, f"{plugin_name}.py")
            spec = importlib.util.spec_from_file_location(
                f"modules.launcher.plugins.{plugin_name}", plugin_path
            )

            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)

                # Add the module to sys.modules to support relative imports
                import sys

                sys.modules[f"modules.launcher.plugins.{plugin_name}"] = module

                spec.loader.exec_module(module)

                # Look for plugin class
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, PluginBase)
                        and attr != PluginBase
                    ):
                        self.plugin_classes[plugin_name] = attr
                        break

        except Exception as e:
            print(f"Failed to load plugin {plugin_name}: {e}")

    def _build_trigger_map(self):
        """Build a mapping of triggers to plugin names without loading plugins."""
        for plugin_name, plugin_class in self.plugin_classes.items():
            try:
                # Get triggers from class without instantiating
                triggers = self._get_class_triggers(plugin_class)
                for trigger in triggers:
                    self.trigger_map[trigger.lower()] = plugin_name
            except Exception as e:
                print(f"Failed to get triggers for plugin {plugin_name}: {e}")

    def _get_class_triggers(self, plugin_class: Type[PluginBase]) -> List[str]:
        """Get triggers from a plugin class without full initialization."""
        # Check if the plugin class has a class-level triggers attribute
        if hasattr(plugin_class, 'TRIGGERS'):
            return plugin_class.TRIGGERS

        # Fallback: create a minimal instance to get triggers
        try:
            temp_instance = plugin_class()
            # Try to get triggers without full initialization if possible
            if hasattr(temp_instance, '_default_triggers'):
                triggers = temp_instance._default_triggers
            else:
                # Last resort: minimal initialization
                temp_instance.initialize()
                triggers = temp_instance.get_triggers()
                temp_instance.cleanup()
            return triggers
        except Exception as e:
            print(f"Failed to get triggers for {plugin_class.__name__}: {e}")
            # Fallback: return empty list if we can't get triggers
            return []

    def activate_plugin(self, plugin_name: str) -> bool:
        """Activate a plugin by name (lazy loading)."""
        if plugin_name in self.plugins:
            # Already activated
            return True

        if plugin_name not in self.plugin_classes:
            return False

        try:
            # Instantiate plugin
            plugin_class = self.plugin_classes[plugin_name]
            plugin_instance = plugin_class()

            # Initialize plugin
            plugin_instance.initialize()

            # Store plugin
            self.plugins[plugin_name] = plugin_instance
            self.active_plugins.append(plugin_name)

            print(f"Lazy loaded plugin: {plugin_name}")
            return True

        except Exception as e:
            print(f"Failed to activate plugin {plugin_name}: {e}")
            return False

    def deactivate_plugin(self, plugin_name: str) -> bool:
        """Deactivate a plugin by name."""
        if plugin_name not in self.plugins:
            return False

        try:
            # Cleanup plugin
            plugin = self.plugins[plugin_name]
            plugin.cleanup()

            # Remove from active plugins
            del self.plugins[plugin_name]
            if plugin_name in self.active_plugins:
                self.active_plugins.remove(plugin_name)

            return True

        except Exception as e:
            print(f"Failed to deactivate plugin {plugin_name}: {e}")
            return False

    def get_active_plugins(self) -> List[PluginBase]:
        """Get list of active plugin instances."""
        return [
            self.plugins[name] for name in self.active_plugins if name in self.plugins
        ]

    def get_plugin_for_trigger(self, trigger: str) -> PluginBase:
        """Get plugin instance for a trigger, loading it if necessary."""
        trigger_lower = trigger.lower()

        # Check if we have a plugin for this trigger
        plugin_name = self.trigger_map.get(trigger_lower)
        if not plugin_name:
            return None

        # Load the plugin if not already loaded
        if plugin_name not in self.plugins:
            if not self.activate_plugin(plugin_name):
                return None

        return self.plugins.get(plugin_name)

    def find_trigger_plugin(self, query: str) -> tuple:
        """Find plugin and trigger for a query without loading the plugin."""
        query_lower = query.lower().strip()

        # Sort triggers by length (longest first) to match more specific triggers first
        sorted_triggers = sorted(self.trigger_map.items(), key=lambda x: len(x[0]), reverse=True)

        for trigger, plugin_name in sorted_triggers:
            trigger_lower = trigger.lower()

            # Exact match with trigger
            if query_lower == trigger_lower:
                return plugin_name, trigger

            # Match trigger followed by space
            if query_lower.startswith(trigger_lower + " "):
                return plugin_name, trigger

        return None, ""

    def get_plugin_names(self) -> List[str]:
        """Get list of available plugin names."""
        return list(self.plugin_classes.keys())

    def get_active_plugin_names(self) -> List[str]:
        """Get list of active plugin names."""
        return self.active_plugins.copy()

    def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a plugin."""
        was_active = plugin_name in self.active_plugins

        # Deactivate if active
        if was_active:
            self.deactivate_plugin(plugin_name)

        # Remove from classes
        if plugin_name in self.plugin_classes:
            del self.plugin_classes[plugin_name]

        # Reload from file
        plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")
        self._load_plugin_from_file(plugins_dir, plugin_name)

        # Reactivate if it was active
        if was_active and plugin_name in self.plugin_classes:
            return self.activate_plugin(plugin_name)

        return plugin_name in self.plugin_classes
