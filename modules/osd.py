import math
import time
from typing import ClassVar, Literal

from gi.repository import GLib, GObject

from fabric.audio import Audio
from fabric.utils.helpers import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.widgets.scale import Scale, ScaleMark
from fabric.widgets.svg import Svg
from services.brightness import Brightness
from utils.animator import Animator
from widgets.wayland import WaylandWindow as Window


class AnimatedScale(Scale):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.animator = None

    def animate_value(self, value: float):
        if not self.animator:
            self.animator = Animator(
                bezier_curve=(0.34, 1.56, 0.64, 1.0),
                duration=0.8,
                min_value=self.min_value,
                max_value=self.value,
                tick_widget=self,
                notify_value=lambda p, *_: self.set_value(p.value),
            )
        self.animator.pause()
        self.animator.min_value = self.value
        self.animator.max_value = value
        self.animator.play()


class BrightnessOSDContainer(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs, orientation="v", spacing=3, name="osd")
        self.brightness_service = Brightness.get_initial()
        self.scale = AnimatedScale(
            marks=(ScaleMark(value=i) for i in range(0, 101, 10)),
            value=70,
            min_value=0,
            max_value=100,
            increments=(1, 1),
            orientation="h",
        )
        self.osd_window_image = Svg(
            get_relative_path("../config/assets/icons/brightness/brightness.svg"),
            size=(84, 150),
            name="osd-image",
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )

        self.add(self.osd_window_image)
        self.add(self.scale)
        self.update_brightness()

        self.scale.connect("value-changed", lambda *_: self.update_brightness())
        self.brightness_service.connect("screen", self.on_brightness_changed)

    def update_brightness(self) -> None:
        current_brightness = self.brightness_service.screen_brightness
        normalized_brightness = self._normalize_brightness(current_brightness)
        if current_brightness != 0:
            self.scale.animate_value(normalized_brightness)

    def get_svg(self, value):
        b_level = 0 if value == 0 else min(int(math.ceil(value / 33)), 3)
        return b_level

    def on_brightness_changed(self, _sender: any, value: float, *_args) -> None:
        normalized_brightness = self._normalize_brightness(value)
        self.osd_window_image.set_from_file(
            get_relative_path(
                f"../config/assets/icons/brightness/brightness-{
                    self.get_svg(normalized_brightness)
                }.svg"
            )
        )
        self.scale.animate_value(normalized_brightness)

    def _normalize_brightness(self, brightness: float) -> float:
        return (brightness / self.brightness_service.max_screen) * 100


