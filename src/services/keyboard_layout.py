import json

from fabric.core.service import Property, Service, Signal
from fabric.hyprland.service import Hyprland
from fabric.utils import Gio, GLib, logger

from services.config import get_config, on_config_change

HYPRCTL_BIN = "hyprctl"
DEFAULT_LAYOUTS = ["us", "np"]


class KeyboardLayout(Service):
    """In-memory service that treats Hyprland as the source of truth for the
    active keyboard layout. All runtime state lives in memory; Hyprland is
    queried/synced via hyprctl and kept in sync through its event socket."""

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
        """Signal emitted when the active keyboard layout changes."""

    def __init__(self, **kwargs):
        if getattr(self, "_initialized", False):
            return
        super().__init__(**kwargs)
        self._initialized = True

        self._layouts: list[str] = []
        self._current_index: int = 0
        self._current_layout: str | None = None
        self._sync_pending: bool = False

        self._init_layout_config()
        self._connect_hyprland_events()
        on_config_change(self._on_config_change)

    # hyprctl wrapper

    def _hyprctl(self, *args, on_reply=None):
        """Execute a hyprctl command via Gio.Subprocess.

        Every hyprctl invocation goes through here. The call is asynchronous and
        never blocks the UI. ``on_reply`` (optional) receives the stripped stdout
        string, or ``None`` on failure.
        """
        argv = [HYPRCTL_BIN, *[str(arg) for arg in args]]
        try:
            proc = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error as error:
            logger.error(f"[KeyboardLayout] Failed to run {argv}: {error}")
            if on_reply is not None:
                on_reply(None)
            return

        def on_done(process: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, _ = process.communicate_utf8_finish(task)
            except GLib.Error:
                stdout = None
            if on_reply is not None:
                on_reply(stdout.strip() if stdout else None)

        proc.communicate_utf8_async(None, None, on_done)

    # initialization

    def _init_layout_config(self):
        self._layouts = self._load_layouts_from_config()

        if not self._layouts:
            logger.warning("[KeyboardLayout] No keyboard layouts configured.")
            return

        self._apply_layouts_to_hyprland()
        self._sync_from_hyprland()

        if self._current_layout is None:
            self._set_current(0, emit=False)

    def _load_layouts_from_config(self) -> list[str]:
        layouts = get_config("keyboard_layouts", DEFAULT_LAYOUTS)
        if not isinstance(layouts, list) or not layouts:
            return list(DEFAULT_LAYOUTS)
        return [str(layout).strip() for layout in layouts if str(layout).strip()]

    # Hyprland synchronization

    def _sync_from_hyprland(self):
        """Query Hyprland for the current layout and update in-memory state.

        Prefers the ``active_layout_index`` reported by ``hyprctl -j devices``,
        falling back to index 0 when the information is unavailable.
        """
        if self._sync_pending:
            return
        self._sync_pending = True

        def on_reply(stdout: str | None):
            self._sync_pending = False
            if not stdout:
                return
            try:
                devices = json.loads(stdout)
            except json.JSONDecodeError as error:
                logger.error(f"[KeyboardLayout] Failed to parse devices: {error}")
                return

            keyboard = self._pick_keyboard(devices.get("keyboards", []))
            if keyboard is None:
                return

            index = keyboard.get("active_layout_index", 0)
            self._set_current(index, emit=True)

        self._hyprctl("-j", "devices", on_reply=on_reply)

    @staticmethod
    def _pick_keyboard(keyboards: list[dict]) -> dict | None:
        if not keyboards:
            return None
        for kb in keyboards:
            if kb.get("main"):
                return kb
        return keyboards[0]

    def _connect_hyprland_events(self):
        try:
            Hyprland().connect("event::activelayout", self._on_hyprland_layout_event)
        except Exception as error:
            logger.warning(
                f"[KeyboardLayout] Could not subscribe to Hyprland layout "
                f"events (external changes won't be tracked): {error}"
            )

    def _on_hyprland_layout_event(self, _hyprland, _event):
        self._sync_from_hyprland()

    # state management

    def _set_current(self, index: int, emit: bool) -> bool:
        if not self._layouts:
            return False

        index = max(0, min(index, len(self._layouts) - 1))
        layout = self._layouts[index]

        if index == self._current_index and layout == self._current_layout:
            return False

        self._current_index = index
        self._current_layout = layout
        self.notify("current_layout", "current_index", "layouts")

        if emit:
            self.emit("layout_changed", layout)
        return True

    # Hyprland writes

    def _apply_layouts_to_hyprland(self):
        if not self._layouts:
            return
        layouts_str = ",".join(self._layouts)
        lua_eval_cmd = f"hl.config({{ input = {{ kb_layout = '{layouts_str}' }} }})"
        self._hyprctl("eval", lua_eval_cmd)

    # public API

    def switch_to_next(self) -> bool:
        if not self._layouts:
            logger.warning("[KeyboardLayout] No layouts configured, cannot cycle.")
            return False

        next_index = (self._current_index + 1) % len(self._layouts)
        self._hyprctl("switchxkblayout", "all", str(next_index))
        self._set_current(next_index, emit=True)
        return True

    @staticmethod
    def switch_keyboard_layout():
        KeyboardLayout.get_initial().switch_to_next()

    # config changes

    def _on_config_change(self, new_config, old_config):
        new_layouts = new_config.get("keyboard_layouts")
        if not isinstance(new_layouts, list) or not new_layouts:
            return
        new_layouts = [str(item).strip() for item in new_layouts if str(item).strip()]
        if new_layouts == self._layouts:
            return

        previous_layout = self._current_layout
        self._layouts = new_layouts
        self._apply_layouts_to_hyprland()

        preserved_index = (
            self._layouts.index(previous_layout)
            if previous_layout in self._layouts
            else 0
        )
        self._hyprctl("switchxkblayout", "all", str(preserved_index))
        self._set_current(preserved_index, emit=True)

        logger.info(f"[KeyboardLayout] Layouts updated from config: {self._layouts}")

    # properties

    @Property(str, "readable", default_value="")
    def current_layout(self) -> str:
        return self._current_layout or ""

    @Property(list, "readable")
    def layouts(self) -> list[str]:
        return self._layouts

    @Property(int, "readable", default_value=0)
    def current_index(self) -> int:
        return self._current_index
