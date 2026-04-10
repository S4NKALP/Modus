from pathlib import Path
import weakref

from fabric.system_tray.widgets import SystemTrayItem
from fabric.utils import GdkPixbuf, GLib, logger

from services.config import get_config, on_config_change

# Track active tray items for hot-reloading
_tracked_items = weakref.WeakSet()


def should_hide(item) -> bool:
    """Check if a tray item should be hidden based on config."""
    ignore_list = get_config("systray_ignore", [])
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


def patched_do_update_properties(self, *_):
    # Determine the icon name to use
    item = self._item
    icon_name = item.icon_name
    attention_icon_name = item.attention_icon_name

    # Log item info for user debugging
    logger.info(
        f"[SysTray] Item: title='{getattr(item, 'title', '')}', identifier='{getattr(item, 'identifier', '')}'"
    )

    # Visibility check
    is_hidden = should_hide(item)
    self.set_visible(not is_hidden)

    if is_hidden:
        return

    if item.status == "NeedsAttention" and attention_icon_name:
        preferred_icon_name = attention_icon_name
    else:
        preferred_icon_name = icon_name

    # 1. Try the standard fabric/GTK implementation first
    pixbuf = item.get_preferred_icon_pixbuf(self._icon_size)

    # 2. If standard lookup fails, try your specific absolute path logic
    if pixbuf is None and preferred_icon_name:
        path = Path(preferred_icon_name)
        if path.is_absolute() and path.exists():
            try:
                target_size = self._icon_size if self._icon_size else 24
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    str(path),
                    target_size,
                    target_size,
                    True,  # Preserve aspect ratio
                )
            except GLib.GError:
                pixbuf = None

    # Apply the resulting pixbuf or the fallback "missing" icon
    if pixbuf:
        self._image.set_from_pixbuf(pixbuf)
    else:
        self._image.set_from_icon_name("image-missing", self._icon_size)

    tooltip = item.tooltip
    self.set_tooltip_markup(
        tooltip.description
        or tooltip.title
        or (item.title.title() if item.title else None)
        or "Unknown"
    )


def apply_enhanced_system_tray():
    # Patch __init__ to track instances
    original_init = SystemTrayItem.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _tracked_items.add(self)

    SystemTrayItem.__init__ = patched_init

    # Replace the method on the class so all tray items use this logic
    SystemTrayItem.do_update_properties = patched_do_update_properties

    # Setup hot-reload listener
    def on_reload(new_config, old_config):
        if new_config.get("systray_ignore") != old_config.get("systray_ignore"):
            logger.info("[SysTray] Config changed, updating tray item visibility")
            for item_widget in _tracked_items:
                item_widget.do_update_properties()

    on_config_change(on_reload)
