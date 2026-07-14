from fabric.utils import Gdk, GLib, Gtk, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.stack import Stack

from services.config import config, on_config_change
from shared.widgets.smooth_switch import SmoothSwitch
from utils.gtk_utils import setup_cursor_hover, svg_file


class SettingsRow(CenterBox):
    def __init__(
        self, label: str, child=None, description: str | None = None, **kwargs
    ):
        label_widget = Label(label=label, name="settings-row-label", h_align="start")

        start_children = [label_widget]
        if description:
            description_widget = Label(
                label=description, name="settings-row-description", h_align="start"
            )
            start_children = [
                Box(
                    orientation="v",
                    spacing=2,
                    children=[label_widget, description_widget],
                )
            ]

        super().__init__(
            name="settings-row",
            start_children=start_children,
            end_children=[child] if child else [],
            **kwargs,
        )
        self.label_widget = label_widget
        if description:
            self.description_widget = description_widget


class SettingsSwitch(SmoothSwitch):
    def __init__(self, config_key: str, **kwargs):
        self.config_key = config_key
        initial_active = config().get(config_key, False)

        super().__init__(
            name="settings-switch",
            active=initial_active,
            on_user_toggle=self.toggle,
            **kwargs,
        )
        setup_cursor_hover(self, "pointer")

        # Sync with external config changes
        on_config_change(self._on_config_change)

    def _on_config_change(self, new_config, old_config):
        if config().has_changed(self.config_key, old_config):
            self.set_active(new_config.get(self.config_key, False))

    def toggle(self, state: bool):
        config().set(self.config_key, state)
        config().save()


class SettingsEntry(Entry):
    def __init__(self, config_key: str, **kwargs):
        self.config_key = config_key
        initial_value = str(config().get(config_key, ""))

        super().__init__(
            name="settings-entry",
            text=initial_value,
            on_activate=self.on_change,
            **kwargs,
        )

        # Sync with external config changes
        on_config_change(self._on_config_change)

    def _on_config_change(self, new_config, old_config):
        if config().has_changed(self.config_key, old_config):
            new_val = str(new_config.get(self.config_key, ""))
            if self.get_text() != new_val:
                self.set_text(new_val)

    def on_change(self, entry, *args):
        value = entry.get_text()
        # Try to convert to int if possible
        try:
            if value.isdigit():
                value = int(value)
        except Exception as e:
            logger.error(f"An error occurred: {e}")

        config().set(self.config_key, value)
        config().save()


class SettingsComboBox(Gtk.ComboBoxText):
    def __init__(self, config_key: str, options: list, **kwargs):
        super().__init__(**kwargs)
        self.set_name("settings-combo")
        self.set_halign(Gtk.Align.END)
        self.config_key = config_key
        self.options = options

        for opt in options:
            self.append_text(opt)

        self._update_from_config()
        self.connect("changed", self.on_change)

        # Sync with external config changes
        on_config_change(self._on_config_change)

    def _update_from_config(self):
        current_val = str(config().get(self.config_key, ""))
        if current_val in self.options:
            self.set_active(self.options.index(current_val))

    def _on_config_change(self, new_config, old_config):
        if config().has_changed(self.config_key, old_config):
            self._update_from_config()

    def on_change(self, combo):
        value = combo.get_active_text()
        if value:
            config().set(self.config_key, value)
            config().save()


