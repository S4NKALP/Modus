import math

from fabric.utils import logger
from fabric.widgets.scale import ScaleMark

from services.brightness import Brightness
from utils.gtk_utils import svg_file

from .animated_scale import AnimatedScale
from .base import BaseOSDContainer


class BrightnessOSDContainer(BaseOSDContainer):
    def __init__(self, window, **kwargs):
        super().__init__(window, **kwargs)
        self.brightness_service = Brightness()
        self._last_percent = None
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.osd_window_image = svg_file(
            "brightness/brightness.svg",
            size=(100, 100),
            name="osd-image",
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )
        self.scale = AnimatedScale(
            marks=(ScaleMark(value=i) for i in range(0, 101, 10)),
            value=70,
            min_value=0,
            max_value=100,
            increments=(1, 1),
            orientation="h",
        )
        self.add(self.osd_window_image)
        self.add(self.scale)

    def _connect_specific_signals(self):
        self.brightness_service.connect("screen", self._on_brightness_changed)

    def _on_brightness_changed(self, _sender, percent, *_args):
        if self._last_percent != percent:
            self._last_percent = percent
            self.update()

    def _sync_with_service(self):
        raw = self.brightness_service.screen_brightness
        max_br = self.brightness_service.max_screen
        self._last_percent = int((raw / max_br) * 100) if max_br > 0 and raw >= 0 else 0
        self.scale.set_value(self._last_percent)
        self._update_display()

    def _update_display(self):
        percent = self._last_percent if self._last_percent is not None else 0
        level = 0 if percent == 0 else min(math.ceil(percent / 33), 3)

        self.osd_window_image.set_from_file(f"brightness/brightness-{level}.svg")
        self.scale.animate_value(percent)

    def update(self, *_):
        self._update_display()
        super().update()

    def destroy(self):
        try:
            self.brightness_service.disconnect_by_func(self._on_brightness_changed)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        super().destroy()
