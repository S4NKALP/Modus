"""
Modus OSD modules package.
Contains UI components and functionality modules
"""

import importlib
import inspect
import pkgutil

__all__ = []

for module_info in pkgutil.iter_modules(__path__):
    module_name = module_info.name
    module = importlib.import_module(f"{__name__}.{module_name}")

    for attr_name in dir(module):
        attr_value = getattr(module, attr_name)
        if (
            isinstance(attr_value, type)
            and (attr_name.endswith("OSDContainer") or attr_name == "AnimatedScale")
            and inspect.getmodule(attr_value) is module
        ):
            globals()[attr_name] = attr_value
            __all__.append(attr_name)
