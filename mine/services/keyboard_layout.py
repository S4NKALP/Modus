from pathlib import Path
from typing import ClassVar, List, Optional

from fabric.core.service import Property, Service, Signal
from fabric.utils import GLib, logger, monitor_file

import config.data as data
from services import on_config_change
from utils.functions import read_json_file, run_command, write_json_file

HYPRCTL_BIN: str = "hyprctl"


class KeyboardLayout(Service):
    """
    Features full compatibility with Hyprland v0.55+ Lua config models:
    - Reads active layout definitions strictly from Modus's config.json.
    - Synchronizes configuration changes seamlessly on runtime events.
    - Leverages `hyprctl eval` for dynamic runtime layout registration.
    - Switches keymaps globally using reliable device indexing.
    """

    _instance: ClassVar[Optional["KeyboardLayout"]] = None

    @Signal
    def layout_changed(self, layout: str) -> None:
        """Signal emitted when keyboard layout changes."""

    def __new__(cls, *args, **kwargs) -> "KeyboardLayout":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_initial(cls) -> "KeyboardLayout":
        """Retrieve the singleton instance of the KeyboardLayout service."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, **kwargs) -> None:
        # Prevent re-initialization if singleton instance is already setup
        if hasattr(self, "_initialized") and self._initialized:
            return
        super().__init__(**kwargs)

        self.layout_file: Path = Path(data.CACHE_DIR) / "kb_layout"
        self.layout_json_file: Path = Path(data.CACHE_DIR) / "kb_layout.json"
        self._last_layout: Optional[str] = None
        self.layouts: List[str] = ["us"]
        self.current_index: int = 0

        self.layout_file.parent.mkdir(parents=True, exist_ok=True)

        self._init_layout_json()
        self._apply_layouts_to_hyprland()

        # Set up state files & monitor
        current = self._read_layout()
        self._write_layout(current)
        self.file_monitor = monitor_file(str(self.layout_file), initial_call=True)
        self.file_monitor.connect("changed", self._on_file_changed)
        self._last_layout = current

        self._apply_current_layout_index()

        on_config_change(self._on_config_change)
        self._initialized: bool = True

    def _on_config_change(self, new_config: dict, old_config: dict) -> None:
        """Handle real-time updates to the shell configuration."""
        old_kb_layout = old_config.get("keyboard_layout", {})
        new_kb_layout = new_config.get("keyboard_layout", {})

        if old_kb_layout.get("layouts") != new_kb_layout.get("layouts"):
            new_layouts = new_kb_layout.get("layouts")
            if new_layouts and new_layouts != self.layouts:
                self.layouts = new_layouts
                self._apply_layouts_to_hyprland()

                current_layout = self._read_layout()
                self.current_index = (
                    self.layouts.index(current_layout)
                    if current_layout in self.layouts
                    else 0
                )
                if self.current_index >= len(self.layouts):
                    self.current_index = 0

                self._save_layout_json()
                self._apply_current_layout_index()
                logger.info(
                    f"[KeyboardLayout] Layouts synced from config: {self.layouts}"
                )

    def _init_layout_json(self) -> None:
        """Initialize layout registry state from cached data or application configuration."""
        config_layouts = data.DATA().get("keyboard_layouts") or ["us", "np"]

        json_data = read_json_file(self.layout_json_file)
        if json_data and isinstance(json_data, dict):
            saved_layouts = json_data.get("layouts", config_layouts)
            self.layouts = (
                config_layouts if saved_layouts != config_layouts else saved_layouts
            )
            self.current_index = json_data.get("current_index", 0)
            if self.current_index >= len(self.layouts):
                self.current_index = 0
        else:
            self.layouts = config_layouts
            self.current_index = 0
            self._save_layout_json()

    def _save_layout_json(self) -> None:
        """Persist current registry layout details to state storage."""
        write_json_file(
            {
                "layouts": self.layouts,
                "current_index": self.current_index,
            },
            self.layout_json_file,
        )

    def _on_file_changed(self, monitor, file, *args) -> bool:
        GLib.timeout_add(50, self._reload_layout)
        return False

    def _reload_layout(self) -> bool:
        """Reload the layout state file and emit event on deviation."""
        new_layout = self._read_layout()
        if new_layout != self._last_layout:
            self._last_layout = new_layout
            self.emit("layout_changed", new_layout)
        return False

    def _read_layout(self) -> str:
        """Safely fetch the active layout from cached JSON state."""
        json_data = read_json_file(self.layout_json_file)
        if json_data and isinstance(json_data, dict):
            layouts = json_data.get("layouts", [])
            current_index = json_data.get("current_index", 0)
            if layouts and 0 <= current_index < len(layouts):
                return layouts[current_index]
        return "us"

    def _write_layout(self, layout: str) -> None:
        """Write current layout selection to raw state files."""
        try:
            self.layout_file.parent.mkdir(parents=True, exist_ok=True)
            self.layout_file.write_text(layout, encoding="utf-8")
        except Exception as e:
            logger.error(f"[KeyboardLayout] Failed writing layout state file: {e}")

    def _apply_layouts_to_hyprland(self) -> None:
        """Configure keyboard layout lists inside the Hyprland state dynamically."""
        if not self.layouts:
            return
        layouts_str = ",".join(self.layouts)
        lua_eval_cmd = f"hl.config({{ input = {{ kb_layout = '{layouts_str}' }} }})"
        run_command(
            [HYPRCTL_BIN, "eval", lua_eval_cmd],
            timeout=2,
        )

    def _apply_current_layout_index(self) -> None:
        """Update active layout index across all connected input devices."""
        run_command(
            [HYPRCTL_BIN, "switchxkblayout", "all", str(self.current_index)],
            timeout=2,
        )

    def switch_to_next(self) -> bool:
        """Cycle forward to the next registered keyboard layout."""
        if not self.layouts:
            logger.warning("[KeyboardLayout] No layouts configured, cannot cycle.")
            return False

        self.current_index = (self.current_index + 1) % len(self.layouts)
        new_layout = self.layouts[self.current_index]

        self._apply_current_layout_index()
        self._save_layout_json()
        self._write_layout(new_layout)

        logger.info(
            f"[KeyboardLayout] Switched layout successfully to '{new_layout}' "
            f"(index {self.current_index})"
        )
        return True

    @Property(str, "readable")
    def current_layout(self) -> str:
        """The currently active keyboard layout code (e.g. 'us', 'np')."""
        return self._read_layout()
