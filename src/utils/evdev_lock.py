"""Parameterised evdev LED-lock service base.

NumLock and CapsLock services are structurally identical; only the LED
glob pattern, LED index, and service name differ.  This module provides a
single base class that both services can inherit from.
"""

from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import logger

from utils.gtk_utils import EvdevLEDMonitor


class EvdevLockService(Service):
    """Base service for keyboard lock-key monitoring via evdev LEDs.

    Subclasses must set **class-level** attributes:

    * ``_LED_GLOB`` – sysfs glob for the LED device
      (e.g. ``"input*::numlock"``).
    * ``_LED_INDEX`` – integer LED code passed to :class:`EvdevLEDMonitor`
      (0 = NUML, 1 = CAPSL).
    * ``_SERVICE_NAME`` – human-readable name for log messages.
    """

    _LED_GLOB: str = ""
    _LED_INDEX: int = 0
    _SERVICE_NAME: str = "EvdevLock"

    _instance = None

    @Signal
    def state_changed(self, is_on: bool) -> None:
        """Emitted when the lock-key state changes."""

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        leds = list(Path("/sys/class/leds").glob(self._LED_GLOB))
        self._led_path = leds[0] if leds else None
        self._last_state = None
        self._monitoring_started = False

        if self._led_path is None:
            logger.warning(f"[{self._SERVICE_NAME}] Device not found, service disabled")
            return

        self._monitor = EvdevLEDMonitor(
            self._led_path, self._LED_INDEX, self._on_state_changed
        )

    def _on_state_changed(self, is_on: bool):
        if is_on != self._last_state:
            self._last_state = is_on
            self.emit("state_changed", is_on)

    def stop(self):
        if hasattr(self, "_monitor"):
            self._monitor.stop()

    def _ensure_monitoring_started(self):
        if not self._monitoring_started and self._led_path:
            self._monitoring_started = True
            self._last_state = self._get_current_state()
            self._monitor._last_state = self._last_state
            self._monitor.start()

    def _get_current_state(self) -> bool:
        if not self._led_path:
            return False
        brightness_path = self._led_path / "brightness"
        if brightness_path.exists():
            try:
                return bool(int(brightness_path.read_text().strip()))
            except (ValueError, OSError) as e:
                logger.warning(f"[{self._SERVICE_NAME}] Failed to read brightness: {e}")
                return False
        return False

    @Property(bool, "read-write", default_value=False)
    def is_on(self) -> bool:
        self._ensure_monitoring_started()
        return self._get_current_state()
