from pathlib import Path

import tomlkit
from fabric.utils import Gio, GLib, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from shared.window.applet_window import AppletWindow
from utils.functions import clear_children, run_command, thread
from utils.gtk_utils import setup_cursor_hover, svg_file, toml_file

MODS_CONFIG_PATH = Path(toml_file("mods.toml"))
RELOAD_DELAY_MS = 200


def dropdown_divider():
    return Box(
        children=[Box(name="dropdown-divider", h_expand=True)],
        name="dropdown-divider-box",
        h_align="fill",
        h_expand=True,
    )


class ModPopup(AppletWindow):
    def __init__(
        self, mod_name, options, parent_window, pointing_to, source_button, **kwargs
    ):
        self._mod_name = mod_name
        self._source_button = source_button

        option_widgets = []
        for opt in sorted(options, key=lambda o: o.get("order", 99)):
            if opt.get("divider"):
                option_widgets.append(dropdown_divider())

            btn = Button(
                name="dropdown-option",
                child=Label(label=opt["label"], name="dropdown-option-label"),
                h_align="fill",
                h_expand=True,
            )
            cmd = opt["on-clicked"]
            btn.connect("clicked", lambda *_, c=cmd: self._run_command(c))
            setup_cursor_hover(btn, "pointer")
            option_widgets.append(btn)

        options_box = Box(
            name="dropdown-options",
            orientation="vertical",
            spacing=0,
            children=option_widgets,
        )

        main_box = Box(name="dropdown-menu", children=[options_box])

        super().__init__(
            parent=parent_window,
            pointing_to=pointing_to,
            name="dropdown-menu",
            title="modus-dropdown",
            layer="overlay",
            visible=False,
            **kwargs,
        )
        self.children = [main_box]
        self.connect("notify::visible", self._on_visible_changed)

    def _on_visible_changed(self, *_):
        if self.get_visible():
            self._source_button.add_style_class("active")
        else:
            self._source_button.remove_style_class("active")

    def _run_command(self, cmd):
        self.close_applet()
        thread(run_command, ["sh", "-c", cmd], timeout=30)

    def toggle(self, pointing_to=None):
        if pointing_to:
            self.set_pointing_to(pointing_to)
        super().toggle()


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

    def _on_btn_press(self, btn, event, mod):
        button_map = {1: "on-left", 2: "on-middle", 3: "on-right"}
        button_key = button_map.get(event.button)
        per_button_cmd = mod.get(button_key) if button_key else None
        popup = self._mod_popups.get(mod["name"])

        if per_button_cmd is not None:
            if popup and popup._is_open:
                popup.toggle()
            thread(run_command, ["sh", "-c", per_button_cmd], timeout=30)
            return True

        cmd = mod.get("on-clicked")
        if cmd:
            if popup and popup._is_open:
                popup.toggle()
            thread(run_command, ["sh", "-c", cmd], timeout=30)
            return True

        if event.button == 3:
            if popup:
                popup.toggle(pointing_to=btn)
            return True

        if event.button == 1:
            if popup and popup._is_open:
                popup.toggle()
                return True

            if popup:
                popup.toggle(pointing_to=btn)
            return True

        if event.button == 2 and popup:
            popup.toggle(pointing_to=btn)

        return True

    def _rebuild(self, mods):
        clear_children(self)

        for popup in self._mod_popups.values():
            if popup:
                popup.destroy()
        self._mod_popups.clear()
        self._mod_buttons.clear()
        self._mods_data.clear()

        sorted_mods = sorted(mods.values(), key=lambda m: m.get("order", 99))

        for mod in sorted_mods:
            icon_widget = svg_file(mod["icon"], size=mod["icon_size"])
            btn = Button(name="global-menu", child=icon_widget)
            setup_cursor_hover(btn, "pointer")

            popup = None
            if mod["options"]:
                popup = ModPopup(
                    mod_name=mod["name"],
                    options=mod["options"],
                    parent_window=self._parent,
                    pointing_to=btn,
                    source_button=btn,
                )

            btn.connect(
                "button-press-event",
                lambda b, e, m=mod: self._on_btn_press(b, e, m),
            )

            self.add(btn)
            self._mod_buttons[mod["name"]] = btn
            self._mod_popups[mod["name"]] = popup
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
                popup.destroy()
        self._mod_popups.clear()
        self._mod_buttons.clear()
        self._mods_data.clear()
        super().destroy()
