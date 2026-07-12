"""
Enhanced System Tray

Patches icon loading (absolute path support), item filtering, and
hot-reloading of filter config based on `config.json`.
"""

from pathlib import Path

from fabric.system_tray.service import SystemTrayItem as SystemTrayItemService
from fabric.utils import GdkPixbuf, GLib, Gtk, idle_add

import config.data as data
from services.config_watcher import get_all_config, has_config_changed, on_config_change


def _get_filter_from_config(config):
    systray_config = config.get("panel", {}).get("systray", {})
    hide_list = systray_config.get("hide_items", [])
    return set(x.lower() for x in hide_list if isinstance(x, str))


def _should_hide_item(identifier, filter_set, item=None):
    if not filter_set:
        return False

    title = ""
    if item and hasattr(item, "title") and item.title:
        title = item.title

    identifier_str = identifier if identifier else ""

    # Check both title and identifier (case-insensitive for convenience)
    for pattern in filter_set:
        p = pattern.lower()
        if p in title.lower() or p in identifier_str.lower():
            return True
    return False


def apply_enhanced_system_tray(tray_widget):
    """
    Patch the system tray widget for advanced icon fallback, config hot-reloading, and item filtering.
    This handles the case where the tray might not initially own the DBus name.
    """

    # Mark that we've already patched this widget to avoid double-patching
    if hasattr(tray_widget, "_enhanced_applied"):
        return
    tray_widget._enhanced_applied = True

    # Set initial filter FIRST
    initial_config = get_all_config()
    tray_widget._current_filter = _get_filter_from_config(initial_config)
    tray_widget._bypass_filter = False

    if is_debug():
        print(
            f"[Systray] Applying enhanced tray with filter: {tray_widget._current_filter}"
        )

    original_get_preferred_icon_pixbuf = SystemTrayItemService.get_preferred_icon_pixbuf
    original_on_item_added = tray_widget.on_item_added

    def patched_get_preferred_icon_pixbuf(self, size=None, resize_method="bilinear"):
        # enhanced icon selection with theme/path fallback.
        try:
            size = size or 24
            icon_name = self.icon_name
            attention_icon_name = self.attention_icon_name
            preferred_icon_name = (
                attention_icon_name
                if (self.status == "NeedsAttention" and attention_icon_name)
                else icon_name
            )
            preferred_icon_pixmap = self.icon_pixmap

            if preferred_icon_pixmap is None and preferred_icon_name:
                path = Path(preferred_icon_name)
                if path.is_absolute() and path.exists():
                    try:
                        target = size
                        return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                            str(path),
                            target,
                            target,
                            True,
                        )
                    except GLib.GError:
                        return None

            if preferred_icon_name:
                icon_theme = self.icon_theme
                if icon_theme.has_icon(preferred_icon_name):
                    try:
                        pixbuf = icon_theme.load_icon(
                            preferred_icon_name, size, Gtk.IconLookupFlags.FORCE_SIZE
                        )
                        if pixbuf:
                            return pixbuf
                    except Exception as e:
                        print(f"[Systray] Theme icon error: {e}")
            # Fallback to original/default logic
            return original_get_preferred_icon_pixbuf(self, size, resize_method)
        except Exception as e:
            print(f"[Systray] Error in patched_get_preferred_icon_pixbuf: {e}")
            try:
                return original_get_preferred_icon_pixbuf(self, size, resize_method)
            except Exception as fallback_e:
                print(f"[Systray] Fallback also failed: {fallback_e}")
                return None

    SystemTrayItemService.get_preferred_icon_pixbuf = patched_get_preferred_icon_pixbuf

    def patched_on_item_added(watcher_self, item_identifier: str):
        """Intercept item addition to check filter BEFORE widget creation"""
        item = tray_widget._watcher.items.get(item_identifier)
        title = item.title if item and hasattr(item, "title") and item.title else ""
        if is_debug():
            print(
                f"[Systray] on_item_added called for: {item_identifier} (title: '{title}')"
            )
            print(f"[Systray] Current filter: {tray_widget._current_filter}")
            print(
                f"[Systray] Should hide: {_should_hide_item(item_identifier, tray_widget._current_filter, item)}"
            )

        # Check if should be hidden
        if not tray_widget._bypass_filter and _should_hide_item(
            item_identifier, tray_widget._current_filter, item
        ):
            if is_debug():
                print(
                    f"[Systray] ✗ Blocking hidden item at registration: {item_identifier}"
                )

            # Get the item from watcher but don't create widget
            item = tray_widget._watcher.items.get(item_identifier)
            if item:
                # Store None as placeholder to track this hidden item
                tray_widget._items[item_identifier] = None
            return

        if is_debug():
            print(f"[Systray] ✓ Allowing item: {item_identifier}")

        # Item is not hidden, proceed with normal creation
        original_on_item_added(watcher_self, item_identifier)

    tray_widget.on_item_added = patched_on_item_added

    def sync_visibility():
        current_filter = tray_widget._current_filter
        app_names = set()

        if is_debug():
            print("[Systray] === sync_visibility called ===")
            print(f"[Systray] Current filter: {current_filter}")
            print(f"[Systray] Items in _items: {list(tray_widget._items.keys())}")

        for identifier, item_button in list(tray_widget._items.items()):
            item = tray_widget._watcher.items.get(identifier)

            title_name = (
                item.title
                if item and hasattr(item, "title") and item.title
                else identifier.split("/")[-1]
            )
            app_names.add(title_name)

            # Handle None entries (items that were blocked at registration)
            if item_button is None:
                should_hide = _should_hide_item(identifier, current_filter, item)
                if is_debug():
                    print(
                        f"[Systray] Found None entry for {identifier}, should_hide={should_hide}"
                    )

                if not should_hide:
                    # Item should now be visible, need to create it
                    if is_debug():
                        print(
                            f"[Systray] Creating previously hidden item: {identifier}"
                        )
                    # Remove the None placeholder
                    tray_widget._items.pop(identifier)
                    # Trigger normal creation by calling original handler
                    tray_widget._bypass_filter = True
                    original_on_item_added(None, identifier)
                    tray_widget._bypass_filter = False
                continue

            should_hide = _should_hide_item(identifier, current_filter, item)
            is_in_parent = item_button.get_parent() is not None
            should_be_in_parent = not should_hide

            title = item.title if item and hasattr(item, "title") and item.title else ""
            if is_debug():
                print(
                    f"[Systray] {identifier} (title: '{title}'): should_hide={should_hide}, is_in_parent={is_in_parent}"
                )

            if is_in_parent and not should_be_in_parent:
                tray_widget.remove(item_button)
                if is_debug():
                    print(f"[Systray] ✗ Hiding: {identifier}")
            elif not is_in_parent and should_be_in_parent:
                # Re-add to container
                container = tray_widget.get_children()
                if item_button not in container:
                    tray_widget.pack_start(item_button, False, False, 0)
                    item_button.show()
                    if is_debug():
                        print(f"[Systray] ✓ Showing: {identifier}")

        if app_names and is_debug():
            debug_str = ",".join(sorted(app_names))
            print(f"[Systray] Tray app identifiers: {debug_str}")

        tray_widget.queue_resize()
        tray_widget.show_all()
        return False

    def on_config_changed(new_config, old_config):
        if has_config_changed(old_config, new_config, "panel.systray.hide_items"):
            tray_widget._current_filter = _get_filter_from_config(new_config)
            if is_debug():
                print(
                    f"[Systray] Config changed, new filter: {tray_widget._current_filter}"
                )
            idle_add(sync_visibility)

    # Monitor the watcher's 'changed' signal to handle re-registration after acquiring DBus name
    def on_tray_changed(*args):
        """Called when tray items change, including when we take over from another bar"""
        if is_debug():
            print("[Systray] Tray changed event, syncing visibility")
        idle_add(sync_visibility)

    tray_widget._watcher.connect("changed", on_tray_changed)

    # Initial sync and config watching
    idle_add(sync_visibility)
    on_config_change(on_config_changed)

    if is_debug():
        print("[Systray] Enhanced system tray applied successfully")


def is_debug():
    return bool(data.DATA()["debug"])
