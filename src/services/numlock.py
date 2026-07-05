from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import GLib, logger

# Discover NumLock LED device (same pattern as capslock)
numlock_leds = list(Path("/sys/class/leds").glob("input*::numlock"))
numlock_device = numlock_leds[0] if numlock_leds else None


class NumLock(Service):
    instance = None

    @staticmethod
    def get_initial():
        if NumLock.instance is None:
            NumLock.instance = NumLock()
        return NumLock.instance

    @Signal
    def state_changed(self, is_on: bool) -> None:
        """Signal emitted when NumLock state changes."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.numlock_led_path = numlock_device
        self._timeout_id = None
        self._last_state = None
        self._monitoring_started = False

        if numlock_device is None:
            logger.warning("NumLock device not found, NumLock service disabled")
            return

    def _start_led_monitoring(self):
        """Start efficient polling for NumLock LED state changes."""
        brightness_path = self.numlock_led_path / "brightness"
        if not brightness_path.exists():
            logger.warning(f"NumLock brightness file does not exist: {brightness_path}")
            return
        self._start_efficient_polling()

    def _start_efficient_polling(self):
        if self._timeout_id is None:
            self._timeout_id = GLib.timeout_add(500, self._efficient_poll)

    def _efficient_poll(self) -> bool:
        try:
            current_state = self._get_current_state()
            if current_state != self._last_state:
                self._last_state = current_state
                self.emit("state_changed", current_state)
        except Exception as e:
            logger.error(f"NumLock polling error: {e}")
            self._timeout_id = None
            return False
        return True

    def stop(self):
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

    def _ensure_monitoring_started(self):
        if not self._monitoring_started and self.numlock_led_path:
            self._monitoring_started = True
            self._last_state = self._get_current_state()
            self._start_led_monitoring()

    def _get_current_state(self) -> bool:
        if not self.numlock_led_path:
            return False
        brightness_path = self.numlock_led_path / "brightness"
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
