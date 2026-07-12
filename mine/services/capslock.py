from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import GLib, logger

# Discover CapsLock LED device
capslock_leds = list(Path("/sys/class/leds").glob("input*::capslock"))
capslock_device = capslock_leds[0] if capslock_leds else None


class CapsLock(Service):
    instance = None

    @staticmethod
    def get_initial():
        if CapsLock.instance is None:
            CapsLock.instance = CapsLock()

        return CapsLock.instance

    @Signal
    def state_changed(self, is_on: bool) -> None:
        """Signal emitted when CapsLock state changes."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.capslock_led_path = capslock_device
        self._timeout_id = None
        self._last_state = None

        if capslock_device is None:
            logger.warning("CapsLock device not found, CapsLock service disabled")

    def _start_polling(self):
        """Poll CapsLock LED at 500ms interval (lightweight file read)."""
        if self._timeout_id is None:
            self._timeout_id = GLib.timeout_add(500, self._poll)

    def _poll(self) -> bool:
        try:
            current_state = self._get_current_state()
            if current_state != self._last_state:
                self._last_state = current_state
                self.emit("state_changed", current_state)
        except Exception as e:
            logger.error(f"CapsLock polling error: {e}")
            self._timeout_id = None
            return False

        return True

    def stop(self):
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

    def _ensure_monitoring_started(self):
        if self._last_state is not None:
            return
        if not self.capslock_led_path:
            return

        self._last_state = self._get_current_state()
        self._start_polling()

    def _get_current_state(self) -> bool:
        if not self.capslock_led_path:
            return False
        brightness_path = self.capslock_led_path / "brightness"
        if brightness_path.exists():
            try:
                return bool(int(brightness_path.read_text().strip()))
            except (ValueError, OSError):
                return False
        return False

    @Property(bool, "read-write", default_value=False)
    def is_on(self) -> bool:
        self._ensure_monitoring_started()
        return self._get_current_state()