class SettingsList(Box):
    """A list of tags that can be added or removed"""

    def __init__(self, config_key: str, **kwargs):
        super().__init__(name="settings-list", orientation="v", spacing=5, **kwargs)
        self.config_key = config_key

        self.list_box = Box(spacing=5, name="settings-list-tags")
        self.entry = Entry(
            name="settings-list-entry",
            placeholder="Add new item...",
            on_activate=self.on_add,
        )

        self.add(self.list_box)
        self.add(self.entry)

        self._update_list()
        on_config_change(self._on_config_change)

    def _on_config_change(self, new_config, old_config):
        if config().has_changed(self.config_key, old_config):
            self._update_list()

    def _update_list(self):
        items = config().get(self.config_key, [])
        if not isinstance(items, list):
            items = []

        # Clear existing tags
        self.list_box.children = []

        for item in items:
            tag = Button(
                name="settings-list-tag",
                child=Box(
                    spacing=5,
                    children=[
                        Label(label=item),
                        Label(label="✕", name="settings-list-tag-close"),
                    ],
                ),
                on_clicked=lambda *_, i=item: self.on_remove(i),
            )
            setup_cursor_hover(tag, "pointer")
            self.list_box.pack_start(tag, False, False, 0)

        self.list_box.show_all()

    def on_add(self, entry):
        val = entry.get_text().strip()
        if not val:
            return

        items = config().get(self.config_key, [])
        if val not in items:
            items.append(val)
            config().set(self.config_key, items)
            config().save()

        entry.set_text("")
        self._update_list()

    def on_remove(self, item):
        items = config().get(self.config_key, [])
        if item in items:
            items.remove(item)
            config().set(self.config_key, items)
            config().save()
        self._update_list()


class SettingsPage(ScrolledWindow):
    def __init__(self, title: str, rows: list, **kwargs):
        container = Box(
            name="settings-page-container",
            orientation="v",
            spacing=10,
            h_expand=True,
            v_expand=True,
            children=[
                Label(label=title, name="settings-page-title", h_align="start"),
                Box(orientation="v", spacing=1, children=rows, h_expand=True),
            ],
        )
        super().__init__(
            name="settings-page",
            h_expand=True,
            v_expand=True,
            propagate_width=True,
            propagate_height=True,
            min_content_width=600,
            min_content_height=500,
            **kwargs,
        )
        self.add(container)
        self.show_all()
        self._container = container


