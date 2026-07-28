import re

from fabric.core.service import Property, Service, Signal
from fabric.utils import Gio, GLib, logger

from services.config import get_config, on_config_change

_CONFIG_KEY = "panel.night_light_temperature"
_DEFAULT_TEMPERATURE = 4500
_NEUTRAL_TEMPERATURE = 6000
_PROFILE_TEMP_RE = re.compile(r"(\d{3,5})")


def _coerce_temperature(value, fallback: int = _DEFAULT_TEMPERATURE) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        logger.warning(f"[nightlight] return int(value) failed: {e}")
        return fallback


class NightLightService(Service):
    """Blue-light filter service backed by a persistent hyprsunset daemon.

    All state changes go through ``hyprctl hyprsunset`` IPC so the daemon is
    started at most once and never respawned on every toggle.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @Signal
    def night_light_changed(self, active: bool) -> None:
        """Emitted when the filter is enabled or disabled."""

    @Signal
    def temperature_changed(self, value: int) -> None:
        """Emitted when the color temperature changes."""

    def __init__(self, **kwargs):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        super().__init__(**kwargs)
        self._active = False
        self._temperature = _coerce_temperature(get_config(_CONFIG_KEY))
        self._process: Gio.Subprocess | None = None
        self._daemon_running = False
        on_config_change(self._on_config_change)
        self._sync_state()

    @Property(bool, "readable", default_value=False)
    def active(self) -> bool:
        return self._active

    @Property(int, "readable", default_value=_DEFAULT_TEMPERATURE)
    def temperature(self) -> int:
        return self._temperature

    def is_active(self) -> bool:
        return self._active

    def enable(self):
        kelvin = self._temperature or _DEFAULT_TEMPERATURE
        if self._daemon_running:
            self._hyprctl("temperature", kelvin)
        else:
            self._start_daemon(["-t", str(kelvin)])
        self._set_temperature(kelvin)
        self._set_active(True)

    def disable(self):
        if self._daemon_running:
            self._hyprctl("identity")
        self._set_active(False)

    def toggle(self) -> bool:
        if self._active:
            self.disable()
        else:
            self.enable()
        return self._active

    def set_temperature(self, kelvin: int):
        self._set_temperature(kelvin)
        if not self._active:
            return
        if self._daemon_running:
            self._hyprctl("temperature", kelvin)
        else:
            self._start_daemon(["-t", str(kelvin)])

    def set_gamma(self, percent: int):
        if self._daemon_running:
            self._hyprctl("gamma", percent)
        else:
            self._start_daemon(["-g", str(percent)])

    def reset(self):
        if self._daemon_running:
            self._hyprctl("reset")
        self._sync_state()

    def _on_config_change(self, new_config, old_config):
        new_panel = new_config.get("panel", {})
        old_panel = old_config.get("panel", {})
        new_temp = new_panel.get("night_light_temperature")
        old_temp = old_panel.get("night_light_temperature")
        if new_temp == old_temp:
            return
        self.set_temperature(_coerce_temperature(new_temp))

    def _set_active(self, value: bool):
        if value != self._active:
            self._active = value
            self.emit("night_light_changed", value)

    def _set_temperature(self, value: int):
        if value != self._temperature:
            self._temperature = value
            self.emit("temperature_changed", value)

    def _start_daemon(self, args: list[str]):
        try:
            self._process = Gio.Subprocess.new(
                ["hyprsunset", *args],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error as error:
            logger.error(f"[NightLightService] Failed to start hyprsunset: {error}")
            self._process = None
            return
        self._daemon_running = True
        self._process.wait_async(None, self._on_daemon_exit)

    def _on_daemon_exit(self, process: Gio.Subprocess, task: Gio.Task):
        # Ignore exit from a stale subprocess — a new daemon may have been
        # started since this one was spawned.
        if self._process is not process:
            return
        self._process = None
        self._daemon_running = False
        self._set_active(False)

    def _hyprctl(self, *args, on_reply=None):
        argv = ["hyprctl", "hyprsunset", *[str(arg) for arg in args]]
        try:
            proc = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error as error:
            logger.error(f"[NightLightService] Failed to run {argv}: {error}")
            if on_reply:
                on_reply(None)
            return

        def on_done(process: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, _ = process.communicate_utf8_finish(task)
            except GLib.Error:
                stdout = None
            if on_reply:
                on_reply(stdout.strip() if stdout else None)

        proc.communicate_utf8_async(None, None, on_done)

    def _sync_state(self):
        self._hyprctl("profile", on_reply=self._on_profile_reply)

    def _on_profile_reply(self, reply: str | None):
        if not self._daemon_alive(reply):
            self._daemon_running = False
            return
        self._daemon_running = True
        temperature = self._parse_temperature(reply)
        if temperature is not None:
            self._apply_synced_temperature(temperature)
        else:
            self._hyprctl("temperature", on_reply=self._on_temperature_reply)

    def _on_temperature_reply(self, reply: str | None):
        if reply is None:
            return
        temperature = self._parse_temperature(reply)
        if temperature is not None:
            self._apply_synced_temperature(temperature)

    def _apply_synced_temperature(self, temperature: int):
        active = temperature < _NEUTRAL_TEMPERATURE
        if active:
            self._set_temperature(temperature)
        self._set_active(active)

    @staticmethod
    def _daemon_alive(reply: str | None) -> bool:
        if reply is None:
            return False
        return "couldn't connect" not in reply.lower()

    @staticmethod
    def _parse_temperature(reply: str | None) -> int | None:
        if not reply:
            return None
        match = _PROFILE_TEMP_RE.search(reply)
        return int(match.group(1)) if match else None


def get_night_light_service() -> NightLightService:
    return NightLightService()
