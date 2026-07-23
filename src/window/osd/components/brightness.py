import math

from fabric.utils import logger

from services.brightness import Brightness
from shared.widgets.block_progress_bar import BlockProgressBar
from utils.gtk_utils import svg_file

from .base import BaseOSDContainer


class BrightnessOSDContainer(BaseOSDContainer):
    def __init__(self, window, **kwargs):
        super().__init__(window, **kwargs)
        self.brightness_service = Brightness()
        self._last_percent = None
        self._last_blocks = None
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
        self.scale = BlockProgressBar(
            value=70,
            min_value=0,
            max_value=100,
            block_count=15,
            block_spacing=2.0,
            block_height=10.0,
            block_radius=0.0,
            orientation="horizontal",
            name="osd-block-bar",
            h_expand=True,
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
        block_size = 100 / self.scale._block_count
        self._last_blocks = int(self._last_percent / block_size)
        self.scale.set_value(self._last_blocks * block_size)
        self._update_display()

    def _update_display(self):
        if self._last_percent is None:
            raw = self.brightness_service.screen_brightness
            max_br = self.brightness_service.max_screen
            self._last_percent = (
                int((raw / max_br) * 100) if max_br > 0 and raw >= 0 else 0
            )
        percent = self._last_percent
        block_size = 100 / self.scale._block_count
        target_blocks = int(percent / block_size)

        if self._last_blocks is None:
            display_blocks = target_blocks
        elif target_blocks > self._last_blocks:
            display_blocks = self._last_blocks + 1
        elif target_blocks < self._last_blocks:
            display_blocks = self._last_blocks - 1
        else:
            display_blocks = self._last_blocks

        self._last_blocks = display_blocks
        snapped = display_blocks * block_size
        level = 0 if percent == 0 else min(math.ceil(percent / 33), 3)

        self.osd_window_image.set_from_file(f"brightness/brightness-{level}.svg")
        self.scale.animate_value(snapped)

    def update(self, *_):
        self._update_display()
        super().update()

    def destroy(self):
        try:
            self.brightness_service.disconnect_by_func(self._on_brightness_changed)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        super().destroy()