class AudioOSDContainer(Box):
    __gsignals__: ClassVar[dict] = {
        "volume-changed": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
    }

    def __init__(self, **kwargs):
        super().__init__(
            **kwargs,
            orientation="v",
            name="osd",
        )
        self.audio = Audio()
        self.scale = AnimatedScale(
            value=70,
            marks=(ScaleMark(value=i) for i in range(1, 100, 10)),
            min_value=0,
            max_value=100,
            increments=(1, 1),
            orientation="h",
        )
        self.osd_window_image = Svg(
            get_relative_path("../config/assets/icons/volume/audio-volume.svg"),
            size=(64, 150),
            name="osd-image",
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )

        self.previous_volume = None
        self.previous_muted = None

        self.add(self.osd_window_image)
        self.add(self.scale)
        self.sync_with_audio()

        self.scale.connect("value-changed", self.on_volume_changed)
        self.audio.connect("notify::speaker", self.on_audio_speaker_changed)

        # Connect to speaker-changed signal directly
        self.audio.connect("speaker-changed", self.on_speaker_changed)

        # Connect to current speaker if available
        if self.audio.speaker:
            self.audio.speaker.connect(
                "notify::volume", self.on_volume_property_changed
            )
            self.audio.speaker.connect("notify::muted", self.on_mute_changed)

    def get_svg(self, value):
        audio_level = 0 if value == 0 else min(int(math.ceil(value / 33)), 3)
        return audio_level

    def sync_with_audio(self):
        if self.audio.speaker:
            volume = round(self.audio.speaker.volume)
            self.scale.set_value(volume)
            # self.update_icon(volume)
            self.previous_volume = volume
            self.previous_muted = self.audio.speaker.muted

    def on_volume_changed(self, *_):
        if self.audio.speaker:
            volume = self.scale.value
            if 0 <= volume <= 100:
                self.audio.speaker.set_volume(volume)

                if volume == 0 or (self.audio.speaker and self.audio.speaker.muted):
                    self.scale.add_style_class("muted")
                    volume = 0
                    self.osd_window_image.set_from_file(
                        get_relative_path(
                            f"../config/assets/icons/volume/audio-volume-{
                                self.get_svg(volume)
                            }.svg"
                        )
                    )

                else:
                    self.on_volume_property_changed()
                    self.scale.remove_style_class("muted")
                    self.osd_window_image.set_from_file(
                        get_relative_path(
                            f"../config/assets/icons/volume/audio-volume-{
                                self.get_svg(volume)
                            }.svg"
                        )
                    )
                    # self.icon.remove_style_class("muted")

                self.emit("volume-changed")

    def on_audio_speaker_changed(self, *_):
        if self.audio.speaker:
            self.audio.speaker.connect(
                "notify::volume", self.on_volume_property_changed
            )
            self.audio.speaker.connect("notify::muted", self.on_mute_changed)
            self.update_volume()

    def on_speaker_changed(self, *_):
        self.update_volume()

    def on_volume_property_changed(self, *_):
        if self.audio.speaker:
            current_volume = round(self.audio.speaker.volume)
            if self.previous_volume is None or current_volume != self.previous_volume:
                self.previous_volume = current_volume
                self.update_volume()
                self.emit("volume-changed")

    def update_volume(self, *_):
        if self.audio.speaker and not self.is_hovered():
            volume = round(self.audio.speaker.volume)
            self.scale.set_value(volume)
            if volume == 0 or (self.audio.speaker and self.audio.speaker.muted):
                self.scale.add_style_class("muted")
                volume = 0
                self.osd_window_image.set_from_file(
                    get_relative_path(
                        f"../config/assets/icons/volume/audio-volume-{
                            self.get_svg(volume)
                        }.svg"
                    )
                )
            else:
                self.scale.remove_style_class("muted")
                self.osd_window_image.set_from_file(
                    get_relative_path(
                        f"../config/assets/icons/volume/audio-volume-{
                            self.get_svg(volume)
                        }.svg"
                    )
                )

    def on_mute_changed(self, *_):
        if self.audio.speaker:
            current_muted = self.audio.speaker.muted
            if self.previous_muted is None or current_muted != self.previous_muted:
                self.previous_muted = current_muted
                self.emit("volume-changed")


