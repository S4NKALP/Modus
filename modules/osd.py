import time
from typing import ClassVar

from fabric.audio import Audio
from fabric.widgets.box import Box
from fabric.widgets.scale import Scale, ScaleMark
from utils.wayland import WaylandWindow as Window
from fabric.utils import invoke_repeater
from gi.repository import GObject
from services.brightness import Brightness
from fabric.widgets.label import Label
from utils import Animator


class AnimatedScale(Scale):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.animator = None  # Lazily initialized

    def animate_value(self, value: float):
        if not self.animator:
            self.animator = Animator(
                bezier_curve=(0.34, 1.56, 0.64, 1.0),
                duration=0.8,
                min_value=self.min_value,
                max_value=self.max_value,
                tick_widget=self,
                notify_value=lambda p, *_: self.set_value(p.value),
            )
        self.animator.pause()
        self.animator.min_value = self.value
        self.animator.max_value = min(max(value, self.min_value), self.max_value)
        self.animator.play()


class BaseOSDContainer(Box):
    def __init__(self, label_text, **kwargs):
        super().__init__(**kwargs, orientation="v", spacing=8, name="osd")

        self.header = Box(orientation="h")
        self.label = Label(
            label=label_text, name="osd-label", h_align="start", h_expand=True
        )
        self.value_label = Label(name="osd-label", h_align="end")
        self.header.add(self.label)
        self.header.add(self.value_label)

        self.scale = AnimatedScale(
            marks=(ScaleMark(value=i) for i in range(0, 100, 10)),
            value=70,
            min_value=0,
            max_value=100,
            increments=(1, 1),
            orientation="h",
        )

        self.add(self.header)
        self.add(self.scale)

    def update_value_label(self, value):
        self.value_label.set_label(str(round(value)))


class BrightnessOSDContainer(BaseOSDContainer):
    def __init__(self, **kwargs):
        super().__init__(label_text="Brightness", **kwargs)
        self.brightness_service = Brightness()
        self.update_brightness()

        self.scale.connect("value-changed", lambda *_: self.update_brightness())
        self.brightness_service.connect("screen", self.on_brightness_changed)

    def update_brightness(self) -> None:
        current_brightness = self.brightness_service.screen_brightness
        if current_brightness != 0:
            normalized_brightness = self._normalize_brightness(current_brightness)
            self.scale.set_value(normalized_brightness)
            self.update_value_label(normalized_brightness)

    def on_brightness_changed(self, _sender: any, value: float, *_args) -> None:
        normalized_brightness = self._normalize_brightness(value)
        self.scale.animate_value(normalized_brightness)
        self.update_value_label(normalized_brightness)

    def _normalize_brightness(self, brightness: float) -> float:
        normalized = (brightness / self.brightness_service.max_screen) * 100
        return max(0, min(100, normalized))  # Ensure value stays within bounds


class AudioOSDContainer(BaseOSDContainer):
    __gsignals__: ClassVar[dict] = {
        "volume-changed": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
    }

    def __init__(self, **kwargs):
        super().__init__(label_text="Volume", **kwargs)
        self.audio = Audio()
        self.sync_with_audio()

        self.scale.connect("value-changed", self.on_volume_changed)
        self.audio.connect("notify::speaker", self.on_audio_speaker_changed)
        self.audio.connect("speaker-changed", self.on_speaker_changed)

    def sync_with_audio(self):
        if self.audio.speaker:
            volume = round(self.audio.speaker.volume)
            self.scale.set_value(
                max(0, min(100, volume))
            )  # Ensure value stays within bounds
            self.update_value_label(volume)

    def on_volume_changed(self, *_):
        if self.audio.speaker:
            volume = self.scale.value
            if 0 <= volume <= 100:
                self.audio.speaker.set_volume(volume)
                self.update_value_label(volume)
                self.emit("volume-changed")

    def on_audio_speaker_changed(self, *_):
        if self.audio.speaker:
            self.audio.speaker.connect("changed", self.update_volume)
            self.update_volume()

    def on_speaker_changed(self, *_):
        self.update_volume()

    def update_volume(self, *_):
        if self.audio.speaker and not self.is_hovered():
            volume = round(self.audio.speaker.volume)
            self.scale.set_value(
                max(0, min(100, volume))
            )  # Ensure value stays within bounds
            self.update_value_label(volume)


class OSD(Window):
    def __init__(self, **kwargs):
        self.audio_container = AudioOSDContainer()
        self.brightness_container = BrightnessOSDContainer()

        self.timeout = 1000

        self.controls_box = Box(
            orientation="h",
            spacing=20,
            children=[self.brightness_container, self.audio_container],
        )

        super().__init__(
            layer="overlay",
            anchor="top",
            child=self.controls_box,
            visible=False,
            pass_through=True,
            keyboard_mode="on-demand",
            **kwargs,
        )

        self.last_activity_time = time.time()

        self.audio_container.audio.connect("notify::speaker", self.show_controls)
        self.brightness_container.brightness_service.connect(
            "screen", self.show_controls
        )
        self.audio_container.connect("volume-changed", self.show_controls)

        invoke_repeater(100, self.check_inactivity, initial_call=True)

    def show_controls(self, *_):
        self.set_visible(True)
        self.reset_inactivity_timer()

    def start_hide_timer(self):
        self.set_visible(False)

    def reset_inactivity_timer(self):
        self.last_activity_time = time.time()

    def check_inactivity(self):
        if time.time() - self.last_activity_time >= (self.timeout / 1000):
            self.start_hide_timer()
        return True
