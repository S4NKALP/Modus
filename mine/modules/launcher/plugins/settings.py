from fabric.utils import Gtk, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label

from config import data as config_data
from modules.launcher.base import LauncherPlugin


class SettingsPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "settings"

    @property
    def icon(self) -> str:
        return "emblem-system-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["settings", "set"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self._settings_items: list[dict] = []

    def on_search(self, text: str) -> None:
        self.query_settings(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
        self._query_handler = 0

    def query_settings(self, text: str) -> None:
        self.handler.start("settings")
        self._settings_items = self._get_all_settings()

        filtered = (
            self._settings_items
            if not text.strip()
            else [i for i in self._settings_items if text.lower() in i["name"].lower()]
        )

        if not filtered:
            return

        self._query_handler = idle_add(self._bake_settings, iter(filtered), pin=True)

    def _get_all_settings(self) -> list[dict]:
        config = config_data.DATA()
        systray_hide_icons = config.get("systray_hide_icons", [])
        # Convert list to comma-separated string for display
        systray_hide_icons_str = (
            ", ".join(systray_hide_icons)
            if isinstance(systray_hide_icons, list)
            else str(systray_hide_icons)
        )
        return [
            {
                "name": "OSD",
                "key": "osd",
                "type": "switch",
                "value": config.get("osd", True),
            },
            {
                "name": "OSD Position",
                "key": "osd_position",
                "type": "select",
                "options": ["top", "bottom"],
                "value": config.get("osd_position", "bottom"),
            },
            {
                "name": "OSD Audio",
                "key": "osd_audio",
                "type": "switch",
                "value": config.get("osd_audio", True),
            },
            {
                "name": "OSD Brightness",
                "key": "osd_brightness",
                "type": "switch",
                "value": config.get("osd_brightness", True),
            },
            {
                "name": "OSD Capslock",
                "key": "osd_capslock",
                "type": "switch",
                "value": config.get("osd_capslock", True),
            },
            {
                "name": "OSD Keyboard Layout",
                "key": "osd_kb_layout",
                "type": "switch",
                "value": config.get("osd_kb_layout", True),
            },
            {
                "name": "OSD Network",
                "key": "osd_network",
                "type": "switch",
                "value": config.get("osd_network", True),
            },
            {
                "name": "OSD Microphone",
                "key": "osd_microphone",
                "type": "switch",
                "value": config.get("osd_microphone", True),
            },
            {
                "name": "OSD Battery",
                "key": "osd_battery",
                "type": "switch",
                "value": config.get("osd_battery", True),
            },
            {
                "name": "Panel",
                "key": "panel_enabled",
                "type": "switch",
                "value": config.get("panel_enabled", True),
            },
            {
                "name": "Panel Position",
                "key": "panel_position",
                "type": "select",
                "options": ["top", "bottom"],
                "value": config.get("panel_position", "top"),
            },
            {
                "name": "Panel Autohide",
                "key": "panel_autohide",
                "type": "switch",
                "value": config.get("panel_autohide", True),
            },
            {
                "name": "Systray",
                "key": "systray",
                "type": "switch",
                "value": config.get("systray", True),
            },
            {
                "name": "Network",
                "key": "network",
                "type": "switch",
                "value": config.get("network", True),
            },
            {
                "name": "Bluetooth",
                "key": "bluetooth",
                "type": "switch",
                "value": config.get("bluetooth", True),
            },
            {
                "name": "DateTime",
                "key": "datetime",
                "type": "switch",
                "value": config.get("datetime", True),
            },
            {
                "name": "DateTime 12hrs",
                "key": "datetime_12hrs",
                "type": "switch",
                "value": config.get("datetime_12hrs", True),
            },
            {
                "name": "Battery",
                "key": "battery",
                "type": "switch",
                "value": config.get("battery", True),
            },
            {
                "name": "Battery Label",
                "key": "battery_label",
                "type": "switch",
                "value": config.get("battery_label", True),
            },
            {
                "name": "Battery Hide Full",
                "key": "battery_hide_on_full",
                "type": "switch",
                "value": config.get("battery_hide_on_full", True),
            },
            {
                "name": "Workspace",
                "key": "workspace",
                "type": "switch",
                "value": config.get("workspace", True),
            },
            {
                "name": "Workspace Hide Special",
                "key": "workspace_hide_special",
                "type": "switch",
                "value": config.get("workspace_hide_special", True),
            },
            {
                "name": "Taskbar",
                "key": "taskbar",
                "type": "switch",
                "value": config.get("taskbar", True),
            },
            {
                "name": "Taskbar Hide Empty",
                "key": "taskbar_hide_empty",
                "type": "switch",
                "value": config.get("taskbar_hide_empty", True),
            },
            {
                "name": "Notifications",
                "key": "notifications",
                "type": "switch",
                "value": config.get("notifications", True),
            },
            {
                "name": "Desktop Widget",
                "key": "desktop_widget_enabled",
                "type": "switch",
                "value": config.get("desktop_widget_enabled", True),
            },
            {
                "name": "Desktop Widget Time",
                "key": "desktop_widget_time_format",
                "type": "select",
                "options": ["12 hrs", "24 hrs"],
                "value": config.get("desktop_widget_time_format", "12 hrs"),
            },
            {
                "name": "Corners",
                "key": "corners",
                "type": "switch",
                "value": config.get("corners", True),
            },
            {
                "name": "Debug",
                "key": "debug",
                "type": "switch",
                "value": config.get("debug", True),
            },
            {
                "name": "Wallpaper Path",
                "key": "wallpaper_dir",
                "type": "entry",
                "value": config.get("wallpaper_dir", ""),
            },
            {
                "name": "Systray Hide Items",
                "key": "systray_hide_icons",
                "type": "entry",
                "value": systray_hide_icons_str,
            },
        ]

    def _bake_settings(self, iterator) -> bool:
        item = next(iterator, None)
        if item is None:
            self.handler.done()
            return False
        self._create_setting_slot(item)
        return True

    def _create_setting_slot(self, item: dict) -> None:
        # For all types, put label on left and control on right
        if item["type"] == "switch":
            # Left side: label
            name_label = Label(label=item["name"])

            # Right side: switch
            switch = Gtk.Switch()
            switch.set_active(item["value"])
            switch.connect("state-set", self._on_switch_toggled, item)
            switch.show()

            content = Box(
                orientation="h",
                spacing=12,
                children=[
                    name_label,
                    switch,
                ],
            )

            slot = Button(
                style_classes="app-slot settings-slot",
                child=content,
                on_clicked=lambda *_: switch.set_active(not switch.get_active()),
            )
        elif item["type"] == "select":
            # Left side: label with colon
            name_label = Label(label=f"{item['name']}: ")

            # Right side: entry for editing (always visible)
            value_text = item["options"][item["options"].index(item["value"])]
            entry = Entry(
                h_expand=True,
                stop_propagation=False,
            )
            entry.set_text(value_text)
            entry.connect("focus-out-event", self._on_entry_focus_out, item)
            entry.connect("activate", self._on_entry_activate, item)
            entry.connect("key-press-event", self._on_entry_key_press, item)
            # Store reference for updating
            item["_entry_ref"] = entry

            content = Box(
                orientation="h",
                spacing=12,
                children=[
                    name_label,
                    entry,
                ],
            )

            # Create button that focuses the entry when clicked
            def _focus_entry(button):
                entry.grab_focus()
                entry.select_region(0, -1)  # Select all text

            slot = Button(
                style_classes="app-slot settings-slot",
                child=content,
                on_clicked=_focus_entry,
            )
        else:  # entry type (text input)
            # Left side: label with colon
            name_label = Label(label=f"{item['name']}: ")

            # Right side: entry for editing (always visible)
            entry = Entry(
                h_expand=True,
                stop_propagation=False,
            )
            entry.set_text(item["value"])
            entry.connect("focus-out-event", self._on_entry_focus_out, item)
            entry.connect("activate", self._on_entry_activate, item)
            entry.connect("key-press-event", self._on_entry_key_press, item)
            # Store reference for updating
            item["_entry_ref"] = entry

            content = Box(
                orientation="h",
                spacing=12,
                children=[
                    name_label,
                    entry,
                ],
            )

            # Create button that focuses the entry when clicked
            def _focus_entry(button):
                entry.grab_focus()
                entry.select_region(0, -1)  # Select all text

            slot = Button(
                style_classes="app-slot settings-slot",
                child=content,
                on_clicked=_focus_entry,
            )

        self.handler.slot_ready(slot, "settings")

    def _on_switch_toggled(self, switch: Gtk.Switch, state, item: dict) -> None:
        new_value = switch.get_active()
        item["value"] = new_value

        def do_update():
            config_data.update_setting(item["key"], new_value)
            return False

        idle_add(do_update)

    def _on_entry_activate(self, entry, item: dict) -> None:
        """Handle Enter key press in entry"""
        new_value = entry.get_text().strip()

        # For select type, validate against options
        if item["type"] == "select" and new_value not in item["options"]:
            # Reset to current value if invalid
            entry.set_text(item["value"])
            return

        # For systray_hide_icons, convert comma-separated string to list
        if item["key"] == "systray_hide_icons":
            # Split by comma and strip whitespace from each item
            new_value = [item.strip() for item in new_value.split(",") if item.strip()]
        else:
            item["value"] = new_value

        item["value"] = new_value

        def do_update():
            config_data.update_setting(item["key"], new_value)
            return False

        idle_add(do_update)

        # Remove focus from entry after saving by focusing parent button
        def unfocus_entry():
            try:
                parent_box = entry.get_parent()
                if parent_box:
                    parent_button = parent_box.get_parent()
                    if parent_button and hasattr(parent_button, "grab_focus"):
                        parent_button.grab_focus()
            except Exception:
                pass  # Ignore errors in unfocusing
            return False

        idle_add(unfocus_entry)

    def _on_entry_focus_out(self, entry, event, item: dict) -> None:
        """Handle focus out event (when user clicks away)"""
        new_value = entry.get_text().strip()

        # For select type, validate against options
        if item["type"] == "select" and new_value not in item["options"]:
            # Reset to current value if invalid
            entry.set_text(item["value"])
            return

        # For systray_hide_icons, convert comma-separated string to list
        if item["key"] == "systray_hide_icons":
            # Split by comma and strip whitespace from each item
            new_value = [item.strip() for item in new_value.split(",") if item.strip()]
        else:
            item["value"] = new_value

        item["value"] = new_value

        def do_update():
            config_data.update_setting(item["key"], new_value)
            return False

        idle_add(do_update)

    def _on_entry_key_press(self, entry, event, item: dict) -> None:
        """Handle key press events - Escape to cancel"""
        # Escape key resets to current value
        if event.keyval == 65307:  # GDK_KEY_Escape
            entry.set_text(item["value"])
            return True  # Prevent further processing
        return False  # Allow other keys to be processed

    def handle_external(self, command: str, args: str) -> None:
        pass
