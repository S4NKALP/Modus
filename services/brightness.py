import os
from loguru import logger
from fabric.core import Service, Property, Signal
from fabric.utils import exec_shell_command_async, monitor_file


class Brightness(Service):
    @Signal
    def changed(self) -> None: ...

    @Property(int, "readable")
    def max_brightness(self):
        if self._cached_max_brightness is not None:
            return self._cached_max_brightness
        try:
            with open(self._max_brightness_path) as f:
                self._cached_max_brightness = int(f.read().strip())
                return self._cached_max_brightness
        except Exception as e:
            logger.error(f"[Brightness] Failed to read max brightness: {e}")
            return -1

    @Property(int, "read-write")
    def brightness(self):
        try:
            with open(self._brightness_path) as f:
                return int(f.read().strip())
        except Exception as e:
            logger.error(f"[Brightness] Failed to read current brightness: {e}")
            return -1

    @brightness.setter
    def brightness(self, value: int):
        max_brightness = self.max_brightness
        if max_brightness <= 0:
            logger.error("[Brightness] Invalid max brightness; cannot set brightness.")
            return

        value = max(0, min(value, max_brightness))
        try:
            exec_shell_command_async(
                f"brightnessctl --device '{self._device}' set {value}"
            )
            logger.info(f"[Brightness] Set screen brightness to {value}")
        except Exception as e:
            logger.exception(f"[Brightness] Failed to set brightness: {e}")

    @Property(int, "readable")
    def brightness_percentage(self):
        max_brightness = self.max_brightness
        current_brightness = self.brightness

        if max_brightness <= 0:
            return 0
        return int((current_brightness / max_brightness) * 100)

    def __init__(self):
        super().__init__()
        self._device = None
        self._cached_max_brightness = None

        self._backlight_path = "/sys/class/backlight"

        try:
            devices = os.listdir(self._backlight_path)
            if devices:
                self._device = devices[0]
            else:
                raise FileNotFoundError
        except FileNotFoundError:
            logger.error("[Brightness] No backlight device found; brightness control disabled.")
            return

        self._brightness_path = f"{self._backlight_path}/{self._device}/brightness"
        self._max_brightness_path = f"{self._backlight_path}/{self._device}/max_brightness"

        try:
            self._screen_monitor = monitor_file(self._brightness_path)
            self._screen_monitor.connect("changed", lambda *args: self.changed.emit())
        except Exception as e:
            logger.error(f"[Brightness] Failed to monitor brightness file: {e}")
