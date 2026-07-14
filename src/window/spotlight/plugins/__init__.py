"""
Modus Launcher plugins package.

Built-in plugins are auto-discovered via pkgutil.
Each plugin module exposes a PLUGIN variable pointing to its class.
"""

import importlib
import pkgutil

from fabric.utils import logger

__all__ = []

for module_info in pkgutil.iter_modules(__path__):
    module_name = module_info.name
    if module_name.startswith("_"):
        continue
    try:
        module = importlib.import_module(f"{__name__}.{module_name}")
        plugin_class = getattr(module, "PLUGIN", None)
        if plugin_class is not None:
            globals()[module_name] = plugin_class
            __all__.append(module_name)
    except Exception as e:
        logger.warning(
            f"[__init__] module = importlib.import_module(f'(__name__).(module_nam... failed: {e}"
        )
