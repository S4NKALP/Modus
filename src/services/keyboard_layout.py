from pathlib import Path

import tomlkit
from fabric.core.service import Property, Service, Signal
from fabric.utils import Gio, GLib, logger

import shared.data as data
from services.config import on_config_change
from utils.functions import run_command

HYPRCTL_BIN = "hyprctl"


class KeyboardLayout(Service):
    """Service to manage keyboard layout switching and monitoring via Hyprland."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def get_initial():
        if KeyboardLayout._instance is None:
            KeyboardLayout._instance = KeyboardLayout()
        return KeyboardLayout._instance

    @Signal
    def layout_changed(self, layout: str) -> None:
        """Signal emitted when keyboard layout changes."""

    def __init__(self, **kwargs):
        if getattr(self, "_initialized", False):
            return
        super().__init__(**kwargs)
        self._initialized = True

        self.layout_state_file = Path(data.CACHE_DIR) / "kb_layout.toml"
        self.layout_file = Path(data.CACHE_DIR) / "kb_layout_current.txt"
        self._last_layout = None
        self.layouts = []
        self.current_index = 0

        self._init_layout_config()
        self._start_file_monitor()

        on_config_change(self._on_config_change)

    def _init_layout_config(self):
        config_layouts = data.load_config().get("keyboard_layouts", ["us", "np"])
        state = self._read_state()

        if state:
            self.layouts = state.get("layouts", config_layouts)
            self.current_index = state.get("current_index", 0)
        else:
            self.layouts = config_layouts
            self.current_index = 0
            self._save_state()

        self._apply_layouts_to_hyprland()
        self._apply_current_layout_index()

    def _read_state(self):
        if not self.layout_state_file.exists():
            return None
        try:
            with open(self.layout_state_file, "r") as f:
                data = tomlkit.load(f)
            return dict(data) if data else None
        except Exception as e:
            logger.error(f"[KeyboardLayout] Failed to read state: {e}")
            return None

    def _save_state(self):
        try:
            self.layout_state_file.parent.mkdir(parents=True, exist_ok=True)
            doc = tomlkit.document()
            arr = tomlkit.array()
            for layout in self.layouts:
                arr.append(layout)
            doc["layouts"] = arr
            doc["current_index"] = self.current_index
            with open(self.layout_state_file, "w") as f:
                tomlkit.dump(doc, f)
        except Exception as e:
            logger.error(f"[KeyboardLayout] Failed to save state: {e}")

    def _on_config_change(self, new_config, old_config):
        new_layouts = new_config.get("keyboard_layouts")
        if new_layouts and new_layouts != self.layouts:
            self.layouts = new_layouts
            self._save_state()
            self._apply_layouts_to_hyprland()
            logger.info(f"[KeyboardLayout] Layouts updated from config: {self.layouts}")

    def _start_file_monitor(self):
        if not self.layout_state_file.exists():
            return
        try:
            gio_file = Gio.File.new_for_path(str(self.layout_state_file))
            self._file_monitor = gio_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._file_monitor.connect("changed", self._on_file_changed)
        except Exception as e:
            logger.error(f"[KeyboardLayout] Failed to start file monitor: {e}")

    def _on_file_changed(self, monitor, file, *args):
        GLib.timeout_add(50, self._reload_layout)

    def _reload_layout(self):
        new_layout = self._read_layout()
        if new_layout != self._last_layout:
            self._last_layout = new_layout
            self.emit("layout_changed", new_layout)
        return False

    def _read_layout(self):
        state = self._read_state()
        if state:
            layouts = state.get("layouts", [])
            current_index = state.get("current_index", 0)
            if layouts and 0 <= current_index < len(layouts):
                return layouts[current_index]
        return "us"

    def _write_layout(self, layout: str):
        try:
            self.layout_file.parent.mkdir(parents=True, exist_ok=True)
            self.layout_file.write_text(layout, encoding="utf-8")
        except Exception as e:
            logger.error(f"[KeyboardLayout] Failed writing layout state file: {e}")

    def _apply_layouts_to_hyprland(self):
        if not self.layouts:
            return
        layouts_str = ",".join(self.layouts)
        lua_eval_cmd = f"hl.config({{ input = {{ kb_layout = '{layouts_str}' }} }})"
        run_command(
            [HYPRCTL_BIN, "eval", lua_eval_cmd],
            timeout=2,
        )

    def _apply_current_layout_index(self):
        run_command(
            [HYPRCTL_BIN, "switchxkblayout", "all", str(self.current_index)],
            timeout=2,
        )

    def switch_to_next(self):
        if not self.layouts:
            logger.warning("[KeyboardLayout] No layouts configured, cannot cycle.")
            return False

        self.current_index = (self.current_index + 1) % len(self.layouts)
        new_layout = self.layouts[self.current_index]

        self._apply_current_layout_index()
        self._save_state()
        self._write_layout(new_layout)

        logger.info(
            f"[KeyboardLayout] Switched layout successfully to '{new_layout}' "
            f"(index {self.current_index})"
        )
        return True

    @staticmethod
    def switch_keyboard_layout():
        KeyboardLayout.get_initial().switch_to_next()

    @Property(str, "readable")
    def current_layout(self):
        return self._read_layout()