class SettingsWindow(Gtk.Window):
    def __init__(self, **kwargs):
        GLib.set_prgname("modus-settings")
        super().__init__(title="Modus Settings", **kwargs)
        self.set_name("settings-window")
        self.set_title("modus-settings")
        self.set_wmclass("modus-settings", "Modus")
        self.set_default_size(850, 600)
        self.set_resizable(False)
        self.set_type_hint(Gtk.Window.get_type_hint(self) | Gdk.WindowTypeHint.DIALOG)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_visible(False)

        # Reset global singleton on destroy
        self.connect("destroy", self._on_window_destroy)

        self.stack = Stack(
            name="settings-stack",
            transition_type="none",
            h_expand=True,
            v_expand=True,
        )

        self.pages = {
            "general": self._create_general_page(),
            "dock": self._create_dock_page(),
            "panel": self._create_panel_page(),
            "notifications": self._create_notifications_page(),
        }

        for name, page in self.pages.items():
            self.stack.add_named(page, name)

        self.sidebar_buttons = {}
        self.sidebar_buttons["general"] = self._create_sidebar_button(
            "General", "general", "misc/logo.svg"
        )
        self.sidebar_buttons["dock"] = self._create_sidebar_button(
            "Dock", "dock", "misc/control.svg"
        )
        self.sidebar_buttons["panel"] = self._create_sidebar_button(
            "Panel", "panel", "misc/control-center.svg"
        )
        self.sidebar_buttons["notifications"] = self._create_sidebar_button(
            "Notifications", "notifications", "notifications/notification-active.svg"
        )

        self.set_page("general")

        self.sidebar = Box(
            name="settings-sidebar",
            orientation="v",
            spacing=5,
            children=list(self.sidebar_buttons.values()),
        )

        self.main_box = Box(
            name="settings-main-box",
            orientation="h",
            h_expand=True,
            v_expand=True,
            children=[
                self.sidebar,
                Box(
                    name="settings-content-wrapper",
                    children=[self.stack],
                    h_expand=True,
                    v_expand=True,
                ),
            ],
        )

        self.add(self.main_box)

    def _create_sidebar_button(self, label, page_name, icon_name):
        btn = Button(
            name="settings-sidebar-button",
            child=Box(
                orientation="h",
                spacing=10,
                children=[svg_file(icon_name, size=16), Label(label=label)],
            ),
            on_clicked=lambda *_: self.set_page(page_name),
        )
        setup_cursor_hover(btn, "pointer")
        return btn

    def set_page(self, page_name):
        if page_name not in self.pages:
            return
        self.stack.set_visible_child(self.pages[page_name])
        for name, btn in self.sidebar_buttons.items():
            if name == page_name:
                btn.add_style_class("active")
            else:
                btn.remove_style_class("active")

    def _create_general_page(self):
        return SettingsPage(
            "General Settings",
            [
                SettingsRow(
                    "Wallpapers Directory",
                    SettingsEntry("wallpapers_dir"),
                    "Path to your wallpaper collection",
                ),
                SettingsRow(
                    "Weather Location",
                    SettingsEntry("weather_location"),
                    "City name for weather updates",
                ),
                SettingsRow(
                    "Keyboard Layouts",
                    SettingsList("keyboard_layouts"),
                    "Manage active keyboard input languages",
                ),
                SettingsRow(
                    "Window Switcher",
                    SettingsSwitch("window_switcher"),
                    "Enable the Alt-Tab window switcher",
                ),
                SettingsRow(
                    "Items Per Row",
                    SettingsEntry("window_switcher_items_per_row"),
                    "Maximum items in window switcher row",
                ),
                SettingsRow(
                    "Hide Special Workspace",
                    SettingsSwitch("hide_special_workspace"),
                    "Don't show special workspace in indicators",
                ),
                SettingsRow(
                    "OSD",
                    SettingsSwitch("osd"),
                    "On-screen display for volume/brightness",
                ),
            ],
        )

    def _create_dock_page(self):
        return SettingsPage(
            "Dock Settings",
            [
                SettingsRow(
                    "Enabled",
                    SettingsSwitch("dock_enabled"),
                    "Show the application dock",
                ),
                SettingsRow(
                    "Auto Hide",
                    SettingsSwitch("dock_auto_hide"),
                    "Hide dock when not in use",
                ),
                SettingsRow(
                    "Always Occluded",
                    SettingsSwitch("dock_always_occluded"),
                    "Keep dock behind other windows",
                ),
                SettingsRow(
                    "Icon Size",
                    SettingsEntry("dock_icon_size"),
                    "Size of dock icons in pixels",
                ),
                SettingsRow(
                    "Hide Special Apps",
                    SettingsSwitch("dock_hide_special_workspace_apps"),
                    "Hide apps from special workspace in dock",
                ),
            ],
        )

    def _create_panel_page(self):
        # panel visibility settings
        rows = []
        panel_settings = [
            ("iMac Button", "imac_button"),
            ("Global Menu", "global_menu"),
            ("Systray", "systray"),
            ("Control Center", "control_center"),
            ("Search", "search"),
            ("Network", "network"),
            ("Battery", "battery"),
            ("Bluetooth", "bluetooth"),
            ("Date & Time", "date_time"),
            ("Workspace Indicator", "workspace_indicator"),
            ("Notification Center", "notification_center"),
        ]
        for label, key in panel_settings:
            rows.append(SettingsRow(label, SettingsSwitch(key)))

        rows.append(
            SettingsRow(
                "Systray Ignore",
                SettingsList("systray_ignore"),
                "Icons to hide from the system tray",
            )
        )

        return SettingsPage("Panel Settings", rows)

    def _create_notifications_page(self):
        return SettingsPage(
            "Notification Settings",
            [
                SettingsRow(
                    "Timeout",
                    SettingsEntry("notification_timeout"),
                    "How long notifications stay on screen (e.g. 5s)",
                ),
                SettingsRow(
                    "Ignored Apps",
                    SettingsList("notification_ignored_apps"),
                    "Apps that won't show notifications",
                ),
                SettingsRow(
                    "Limited History",
                    SettingsList("notification_limited_apps_history"),
                    "Apps with only the latest notification shown",
                ),
            ],
        )

    def _on_window_destroy(self, *args):
        global _settings_window
        _settings_window = None

    def toggle(self):
        if not self.get_visible():
            self.show_all()
            self.present()

            # Re-sync current page
            current_page = "general"
            for name, btn in self.sidebar_buttons.items():
                if "active" in btn.get_style_context().list_classes():
                    current_page = name
                    break
            self.set_page(current_page)
        else:
            self.hide()


_settings_window = None


def get_settings_window():
    global _settings_window
    if _settings_window is None:
        _settings_window = SettingsWindow()
    return _settings_window
