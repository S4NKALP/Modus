import importlib
import importlib.util
import inspect
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Type

from fabric.utils import logger

from window.spotlight.api.plugin import SpotlightPlugin

VENV_DIR = ".venvs"


@dataclass
class DiscoveredPlugin:
    """A plugin class discovered on disk, not yet instantiated."""

    plugin_class: Type[SpotlightPlugin]
    source: str
    path: str
    module_name: str = ""


class PluginLoader:
    """Discovers and imports plugins from filesystem paths.

    Handles:
      - Single-file plugins (weather.py)
      - Package plugins (weather/plugin.py or weather/__init__.py)
      - Built-in plugins from the plugins/ directory
      - Third-party plugins from config/data/system paths
      - Per-plugin virtualenvs for isolated dependencies
    """

    USER_PATHS = [Path(__file__).resolve().parents[4] / "config" / "plugins"]

    def __init__(self, builtin_dir: str | Path):
        self._builtin_dir = Path(builtin_dir)
        self._loaded_modules: set[str] = set()

    def discover(self) -> list[DiscoveredPlugin]:
        """Scan all paths and return discovered plugin classes."""
        found: list[DiscoveredPlugin] = []
        seen_ids: set[str] = set()

        # Built-in plugins first
        for entry in self._discover_directory(self._builtin_dir, "builtin"):
            if entry.plugin_class.id not in seen_ids:
                seen_ids.add(entry.plugin_class.id)
                found.append(entry)

        # Third-party paths
        source_labels = ["user", "system"]
        for path, source in zip(self.USER_PATHS, source_labels, strict=False):
            if path.is_dir():
                for entry in self._discover_directory(path, source):
                    pid = entry.plugin_class.id
                    if pid and pid not in seen_ids:
                        seen_ids.add(pid)
                        found.append(entry)
                    elif pid in seen_ids:
                        logger.warning(
                            f"[PluginLoader] Duplicate plugin id '{pid}' "
                            f"from {entry.path}, skipping"
                        )

        return found

    def _discover_directory(
        self, directory: Path, source: str
    ) -> list[DiscoveredPlugin]:
        """Scan a directory for plugins."""
        results: list[DiscoveredPlugin] = []
        if not directory.is_dir():
            return results

        for item in sorted(directory.iterdir()):
            try:
                discovered = self._discover_item(item, source)
                if discovered:
                    results.append(discovered)
            except Exception as e:
                logger.error(f"[PluginLoader] Error discovering {item.name}: {e}")

        return results

    def _discover_item(self, item: Path, source: str) -> DiscoveredPlugin | None:
        """Discover a single plugin from a file or directory."""
        if item.is_file() and item.suffix == ".py":
            if item.name.startswith("_"):
                return None
            return self._load_file_plugin(item, source)

        if item.is_dir() and not item.name.startswith("_"):
            return self._load_package_plugin(item, source)

        return None

    def _load_file_plugin(self, filepath: Path, source: str) -> DiscoveredPlugin | None:
        """Import a single .py file and extract PLUGIN."""
        # Check for requirements.txt next to the .py file
        req_file = filepath.parent / "requirements.txt"
        if req_file.exists():
            self._ensure_venv(filepath.parent, source)

        # Also check for a companion directory with requirements
        # e.g. weather.py + weather/requirements.txt
        companion_dir = filepath.parent / filepath.stem
        if companion_dir.is_dir():
            companion_req = companion_dir / "requirements.txt"
            if companion_req.exists():
                self._ensure_venv(companion_dir, source)

        module_name = f"modus_plugin_{source}_{filepath.stem}"
        plugin_class = self._import_and_extract(filepath, module_name)
        if plugin_class:
            return DiscoveredPlugin(
                plugin_class=plugin_class,
                source=source,
                path=str(filepath),
            )
        return None

    def _load_package_plugin(
        self, pkg_dir: Path, source: str
    ) -> DiscoveredPlugin | None:
        """Import a package plugin (plugin.py or __init__.py).

        Sets up the package hierarchy in sys.modules so that relative
        imports (from .module import ...) work correctly.
        """
        # Check for requirements.txt in package directory
        req_file = pkg_dir / "requirements.txt"
        if req_file.exists():
            self._ensure_venv(pkg_dir, source)

        parent_pkg = pkg_dir.parent.name
        pkg_name = pkg_dir.name
        full_pkg_name = f"{parent_pkg}.{pkg_name}"
        mod_name = full_pkg_name

        # Ensure parent directory is on sys.path for submodule resolution
        parent_dir = str(pkg_dir.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        # Set up package hierarchy so relative imports work
        self._ensure_package_modules(pkg_dir.parent, parent_pkg, pkg_name)

        candidates = [
            (pkg_dir / "plugin.py", None),
            (pkg_dir / "__init__.py", [str(pkg_dir)]),
        ]

        for candidate, search_locs in candidates:
            if candidate.exists():
                plugin_class = self._import_and_extract(
                    candidate, full_pkg_name, search_locs
                )
                if plugin_class:
                    return DiscoveredPlugin(
                        plugin_class=plugin_class,
                        source=source,
                        path=str(candidate),
                        module_name=mod_name,
                    )

        return None

    def _ensure_package_modules(
        self, parent_dir: Path, parent_pkg: str, pkg_name: str
    ) -> None:
        """Create stub package modules in sys.modules for relative imports."""
        import types

        parent_mod_name = parent_pkg
        if parent_mod_name not in sys.modules:
            parent_mod = types.ModuleType(parent_mod_name)
            parent_mod.__path__ = [str(parent_dir)]
            parent_mod.__package__ = parent_mod_name
            sys.modules[parent_mod_name] = parent_mod

        pkg_mod_name = f"{parent_pkg}.{pkg_name}"
        if pkg_mod_name not in sys.modules:
            pkg_dir = parent_dir / pkg_name
            pkg_mod = types.ModuleType(pkg_mod_name)
            pkg_mod.__path__ = [str(pkg_dir)]
            pkg_mod.__package__ = pkg_mod_name
            sys.modules[pkg_mod_name] = pkg_mod

    # ------------------------------------------------------------------
    # Plugin virtualenv management
    # ------------------------------------------------------------------

    def _ensure_venv(self, plugin_dir: Path, source: str) -> None:
        """Create or update a venv for a plugin if requirements.txt exists.

        The venv lives at <plugins_dir>/.venvs/<plugin_name>/
        Dependencies are installed into it, and its site-packages
        are added to sys.path before the plugin is imported.
        """
        req_file = plugin_dir / "requirements.txt"
        if not req_file.exists():
            return

        venv_base = plugin_dir.parent / VENV_DIR
        venv_base.mkdir(parents=True, exist_ok=True)
        venv_dir = venv_base / plugin_dir.name

        if not venv_dir.is_dir():
            logger.info(f"[PluginLoader] Creating venv for {plugin_dir.name}")
            if not self._create_venv(venv_dir):
                return

        # Check if we need to install/update deps
        marker_file = venv_dir / ".deps_installed"
        needs_install = not marker_file.exists() or self._reqs_changed(
            req_file, marker_file
        )
        if needs_install:
            logger.info(f"[PluginLoader] Installing deps for {plugin_dir.name}")
            if self._install_deps(venv_dir, req_file):
                marker_file.write_text(req_file.read_text())
            else:
                logger.error(
                    f"[PluginLoader] Dep install failed for {plugin_dir.name}, "
                    "will retry next time"
                )

        # Add venv site-packages to sys.path
        site_packages = self._find_site_packages(venv_dir)
        if site_packages and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))

    def _create_venv(self, venv_dir: Path) -> bool:
        """Create a virtualenv using uv."""
        try:
            result = subprocess.run(
                ["uv", "venv", str(venv_dir)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.error(f"[PluginLoader] uv venv failed: {result.stderr[:300]}")
            return result.returncode == 0
        except FileNotFoundError:
            logger.error("[PluginLoader] uv not found — install it first")
            return False
        except Exception as e:
            logger.error(f"[PluginLoader] Failed to create venv: {e}")
            return False

    def _install_deps(self, venv_dir: Path, req_file: Path) -> bool:
        """Install dependencies from requirements.txt using uv."""
        venv_python = venv_dir / "bin" / "python"
        try:
            result = subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "-r",
                    str(req_file),
                    "--python",
                    str(venv_python),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.error(
                    f"[PluginLoader] uv pip install failed: {result.stderr[:500]}"
                )
                return False
            return True
        except FileNotFoundError:
            logger.error("[PluginLoader] uv not found — install it first")
            return False
        except Exception as e:
            logger.error(f"[PluginLoader] Failed to install deps: {e}")
            return False

    def _find_site_packages(self, venv_dir: Path) -> Path | None:
        """Find site-packages directory in a venv."""
        # Look in lib/pythonX.Y/site-packages
        lib_dir = venv_dir / "lib"
        if lib_dir.is_dir():
            for item in lib_dir.iterdir():
                if item.name.startswith("python"):
                    site_pkgs = item / "site-packages"
                    if site_pkgs.is_dir():
                        return site_pkgs
        return None

    def _reqs_changed(self, req_file: Path, marker_file: Path) -> bool:
        """Check if requirements.txt changed since last install."""
        try:
            return req_file.read_text() != marker_file.read_text()
        except Exception:
            return True

    # ------------------------------------------------------------------
    # Module import
    # ------------------------------------------------------------------

    def _import_and_extract(
        self,
        filepath: Path,
        module_name: str,
        submodule_search_locations: list[str] | None = None,
    ) -> Type[SpotlightPlugin] | None:
        """Import a module and extract the PLUGIN attribute.

        For package __init__.py files, pass submodule_search_locations
        so that relative imports within the package work.
        """
        try:
            spec = importlib.util.spec_from_file_location(
                module_name,
                filepath,
                submodule_search_locations=submodule_search_locations,
            )
            if not spec or not spec.loader:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            self._loaded_modules.add(module_name)
            spec.loader.exec_module(module)

            plugin = self._extract_plugin_class(module, module_name)
            if not plugin:
                self._unload_module(module_name)
            return plugin

        except Exception as e:
            logger.error(f"[PluginLoader] Failed to import {filepath.name}: {e}")
            return None

    def _extract_plugin_class(
        self, module, module_name: str
    ) -> Type[SpotlightPlugin] | None:
        """Extract plugin class from a module.

        Priority:
          1. MODULE.PLUGIN attribute (explicit, preferred)
          2. First SpotlightPlugin subclass found in module (fallback)
        """
        # Preferred: explicit PLUGIN variable
        plugin_attr = getattr(module, "PLUGIN", None)
        if plugin_attr is not None:
            if (
                inspect.isclass(plugin_attr)
                and issubclass(plugin_attr, SpotlightPlugin)
                and plugin_attr is not SpotlightPlugin
            ):
                return plugin_attr
            logger.warning(
                f"[PluginLoader] {module_name}.PLUGIN is not a "
                f"SpotlightPlugin subclass, ignoring"
            )
            return None

        # Fallback: scan for subclass
        for attr_name in dir(module):
            attr_value = getattr(module, attr_name)
            if (
                inspect.isclass(attr_value)
                and issubclass(attr_value, SpotlightPlugin)
                and attr_value is not SpotlightPlugin
                and inspect.getmodule(attr_value) is module
            ):
                logger.info(
                    f"[PluginLoader] Found {attr_name} via subclass scan "
                    f"in {module_name} (consider adding PLUGIN = {attr_name})"
                )
                return attr_value

        logger.warning(f"[PluginLoader] No SpotlightPlugin found in {module_name}")
        return None

    def unload_module(self, module_name: str) -> None:
        """Remove a plugin module from sys.modules."""
        if module_name in self._loaded_modules:
            self._loaded_modules.discard(module_name)
        for key in list(sys.modules.keys()):
            if key == module_name or key.startswith(module_name + "."):
                sys.modules.pop(key, None)

    def unload_all(self) -> None:
        """Remove all loaded plugin modules from sys.modules."""
        for name in list(self._loaded_modules):
            self.unload_module(name)
        self._loaded_modules.clear()
