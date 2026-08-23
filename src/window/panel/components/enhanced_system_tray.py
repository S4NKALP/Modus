import weakref

from fabric.system_tray.widgets import SystemTrayItem
from fabric.utils import logger

from services.config import get_config, on_config_change

# Track active tray items for hot-reloading
_tracked_items = weakref.WeakSet()


def should_hide(item) -> bool:
    """Check if a tray item should be hidden based on config."""
    ignore_list = get_config("panel.systray_ignore", [])
    if not ignore_list:
        return False

    title = item.title if item.title else ""
    identifier = item.identifier if item.identifier else ""

    # Check both title and identifier (case-insensitive for convenience)
    for pattern in ignore_list:
        p = pattern.lower()
        if p in title.lower() or p in identifier.lower():
            return True
    return False


def apply_enhanced_system_tray():
    # Patch __init__ to track instances
    original_init = SystemTrayItem.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _tracked_items.add(self)

    SystemTrayItem.__init__ = patched_init

    # Wrap the stock implementation so fabric keeps handling icons,
    # while we enforce the configured visibility rules
    original_do_update_properties = SystemTrayItem.do_update_properties

    def patched_do_update_properties(self, *_):
        original_do_update_properties(self)
        self.set_visible(not should_hide(self._item))

    SystemTrayItem.do_update_properties = patched_do_update_properties

    # Setup hot-reload listener
    def on_reload(new_config, old_config):
        if new_config.get("systray_ignore") != old_config.get("systray_ignore"):
            logger.info("[SysTray] Config changed, updating tray item visibility")
            for item_widget in _tracked_items:
                item_widget.do_update_properties()

    on_config_change(on_reload)