class MicrophoneOSDContainer(Box):
    __gsignals__: ClassVar[dict] = {
        "mic-changed": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs, orientation="v", spacing=13, name="osd")
        self.audio = Audio()
        self.scale = AnimatedScale(
            marks=(ScaleMark(value=i) for i in range(1, 100, 10)),
            value=70,
            min_value=0,
            max_value=100,
            increments=(1, 1),
            orientation="h",
        )

        self.osd_window_image = Svg(
            get_relative_path("../config/assets/icons/mic/microphone.svg"),
            size=(64, 150),
            name="osd-image",
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )
        self.previous_volume = None
        self.previous_muted = None

        self.add(self.osd_window_image)
        self.add(self.scale)
        self.sync_with_audio()

        self.scale.connect("value-changed", self.on_volume_changed)
        self.audio.connect("notify::microphone", self.on_audio_microphone_changed)

        # Connect to microphone-changed signal directly
        self.audio.connect("microphone-changed", self.on_microphone_changed)

        if self.audio.microphone:
            self.audio.microphone.connect(
                "notify::volume", self.on_volume_property_changed
            )
            self.audio.microphone.connect("notify::muted", self.on_mute_changed)

    def get_svg(self, value):
        audio_level = 0 if value == 0 else min(int(math.ceil(value / 33)), 3)
        return audio_level

    def sync_with_audio(self):
        if self.audio.microphone:
            volume = round(self.audio.microphone.volume)
            self.scale.set_value(volume)
            self.previous_volume = volume
            self.previous_muted = self.audio.microphone.muted

    def on_volume_changed(self, *_):
        if self.audio.microphone:
            volume = self.scale.value
            if 0 <= volume <= 100:
                self.audio.microphone.set_volume(volume)
                self.osd_window_image.set_from_file(
                    get_relative_path(
                        f"../config/assets/icons/mic/microphone-{
                            self.get_svg(volume)
                        }.svg"
                    )
                )

                if volume == 0 or (
                    self.audio.microphone and self.audio.microphone.muted
                ):
                    volume = 0
                    self.osd_window_image.set_from_file(
                        get_relative_path(
                            f"../config/assets/icons/mic/microphone-{
                                self.get_svg(volume)
                            }.svg"
                        )
                    )

                else:
                    self.osd_window_image.set_from_file(
                        get_relative_path(
                            f"../config/assets/icons/mic/microphone-{
                                self.get_svg(volume)
                            }.svg"
                        )
                    )
                    self.scale.remove_style_class("muted")

                self.emit("mic-changed")

    def on_audio_microphone_changed(self, *_):
        if self.audio.microphone:
            self.audio.microphone.connect(
                "notify::volume", self.on_volume_property_changed
            )
            self.audio.microphone.connect("notify::muted", self.on_mute_changed)
            self.update_volume()

    def on_microphone_changed(self, *_):
        self.update_volume()

    def on_volume_property_changed(self, *_):
        if self.audio.microphone:
            current_volume = round(self.audio.microphone.volume)
            if self.previous_volume is None or current_volume != self.previous_volume:
                self.previous_volume = current_volume
                self.osd_window_image.set_from_file(
                    get_relative_path(
                        f"../config/assets/icons/mic/microphone-{
                            self.get_svg(current_volume)
                        }.svg"
                    )
                )
                self.update_volume()
                self.emit("mic-changed")

    def update_volume(self, *_):
        if self.audio.microphone and not self.is_hovered():
            volume = round(self.audio.microphone.volume)
            self.scale.set_value(volume)

            if volume == 0 or (self.audio.microphone and self.audio.microphone.muted):
                self.scale.add_style_class("muted")
                volume = 0
                self.osd_window_image.set_from_file(
                    get_relative_path(
                        f"../config/assets/icons/mic/microphone-{
                            self.get_svg(volume)
                        }.svg"
                    )
                )
            else:
                self.osd_window_image.set_from_file(
                    get_relative_path(
                        f"../config/assets/icons/mic/microphone-{
                            self.get_svg(volume)
                        }.svg"
                    )
                )
                self.scale.remove_style_class("muted")

    def on_mute_changed(self, *_):
        if self.audio.microphone:
            current_muted = self.audio.microphone.muted
            if self.previous_muted is None or current_muted != self.previous_muted:
                self.previous_muted = current_muted
                GLib.idle_add(lambda: self.emit("mic-changed"))


class OSD(Window):
    def __init__(self, **kwargs):
        self.audio_container = AudioOSDContainer()
        self.brightness_container = BrightnessOSDContainer()
        self.microphone_container = MicrophoneOSDContainer()

        self.timeout = 1000

        self.revealer = Revealer(
            transition_type="slide-up",
            transition_duration=100,
            child_revealed=False,
        )

        self.main_box = Box(
            orientation="v",
            h_expand=True,
            children=[self.revealer],
        )

        super().__init__(
            layer="overlay",
            anchor="bottom",
            title="modus",
            child=self.main_box,
            visible=False,
            pass_through=True,
            keyboard_mode="on-demand",
            **kwargs,
        )

        self.last_activity_time = time.time()

        self.audio_container.connect("volume-changed", self.show_audio)
        self.brightness_container.brightness_service.connect(
            "screen", self.show_brightness
        )
        self.microphone_container.connect("mic-changed", self.show_microphone)

        GLib.timeout_add(100, self.check_inactivity)

    def show_audio(self, *_):
        self.show_box(box_to_show="audio")
        self.reset_inactivity_timer()

    def show_brightness(self, *_):
        self.show_box(box_to_show="brightness")
        self.reset_inactivity_timer()

    def show_microphone(self, *_):
        self.show_box(box_to_show="microphone")
        self.reset_inactivity_timer()

    def show_box(self, box_to_show: Literal["audio", "brightness", "microphone"]):
        self.set_visible(True)
        if box_to_show == "audio":
            self.revealer.children = self.audio_container
        elif box_to_show == "brightness":
            self.revealer.children = self.brightness_container
        elif box_to_show == "microphone":
            self.revealer.children = self.microphone_container
        self.revealer.set_reveal_child(True)
        self.reset_inactivity_timer()

    def start_hide_timer(self):
        self.set_visible(False)

    def reset_inactivity_timer(self):
        self.last_activity_time = time.time()

    def check_inactivity(self):
        if time.time() - self.last_activity_time >= (self.timeout / 1000):
            self.start_hide_timer()
        return True
