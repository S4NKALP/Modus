"""
Enhanced System Tray Icon Handling

This module provides enhanced icon loading capabilities for system tray items,
including fallback mechanisms for file paths and common icon locations.
"""

import os
from gi.repository import Gtk, GdkPixbuf
from fabric.system_tray.widgets import SystemTrayItem


def patched_do_update_properties(self, *_):
    # Try default GTK theme first
    icon_name = self._item.icon_name
    attention_icon_name = self._item.attention_icon_name

    if self._item.status == "NeedsAttention" and attention_icon_name:
        preferred_icon_name = attention_icon_name
    else:
        preferred_icon_name = icon_name

    # Try to load from default GTK theme
    if preferred_icon_name:
        try:
            default_theme = Gtk.IconTheme.get_default()
            if default_theme.has_icon(preferred_icon_name):
                pixbuf = default_theme.load_icon(
                    preferred_icon_name, self._icon_size, Gtk.IconLookupFlags.FORCE_SIZE
                )
                if pixbuf:
                    self._image.set_from_pixbuf(pixbuf)
                    # Set tooltip
                    tooltip = self._item.tooltip
                    self.set_tooltip_markup(
                        tooltip.description or tooltip.title or self._item.title.title()
                        if self._item.title
                        else "Unknown"
                    )
                    return
        except:
            pass

        # Enhanced fallback handling for file paths
        if preferred_icon_name and self._try_load_icon_from_path(preferred_icon_name):
            return

    # Fallback to original implementation
    original_do_update_properties(self, *_)


def _try_load_icon_from_path(self, icon_path):
    try:
        # Check if it's a file path and handle it directly
        if os.path.isabs(icon_path) or "/" in icon_path:
            # Try to load as SVG from the original path if it exists
            if os.path.exists(icon_path):
                if icon_path.lower().endswith(".svg"):
                    # Load SVG directly
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        icon_path, self._icon_size, self._icon_size
                    )
                    if pixbuf:
                        self._image.set_from_pixbuf(pixbuf)
                        self._set_tooltip()
                        return True
                else:
                    # Load other image formats
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        icon_path, self._icon_size, self._icon_size
                    )
                    if pixbuf:
                        self._image.set_from_pixbuf(pixbuf)
                        self._set_tooltip()
                        return True

            # If it's a file path, try to extract just the filename for theme lookup
            filename = os.path.basename(icon_path)
            if filename:
                # Remove extension for theme lookup
                name_without_ext = os.path.splitext(filename)[0]
                default_theme = Gtk.IconTheme.get_default()

                # Try filename without extension
                if default_theme.has_icon(name_without_ext):
                    pixbuf = default_theme.load_icon(
                        name_without_ext,
                        self._icon_size,
                        Gtk.IconLookupFlags.FORCE_SIZE,
                    )
                    if pixbuf:
                        self._image.set_from_pixbuf(pixbuf)
                        self._set_tooltip()
                        return True

                # Try full filename
                if default_theme.has_icon(filename):
                    pixbuf = default_theme.load_icon(
                        filename, self._icon_size, Gtk.IconLookupFlags.FORCE_SIZE
                    )
                    if pixbuf:
                        self._image.set_from_pixbuf(pixbuf)
                        self._set_tooltip()
                        return True

            # If it looks like a file path but doesn't exist, try common icon locations
            if os.path.isabs(icon_path):
                common_icon_dirs = [
                    "/usr/share/icons",
                    "/usr/share/pixmaps",
                    "/usr/local/share/icons",
                    "/usr/local/share/pixmaps",
                    os.path.expanduser("~/.local/share/icons"),
                    os.path.expanduser("~/.icons"),
                ]

                filename = os.path.basename(icon_path)
                for icon_dir in common_icon_dirs:
                    potential_path = os.path.join(icon_dir, filename)
                    if os.path.exists(potential_path):
                        try:
                            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                                potential_path, self._icon_size, self._icon_size
                            )
                            if pixbuf:
                                self._image.set_from_pixbuf(pixbuf)
                                self._set_tooltip()
                                return True
                        except:
                            continue

    except Exception:
        pass

    return False


def _set_tooltip(self):
    tooltip = self._item.tooltip
    self.set_tooltip_markup(
        tooltip.description or tooltip.title or self._item.title.title()
        if self._item.title
        else "Unknown"
    )


def apply_enhanced_system_tray():
    # Store original method
    global original_do_update_properties
    original_do_update_properties = SystemTrayItem.do_update_properties

    # Attach helper methods to SystemTrayItem class
    SystemTrayItem._try_load_icon_from_path = _try_load_icon_from_path
    SystemTrayItem._set_tooltip = _set_tooltip

    # Replace the do_update_properties method
    SystemTrayItem.do_update_properties = patched_do_update_properties


# Store reference to original method
original_do_update_properties = None
