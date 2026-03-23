import math
from services.brightness import Brightness
from fabric.utils import get_relative_path
from fabric.widgets.svg import Svg
from fabric.widgets.scale import ScaleMark
from .animated_scale import AnimatedScale
from .base import BaseOSDContainer


class BrightnessOSDContainer(BaseOSDContainer):
    def __init__(self, window, **kwargs):
        super().__init__(window, **kwargs)
        self.brightness_service = Brightness.get_initial()
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.osd_window_image = Svg(
            get_relative_path("../../../config/assets/icons/brightness/brightness.svg"),
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
        self.brightness_service.connect("screen", self._on_screen_brightness_changed)

    def _on_screen_brightness_changed(self, _sender, value, *_args):
        self.update()

    def _get_normalized_brightness(self):
        return (
            self.brightness_service.screen_brightness
            / self.brightness_service.max_screen
        ) * 100

    def _update_display(self):
        normalized = self._get_normalized_brightness()
        level = 0 if normalized == 0 else min(int(math.ceil(normalized / 33)), 3)

        self.osd_window_image.set_from_file(
            get_relative_path(
                f"../../../config/assets/icons/brightness/brightness-{level}.svg"
            )
        )

        self.scale.animate_value(normalized)

    def update(self, *_):
        self._update_display()
        super().update()
