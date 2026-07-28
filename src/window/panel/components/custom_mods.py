from pathlib import Path

import tomlkit
from fabric.utils import Gio, GLib, Gtk, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button

from shared.window.dropdown import ModusDropdown
from utils.functions import clear_children, run_command, thread
from utils.gtk_utils import setup_cursor_hover, svg_file, toml_file

MODS_CONFIG_PATH = Path(toml_file("mods.toml"))
RELOAD_DELAY_MS = 200


class CustomMods(Box):
    def __init__(self, parent_window, **kwargs):
        self._parent = parent_window
        self._monitors = []
        self._reload_pending = False
        self._mods_data = {}
        self._mod_buttons = {}
        self._mod_popups = {}
        super().__init__(name="custom-mods", orientation="h", spacing=0, **kwargs)
        self._load_mods()
        self._setup_monitor()

    def _load_mods(self):
        try:
            if not MODS_CONFIG_PATH.exists():
                return
            with open(MODS_CONFIG_PATH) as f:
                data = tomlkit.load(f)
        except Exception as e:
            logger.error(f"[CustomMods] Failed to parse {MODS_CONFIG_PATH}: {e}")
            return

        mods = {}
        for mod_name, val in data.get("Mods", {}).items():
            icon = val.get("icon", "")
            icon_size = val.get("icon-size", 16)
            order = val.get("order", 99)
            on_clicked = val.get("on-clicked")
            options = val.get("options", [])
            mod_data = {
                "name": mod_name,
                "icon": icon,
                "icon_size": icon_size,
                "order": order,
                "on-clicked": on_clicked,
                "options": options,
            }
            for k in ("on-left", "on-middle", "on-right"):
                v = val.get(k)
                if v is not None:
                    mod_data[k] = v
            mods[mod_name] = mod_data

        self._rebuild(mods)

    def _build_dropdown(self, options, btn):
        menu_items = []
        for opt in sorted(options, key=lambda o: o.get("order", 99)):
            if opt.get("divider"):
                menu_items.append(None)

            cmd = opt["on-clicked"]

            def _on_activate(_, c=cmd):
                thread(run_command, ["sh", "-c", c], timeout=30)

            menu_items.append((opt["label"], _on_activate))

        dropdown = ModusDropdown(items=menu_items)
        return dropdown

    def _on_btn_press(self, btn, event, mod):
        button_map = {1: "on-left", 2: "on-middle", 3: "on-right"}
        button_key = button_map.get(event.button)
        per_button_cmd = mod.get(button_key) if button_key else None
        popup = self._mod_popups.get(mod["name"])

        if per_button_cmd is not None:
            if popup and popup.menu.get_visible():
                popup.menu.popdown()
            thread(run_command, ["sh", "-c", per_button_cmd], timeout=30)
            return True

        cmd = mod.get("on-clicked")
        if cmd:
            if popup and popup.menu.get_visible():
                popup.menu.popdown()
            thread(run_command, ["sh", "-c", cmd], timeout=30)
            return True

        return False

    def _rebuild(self, mods):
        clear_children(self)

        for popup in self._mod_popups.values():
            if popup:
                popup.menu.destroy()
        self._mod_popups.clear()
        self._mod_buttons.clear()
        self._mods_data.clear()

        sorted_mods = sorted(mods.values(), key=lambda m: m.get("order", 99))

        for mod in sorted_mods:
            icon_widget = svg_file(mod["icon"], size=mod["icon_size"])

            if mod["options"]:
                btn = Gtk.MenuButton(name="panel-button", child=icon_widget)
                btn.get_style_context().add_class("flat")
                dropdown = self._build_dropdown(mod["options"], btn)
                btn.set_popup(dropdown.menu)
            else:
                btn = Button(name="panel-button", child=icon_widget)
                btn.get_style_context().add_class("flat")

            btn.set_margin_start(4)
            btn.set_margin_end(4)
            setup_cursor_hover(btn, "pointer")
            btn.connect(
                "button-press-event",
                lambda b, e, m=mod: self._on_btn_press(b, e, m),
            )

            self.add(btn)
            self._mod_buttons[mod["name"]] = btn
            self._mod_popups[mod["name"]] = dropdown if mod["options"] else None
            self._mods_data[mod["name"]] = mod

        self.show_all()

    def _setup_monitor(self):
        try:
            for path in [MODS_CONFIG_PATH, MODS_CONFIG_PATH.parent]:
                if not path.exists():
                    continue
                gio_file = Gio.File.new_for_path(str(path))
                monitor = gio_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
                monitor.connect("changed", self._on_file_changed)
                self._monitors.append(monitor)
        except Exception as e:
            logger.error(f"[CustomMods] Failed to setup monitor: {e}")

    def _on_file_changed(self, monitor, gfile, _other_file, event_type):
        if event_type == Gio.FileMonitorEvent.DELETED and gfile.get_path() == str(
            MODS_CONFIG_PATH
        ):
            self._schedule_reload()
            return
        valid_events = [
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CHANGED,
            Gio.FileMonitorEvent.CREATED,
        ]
        if event_type in valid_events and not self._reload_pending:
            path = gfile.get_path()
            if path and path != str(MODS_CONFIG_PATH):
                return
            self._schedule_reload()

    def _schedule_reload(self):
        self._reload_pending = True
        GLib.timeout_add(RELOAD_DELAY_MS, self._reload_config)

    def _reload_config(self):
        self._reload_pending = False
        self._load_mods()
        return False

    def destroy(self):
        for monitor in self._monitors:
            monitor.cancel()
        for popup in self._mod_popups.values():
            if popup:
                popup.menu.destroy()
        self._mod_popups.clear()
        self._mod_buttons.clear()
        self._mods_data.clear()
        super().destroy()
