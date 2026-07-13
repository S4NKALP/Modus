"""Hyprland Game Mode service."""

from fabric.core.service import Property, Service, Signal

from utils.functions import run_command

HYPRCTL = "hyprctl"

_ENABLE_LUA = (
    "hl.config({"
    " animations = { enabled = false },"
    " decoration = { shadow = { enabled = false }, blur = { enabled = false },"
    " rounding = 0 },"
    " general = { gaps_in = 0, gaps_out = 0, border_size = 1 }"
    "})"
)


class GameModeService(Service):
    """Owns all Hyprland interaction for game mode and notifies observers."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def get_initial():
        if GameModeService._instance is None:
            GameModeService._instance = GameModeService()
        return GameModeService._instance

    @Signal
    def changed(self, enabled: bool) -> None:
        """Emitted when game mode is enabled or disabled."""

    def __init__(self, **kwargs):
        if getattr(self, "_initialized", False):
            return
        super().__init__(**kwargs)
        self._initialized = True
        self._enabled = False
        self.sync_state()

    @Property(bool, "readable", default_value=False)
    def enabled(self) -> bool:
        """Whether game mode (visual effects off) is currently active."""
        return self._enabled

    def toggle(self) -> None:
        if self._enabled:
            self.disable()
        else:
            self.enable()

    def enable(self) -> None:
        if self._enabled:
            return
        run_command([HYPRCTL, "eval", _ENABLE_LUA], timeout=5)
        self._set_enabled(True)

    def disable(self) -> None:
        if not self._enabled:
            return
        # A full reload restores the user's exact prior configuration (gaps,
        # border, rounding, etc.) which per-option restores cannot reproduce,
        # so it is kept instead of guessing default values.
        run_command([HYPRCTL, "reload"], timeout=5)
        self._set_enabled(False)

    def sync_state(self) -> None:
        """Read the authoritative state from Hyprland (animations toggle)."""
        result = run_command(
            [HYPRCTL, "eval", "return hl.get_config('animations.enabled')"], timeout=5
        )
        if result.returncode != 0:
            return
        value = result.stdout.strip().lower()
        if value in ("true", "1", "on"):
            animations_on = True
        elif value in ("false", "0", "off"):
            animations_on = False
        else:
            # Unrecognized output (e.g. an error string): keep current state
            # rather than falsely reporting game mode as active.
            return
        # Game mode is on when Hyprland animations are disabled.
        self._set_enabled(not animations_on)

    def _set_enabled(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        self._enabled = enabled
        self.notify("enabled")
        self.emit("changed", enabled)
