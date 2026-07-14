from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import logger

from utils.gtk_utils import EvdevLEDMonitor

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
        self._last_state = None
        self._monitoring_started = False

        if capslock_device is None:
            logger.warning("CapsLock device not found, CapsLock service disabled")
            return

        # LED_CAPSL = 1
        self._monitor = EvdevLEDMonitor(
            self.capslock_led_path, 1, self._on_state_changed
        )

    def _on_state_changed(self, is_on: bool):
        if is_on != self._last_state:
            self._last_state = is_on
            self.emit("state_changed", is_on)

    def stop(self):
        if hasattr(self, "_monitor"):
            self._monitor.stop()

    def _ensure_monitoring_started(self):
        if not self._monitoring_started and self.capslock_led_path:
            self._monitoring_started = True
            # Set initial state before starting monitoring
            self._last_state = self._get_current_state()
            self._monitor._last_state = self._last_state
            self._monitor.start()

    def _get_current_state(self) -> bool:
        if not self.capslock_led_path:
            return False
        brightness_path = self.capslock_led_path / "brightness"
        if brightness_path.exists():
            try:
                return bool(int(brightness_path.read_text().strip()))
            except (ValueError, OSError) as e:
                logger.warning(
                    f"[capslock] return bool(int(brightness_path.read_text().strip())) failed: {e}"
                )
                return False
        return False

    @Property(bool, "read-write", default_value=False)
    def is_on(self) -> bool:
        self._ensure_monitoring_started()
        return self._get_current_state()
