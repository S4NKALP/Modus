"""
Simplified System Tray Icon Patch

Focuses on loading icons from absolute file paths and fixing tooltip naming.
"""

from pathlib import Path

from fabric.system_tray.widgets import SystemTrayItem
from fabric.utils import GdkPixbuf, GLib


def patched_do_update_properties(self, *_):
    # Determine the icon name to use
    icon_name = self._item.icon_name
    attention_icon_name = self._item.attention_icon_name

    if self._item.status == "NeedsAttention" and attention_icon_name:
        preferred_icon_name = attention_icon_name
    else:
        preferred_icon_name = icon_name

    # 1. Try the standard fabric/GTK implementation first
    pixbuf = self._item.get_preferred_icon_pixbuf(self._icon_size)

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

    tooltip = self._item.tooltip
    self.set_tooltip_markup(
        tooltip.description
        or tooltip.title
        or (self._item.title.title() if self._item.title else None)
        or "Unknown"
    )


def apply_enhanced_system_tray():
    # Replace the method on the class so all tray items use this logic
    SystemTrayItem.do_update_properties = patched_do_update_properties
