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
        self._monitoring_started = False

        if capslock_device is None:
            logger.warning("CapsLock device not found, CapsLock service disabled")
            return

        # Don't access is_on property during init to avoid starting monitoring
        # The last_state will be set when monitoring actually starts

    def _start_led_monitoring(self):
        """Start efficient polling for CapsLock LED state changes."""
        brightness_path = self.capslock_led_path / "brightness"
        if not brightness_path.exists():
            logger.warning(
                f"CapsLock brightness file does not exist: {brightness_path}"
            )
            return

        self._start_efficient_polling()

    def _start_efficient_polling(self):
        """Start efficient polling with 100ms intervals."""
        if self._timeout_id is None:
            self._timeout_id = GLib.timeout_add(100, self._efficient_poll)

    def _efficient_poll(self) -> bool:
        """Monitor CapsLock state with 100ms polling intervals.

        Returns:
            bool: True to continue polling, False to stop.
        """
        try:
            current_state = self._get_current_state()
            if current_state != self._last_state:
                self._last_state = current_state
                self.emit("state_changed", current_state)
        except Exception as e:
            logger.error(f"CapsLock polling error: {e}")
            self._timeout_id = None
            return False  # Stop polling on error

        return True  # Continue polling

    def stop(self):
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

    def _ensure_monitoring_started(self):
        if not self._monitoring_started and self.capslock_led_path:
            self._monitoring_started = True
            # Set initial state before starting monitoring
            self._last_state = self._get_current_state()
            self._start_led_monitoring()

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
