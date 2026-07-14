from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import logger

from utils.gtk_utils import EvdevLEDMonitor

# Discover NumLock LED device
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
        self._last_state = None
        self._monitoring_started = False

        if numlock_device is None:
            logger.warning("NumLock device not found, NumLock service disabled")
            return

        # LED_NUML = 0
        self._monitor = EvdevLEDMonitor(
            self.numlock_led_path, 0, self._on_state_changed
        )

    def _on_state_changed(self, is_on: bool):
        if is_on != self._last_state:
            self._last_state = is_on
            self.emit("state_changed", is_on)

    def stop(self):
        if hasattr(self, "_monitor"):
            self._monitor.stop()

    def _ensure_monitoring_started(self):
        if not self._monitoring_started and self.numlock_led_path:
            self._monitoring_started = True
            # Set initial state before starting monitoring
            self._last_state = self._get_current_state()
            self._monitor._last_state = self._last_state
            self._monitor.start()

    def _get_current_state(self) -> bool:
        if not self.numlock_led_path:
            return False
        brightness_path = self.numlock_led_path / "brightness"
        if brightness_path.exists():
            try:
                return bool(int(brightness_path.read_text().strip()))
            except (ValueError, OSError) as e:
                logger.warning(
                    f"[numlock] return bool(int(brightness_path.read_text().strip())) failed: {e}"
                )
                return False
        return False

    @Property(bool, "read-write", default_value=False)
    def is_on(self) -> bool:
        self._ensure_monitoring_started()
        return self._get_current_state()
