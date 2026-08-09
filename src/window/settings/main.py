from fabric.utils import Gdk, GLib, Gtk
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.stack import Stack

from services.config import config, off_config_change, on_config_change
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

    def destroy(self):
        off_config_change(self._on_config_change)
        super().destroy()


class SettingsEntry(Entry):
    def __init__(self, config_key: str, **kwargs):
        self.config_key = config_key
        initial_value = str(config().get(config_key, ""))

        super().__init__(
            name="settings-entry",
            text=initial_value,
            **kwargs,
        )
        self.connect("activate", self.on_change)

        # Sync with external config changes
        on_config_change(self._on_config_change)

    def _on_config_change(self, new_config, old_config):
        if config().has_changed(self.config_key, old_config):
            new_val = str(new_config.get(self.config_key, ""))
            if self.get_text() != new_val:
                self.set_text(new_val)

    def on_change(self, entry, *args):
        value = entry.get_text()
        try:
            if value.isdigit():
                value = int(value)
            else:
                value = float(value)
        except (ValueError, TypeError):
            pass

        config().set(self.config_key, value)
        config().save()

    def destroy(self):
        off_config_change(self._on_config_change)
        super().destroy()


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

    def destroy(self):
        off_config_change(self._on_config_change)
        super().destroy()


class SettingsList(Box):
    """A list of tags that can be added or removed"""

    def __init__(self, config_key: str, **kwargs):
        super().__init__(name="settings-list", orientation="v", spacing=5, **kwargs)
        self.config_key = config_key

        self.list_box = Box(spacing=5, name="settings-list-tags")
        self.entry = Entry(
            name="settings-list-entry",
            placeholder="Add new item...",
        )
        self.entry.connect("activate", self.on_add)

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

    def destroy(self):
        off_config_change(self._on_config_change)
        super().destroy()


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
            propagate_height=False,
            min_content_width=600,
            **kwargs,
        )
        self.add(container)
        self.show_all()
        self._container = container


SECTION_ICONS = {
    "general": "misc/logo.svg",
    "dock": "misc/control.svg",
    "panel": "misc/control-center.svg",
    "switcher": "screencapture/window.svg",
    "notification": "notifications/notification-active.svg",
}

DEFAULT_SECTION_ICON = "misc/logo.svg"

ENUM_OPTIONS = {
    "dock.position": ["bottom", "left", "right"],
}


def humanize_key(key):
    return " ".join(word.capitalize() for word in key.replace("_", " ").split())


class SettingsWindow(Gtk.Window):
    def __init__(self, **kwargs):
        super().__init__(title="Modus Settings", **kwargs)
        self.set_name("settings-window")
        self.set_title("modus-settings")
        self.set_wmclass("modus-settings", "Modus")
        self.set_default_size(850, 600)
        self.set_resizable(False)
        self.set_type_hint(Gtk.Window.get_type_hint(self) | Gdk.WindowTypeHint.DIALOG)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_visible(False)

        # Destroy on close so the widget tree is freed; get_settings_window
        # recreates it on next open. Destruction is deferred out of the
        # delete-event emission to avoid tearing the window down mid-signal.
        self.connect("delete-event", self._on_delete_event)
        self.connect("destroy", self._on_window_destroyed)

        self.stack = Stack(
            name="settings-stack",
            transition_type="none",
            h_expand=True,
            v_expand=True,
        )

        self.pages = {}
        self.sidebar_buttons = {}

        for section, values in config().get_all().items():
            if not isinstance(values, dict):
                continue
            self._add_section(section, values)

        self.set_page(next(iter(self.pages)))

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

    def _add_section(self, section, values):
        page = self._build_page(section, values)
        self.pages[section] = page
        self.stack.add_named(page, section)
        self.sidebar_buttons[section] = self._create_sidebar_button(
            humanize_key(section),
            section,
            SECTION_ICONS.get(section, DEFAULT_SECTION_ICON),
        )

    def _build_page(self, section, values):
        rows = []
        for key, value in values.items():
            widget = self._infer_widget(f"{section}.{key}", value)
            rows.append(SettingsRow(humanize_key(key), widget))
        return SettingsPage(f"{humanize_key(section)} Settings", rows)

    def _infer_widget(self, full_key, value):
        if full_key in ENUM_OPTIONS:
            return SettingsComboBox(full_key, ENUM_OPTIONS[full_key])
        if isinstance(value, bool):
            return SettingsSwitch(full_key)
        if isinstance(value, list):
            return SettingsList(full_key)
        return SettingsEntry(full_key)

    def toggle(self):
        if getattr(self, "_destroyed", False):
            # A stale reference (e.g. __main__.settings) outlived this window.
            get_settings_window().toggle()
            return

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

    def _on_delete_event(self, *_):
        GLib.idle_add(self.destroy)
        return True

    def _on_window_destroyed(self, *_):
        global _settings_window
        self._destroyed = True
        if _settings_window is self:
            _settings_window = None


_settings_window = None


def get_settings_window():
    global _settings_window
    if _settings_window is None:
        _settings_window = SettingsWindow()
    return _settings_window
