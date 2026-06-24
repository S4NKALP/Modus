import json
import socket
import threading
from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import GLib, logger, os

import shared.data as data
from services.config import on_config_change
from utils.functions import read_json_file, run_command, write_json_file

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

        self.layout_json_file = Path(data.CACHE_DIR) / "kb_layout.json"
        self._last_layout = None
        self.layouts = []
        self.current_index = 0

        self._init_layout_config()
        self._start_event_listener()

        on_config_change(self._on_config_change)

    def _init_layout_config(self):
        config_layouts = data.load_config().get("keyboard_layouts", ["us", "np"])
        json_data = read_json_file(self.layout_json_file)

        if json_data:
            self.layouts = json_data.get("layouts", config_layouts)
            self.current_index = json_data.get("current_index", 0)
        else:
            self.layouts = config_layouts
            self.current_index = 0
            self._save_layout_json()

        # Sync with actual Hyprland state
        self._sync_with_hyprland()

    def _sync_with_hyprland(self):
        try:
            result = run_command([HYPRCTL_BIN, "devices", "-j"])
            devices = json.loads(result.stdout)
            keyboards = devices.get("keyboards", [])
            for k in keyboards:
                if k.get("main"):
                    layout_name = k.get("active_keymap")
                    if layout_name:
                        self._last_layout = layout_name
                        # Try to match with our list to update index
                        for i, layout_item in enumerate(self.layouts):
                            if layout_item.lower() in layout_name.lower():
                                self.current_index = i
                                break
                    break
        except Exception as e:
            logger.error(f"[KeyboardLayout] Sync error: {e}")

    def _save_layout_json(self):
        write_json_file(
            {
                "layouts": self.layouts,
                "current_index": self.current_index,
            },
            self.layout_json_file,
        )

    def _on_config_change(self, new_config, old_config):
        new_layouts = new_config.get("keyboard_layouts")
        if new_layouts and new_layouts != self.layouts:
            self.layouts = new_layouts
            self._save_layout_json()
            logger.info(f"[KeyboardLayout] Layouts updated from config: {self.layouts}")

    def _start_event_listener(self):
        """Start a thread to listen for Hyprland layout events."""
        thread = threading.Thread(target=self._event_loop, daemon=True)
        thread.start()

    def _event_loop(self):
        his = os.getenv("HYPRLAND_INSTANCE_SIGNATURE")
        xdg_runtime_dir = os.getenv("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        socket_path = f"{xdg_runtime_dir}/hypr/{his}/.socket2.sock"

        if not os.path.exists(socket_path):
            logger.error(f"[KeyboardLayout] Hyprland socket not found: {socket_path}")
            return

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(socket_path)
                logger.info("[KeyboardLayout] Connected to Hyprland event socket.")
                while True:
                    data = s.recv(1024).decode("utf-8")
                    if not data:
                        break
                    for line in data.split("\n"):
                        if line.startswith("activelayout>>"):
                            # Format: activelayout>>keyboardname,layoutname
                            parts = line.split(">>")[1].split(",")
                            if len(parts) >= 2:
                                layout_name = parts[1]
                                if layout_name != self._last_layout:
                                    self._last_layout = layout_name
                                    GLib.idle_add(
                                        self.emit, "layout_changed", layout_name
                                    )
        except Exception as e:
            logger.error(f"[KeyboardLayout] Event listener error: {e}")

    def switch_to_next(self) -> bool:
        if not self.layouts:
            return False

        self.current_index = (self.current_index + 1) % len(self.layouts)
        self.layouts[self.current_index]

        # Use hyprctl to switch layout for all devices
        # We assume the layouts in Hyprland config match self.layouts in order
        run_command([HYPRCTL_BIN, "switchxkblayout", "all", "next"])

        self._save_layout_json()
        return True

    @Property(str, "readable")
    def current_layout(self) -> str:
        return self._last_layout or "Unknown"
