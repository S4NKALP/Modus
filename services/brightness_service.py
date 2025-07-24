import os
from loguru import logger
from gi.repository import GLib

from fabric.core.service import Service, Signal
from fabric.utils.helpers import monitor_file

from config.info import BRIGHTNESS_DEV


class BrightnessService(Service):

    _instance = None

    @Signal
    def value_changed(self, new_value: int, max_value: int) -> None:...

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_singleton()
        return cls._instance

    def _init_singleton(self):
        super().__init__()

        self.max_brightness = -1
        self.brightness_monitor = None

        backlight_path = f"/sys/class/backlight/{BRIGHTNESS_DEV}"
        try:
            self.brightness_monitor = monitor_file(backlight_path)
            self.max_brightness = self._read_max_brightness(backlight_path)
            self.brightness_monitor.connect("changed", self._on_brightness_changed)
        except Exception as e:
            logger.error(f"Brightness device not found at {backlight_path}: {e}")

    def _read_max_brightness(self, path: str) -> int:
        max_path = os.path.join(path, "max_brightness")
        if os.path.exists(max_path):
            with open(max_path) as f:
                return int(f.readline())
        return -1

    def _on_brightness_changed(self, monitor, file, *args):
        try:
            raw = file.load_bytes()[0].get_data()
            new_value = round(int(raw))
            self.value_changed(new_value, self.max_brightness)
        except Exception as e:
            logger.warning(f"Failed to read brightness: {e}")
