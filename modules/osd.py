import time
from typing import ClassVar, Literal
from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.widgets.scale import Scale, ScaleMark
from fabric.widgets.wayland import WaylandWindow as Window
from gi.repository import GObject
from snippets import Animator, MaterialIcon
from services import brightness, audio


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
        super().__init__(**kwargs, orientation="h", spacing=12, name="osd")
        self.brightness_service = brightness
        self.icon = MaterialIcon(icon_name="brightness_7", size=20)
        self.scale = AnimatedScale(
            marks=(ScaleMark(value=i) for i in range(0, 101, 10)),
            value=70,
            min_value=0,
            max_value=100,
            increments=(1, 1),
            orientation="h",
        )

        self.add(self.icon)
        self.add(self.scale)
        self.update_brightness()

        self.scale.connect("value-changed", lambda *_: self.update_brightness())
        self.brightness_service.connect("screen", self.on_brightness_changed)

    def update_brightness(self) -> None:
        current_brightness = self.brightness_service.screen_brightness
        if current_brightness != 0:
            normalized_brightness = self._normalize_brightness(current_brightness)
            self.scale.animate_value(normalized_brightness)
        self.update_icon(normalized_brightness)

    def update_icon(self, brightness_percentage: float) -> None:
        icon_name = self.get_brightness_icon(brightness_percentage)
        self.icon.set_label(icon_name)

    def on_brightness_changed(self, _sender: any, value: float, *_args) -> None:
        normalized_brightness = self._normalize_brightness(value)
        self.scale.animate_value(normalized_brightness)
        self.update_icon(normalized_brightness)

    def _normalize_brightness(self, brightness: float) -> float:
        return (brightness / self.brightness_service.max_screen) * 100

    def get_brightness_icon(self, brightness_percentage: float) -> str:
        brightness_icons = [
            "brightness_1",
            "brightness_2",
            "brightness_3",
            "brightness_4",
            "brightness_5",
            "brightness_6",
            "brightness_7",
        ]
        thresholds = [
            100 / (1.6 ** (len(brightness_icons) - i - 1))
            for i in range(len(brightness_icons))
        ]

        for i, threshold in enumerate(thresholds):
            if brightness_percentage < threshold:
                return brightness_icons[i]

        return brightness_icons[-1]


class AudioOSDContainer(Box):
    __gsignals__: ClassVar[dict] = {
        "volume-changed": (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs, orientation="h", spacing=13, name="osd")
        self.audio = audio
        self.icon = MaterialIcon(icon_name="volume_up", size=20)
        self.scale = AnimatedScale(
            marks=(ScaleMark(value=i) for i in range(1, 100, 10)),
            value=70,
            min_value=0,
            max_value=100,
            increments=(1, 1),
            orientation="h",
        )

        self.add(self.icon)
        self.add(self.scale)
        self.sync_with_audio()

        self.scale.connect("value-changed", self.on_volume_changed)
        self.audio.connect("notify::speaker", self.on_audio_speaker_changed)

    def sync_with_audio(self):
        if self.audio.speaker:
            volume = round(self.audio.speaker.volume)
            self.scale.set_value(volume)
            self.update_icon(volume)

    def on_volume_changed(self, *_):
        if self.audio.speaker:
            volume = self.scale.value
            if 0 <= volume <= 100:
                self.audio.speaker.set_volume(volume)
                self.update_icon(volume)
                self.emit("volume-changed")

    def on_audio_speaker_changed(self, *_):
        if self.audio.speaker:
            self.audio.speaker.connect("notify::volume", self.update_volume)
            self.update_volume()

    def update_volume(self, *_):
        if self.audio.speaker and not self.is_hovered():
            volume = round(self.audio.speaker.volume)
            self.scale.set_value(volume)
            self.update_icon(volume)

    def update_icon(self, volume):
        icon_name = self._get_audio_icon_name(volume)
        self.icon.set_label(icon_name)

    def _get_audio_icon_name(self, volume: int) -> str:
        if volume == 101:
            return "sound_detection_loud_sound"
        elif volume >= 67:
            return "volume_up"
        elif volume >= 34:
            return "volume_down"
        elif volume >= 1:
            return "volume_mute"
        else:
            return "volume_off"


class OSDContainer(Window):
    def __init__(self, **kwargs):
        self.audio_container = AudioOSDContainer()
        self.brightness_container = BrightnessOSDContainer()

        self.timeout = 1000

        self.revealer = Revealer(
            transition_type="slide-right",
            transition_duration=200,
            child_revealed=False,
        )

        self.main_box = Box(
            orientation="v",
            spacing=13,
            children=[self.revealer],
        )

        super().__init__(
            layer="overlay",
            anchor="bottom",
            child=self.main_box,
            visible=False,
            pass_through=True,
            keyboard_mode="on-demand",
            **kwargs,
        )

        self.last_activity_time = time.time()

        self.audio_container.audio.connect("notify::speaker", self.show_audio)
        self.brightness_container.brightness_service.connect(
            "screen", self.show_brightness
        )
        self.audio_container.connect("volume-changed", self.show_audio)

        invoke_repeater(100, self.check_inactivity, initial_call=True)

    def show_audio(self, *_):
        self.show_box(box_to_show="audio")
        self.reset_inactivity_timer()

    def show_brightness(self, *_):
        self.show_box(box_to_show="brightness")
        self.reset_inactivity_timer()

    def show_box(self, box_to_show: Literal["audio", "brightness"]):
        self.set_visible(True)
        if box_to_show == "audio":
            self.revealer.children = self.audio_container
        elif box_to_show == "brightness":
            self.revealer.children = self.brightness_container
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
