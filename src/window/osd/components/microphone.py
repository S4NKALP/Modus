import math
from fabric.audio import Audio
from utils.utils import svg_file
from fabric.widgets.scale import ScaleMark
from .animated_scale import AnimatedScale
from .base import BaseOSDContainer


class MicrophoneOSDContainer(BaseOSDContainer):
    def __init__(self, window, **kwargs):
        super().__init__(window, **kwargs)
        self.audio = Audio()
        self._last_volume = None
        self._last_muted = None
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.osd_window_image = svg_file(
            "mic/microphone.svg",
            size=(100, 100),
            name="osd-image",
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )
        self.scale = AnimatedScale(
            marks=(ScaleMark(value=i) for i in range(1, 100, 10)),
            value=70,
            min_value=0,
            max_value=100,
            increments=(1, 1),
            orientation="h",
        )
        self.add(self.osd_window_image)
        self.add(self.scale)

    def _connect_specific_signals(self):
        self.audio.connect("notify::microphone", self._on_microphone_changed)
        if self.audio.microphone:
            self._connect_microphone_signals()

    def _connect_microphone_signals(self):
        if self.audio.microphone:
            self.audio.microphone.connect("changed", self._on_microphone_stream_changed)
            self._sync_with_audio()

    def _on_microphone_changed(self, *_):
        self._connect_microphone_signals()
        self.update()

    def _on_microphone_stream_changed(self, *_):
        if self.audio.microphone:
            current_volume = round(self.audio.microphone.volume)
            current_muted = self.audio.microphone.muted
            if self._last_volume != current_volume or self._last_muted != current_muted:
                self._last_volume = current_volume
                self._last_muted = current_muted
                self.update()

    def _sync_with_audio(self):
        if self.audio.microphone:
            self._last_volume = round(self.audio.microphone.volume)
            self._last_muted = self.audio.microphone.muted
            self.scale.set_value(self._last_volume)
            self._update_display()

    def _update_display(self):
        if not self.audio.microphone:
            return

        volume = (
            self._last_volume
            if self._last_volume is not None
            else round(self.audio.microphone.volume)
        )
        muted = (
            self._last_muted
            if self._last_muted is not None
            else self.audio.microphone.muted
        )

        display_volume = 0 if (volume == 0 or muted) else volume
        level = (
            0 if display_volume == 0 else min(int(math.ceil(display_volume / 33)), 3)
        )

        self.osd_window_image.set_from_file(f"mic/microphone-{level}.svg")

        if muted or volume == 0:
            self.scale.add_style_class("muted")
        else:
            self.scale.remove_style_class("muted")

        self.scale.animate_value(volume)

    def update(self, *_):
        self._update_display()
        super().update()
