from fabric.audio.service import Audio
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.scale import Scale
from gi.repository import Gdk, GLib

import config.data as data
import utils.icons as icons
from services.brightness import Brightness


class BrightnessSmall(Box):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-brightness", **kwargs)
        self.brightness = Brightness.get_initial()
        if self.brightness.screen_brightness == -1:
            self.destroy()
            return

        self.progress_bar = CircularProgressBar(
            name="button-brightness", size=28, line_width=2,
            start_angle=150, end_angle=390,
        )
        self.brightness_label = Label(name="brightness-label", markup=icons.brightness_high)
        self.brightness_button = Button(child=self.brightness_label)
        self.event_box = EventBox(
            events=["scroll", "smooth-scroll"],
            child=Overlay(
                child=self.progress_bar,
                overlays=self.brightness_button
            ),
        )
        self.event_box.connect("scroll-event", self.on_scroll)
        self.add(self.event_box)
        self.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)

        self._updating_from_brightness = False
        self._pending_value = None
        self._update_source_id = None

        self.progress_bar.connect("notify::value", self.on_progress_value_changed)
        self.brightness.connect("screen", self.on_brightness_changed)
        self.on_brightness_changed()

    def on_scroll(self, widget, event):
        if self.brightness.max_screen == -1:
            return

        step_size = 5
        current_norm = self.progress_bar.value
        if event.delta_y < 0:
            new_norm = min(current_norm + (step_size / self.brightness.max_screen), 1)
        elif event.delta_y > 0:
            new_norm = max(current_norm - (step_size / self.brightness.max_screen), 0)
        else:
            return
        self.progress_bar.value = new_norm

    def on_progress_value_changed(self, widget, pspec):
        if self._updating_from_brightness:
            return
        new_norm = widget.value
        new_brightness = int(new_norm * self.brightness.max_screen)
        self._pending_value = new_brightness
        if self._update_source_id is None:
            self._update_source_id = GLib.timeout_add(50, self._update_brightness_callback)

    def _update_brightness_callback(self):
        if self._pending_value is not None and self._pending_value != self.brightness.screen_brightness:
            self.brightness.screen_brightness = self._pending_value
            self._pending_value = None
            return True
        else:
            self._update_source_id = None
            return False

    def on_brightness_changed(self, *args):
        if self.brightness.max_screen == -1:
            return
        normalized = self.brightness.screen_brightness / self.brightness.max_screen
        self._updating_from_brightness = True
        self.progress_bar.value = normalized
        self._updating_from_brightness = False

        brightness_percentage = int(normalized * 100)
        if brightness_percentage >= 75:
            self.brightness_label.set_markup(icons.brightness_high)
        elif brightness_percentage >= 24:
            self.brightness_label.set_markup(icons.brightness_medium)
        else:
            self.brightness_label.set_markup(icons.brightness_low)
        self.set_tooltip_text(f"{brightness_percentage}%")

    def destroy(self):
        if self._update_source_id is not None:
            GLib.source_remove(self._update_source_id)
        super().destroy()

class VolumeSmall(Box):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-vol", **kwargs)
        self.audio = Audio()
        self.progress_bar = CircularProgressBar(
            name="button-volume", size=28, line_width=2,
            start_angle=150, end_angle=390,
        )
        self.vol_label = Label(name="vol-label", markup=icons.vol_high)
        self.vol_button = Button(on_clicked=self.toggle_mute, child=self.vol_label)
        self.event_box = EventBox(
            events=["scroll", "smooth-scroll"],
            child=Overlay(child=self.progress_bar, overlays=self.vol_button),
        )
        self.audio.connect("notify::speaker", self.on_new_speaker)
        if self.audio.speaker:
            self.audio.speaker.connect("changed", self.on_speaker_changed)
        self.event_box.connect("scroll-event", self.on_scroll)
        self.add(self.event_box)
        self.on_speaker_changed()
        self.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)

    def on_new_speaker(self, *args):
        if self.audio.speaker:
            self.audio.speaker.connect("changed", self.on_speaker_changed)
            self.on_speaker_changed()

    def toggle_mute(self, event):
        current_stream = self.audio.speaker
        if current_stream:
            current_stream.muted = not current_stream.muted
            if current_stream.muted:
                self.on_speaker_changed()
                self.progress_bar.add_style_class("muted")
                self.vol_label.add_style_class("muted")
            else:
                self.on_speaker_changed()
                self.progress_bar.remove_style_class("muted")
                self.vol_label.remove_style_class("muted")

    def on_scroll(self, _, event):
        if not self.audio.speaker:
            return
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            if abs(event.delta_y) > 0:
                self.audio.speaker.volume -= event.delta_y
            if abs(event.delta_x) > 0:
                self.audio.speaker.volume += event.delta_x

    def on_speaker_changed(self, *_):
        if not self.audio.speaker:
            return
        
        vol_high_icon = icons.vol_high
        vol_medium_icon = icons.vol_medium
        vol_mute_icon = icons.vol_off
        vol_off_icon = icons.vol_mute

        if "bluetooth" in self.audio.speaker.icon_name:
            vol_high_icon = icons.bluetooth_connected
            vol_medium_icon = icons.bluetooth
            vol_mute_icon = icons.bluetooth_off
            vol_off_icon = icons.bluetooth_disconnected

        self.progress_bar.value = self.audio.speaker.volume / 100
        
        if self.audio.speaker.muted:
            self.vol_label.set_markup(vol_mute_icon)
            self.progress_bar.add_style_class("muted")
            self.vol_label.add_style_class("muted")
            self.set_tooltip_text("Muted")
            return
        else:
            self.progress_bar.remove_style_class("muted")
            self.vol_label.remove_style_class("muted")
        self.set_tooltip_text(f"{round(self.audio.speaker.volume)}%")
        if self.audio.speaker.volume > 74:
            self.vol_label.set_markup(vol_high_icon)
        elif self.audio.speaker.volume > 0:
            self.vol_label.set_markup(vol_medium_icon)
        else:
            self.vol_label.set_markup(vol_off_icon)

class MicSmall(Box):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-mic", **kwargs)
        self.audio = Audio()
        self.progress_bar = CircularProgressBar(
            name="button-mic", size=28, line_width=2,
            start_angle=150, end_angle=390,
        )
        self.mic_label = Label(name="mic-label", markup=icons.mic)
        self.mic_button = Button(on_clicked=self.toggle_mute, child=self.mic_label)
        self.event_box = EventBox(
            events=["scroll", "smooth-scroll"],
            child=Overlay(child=self.progress_bar, overlays=self.mic_button),
        )
        self.audio.connect("notify::microphone", self.on_new_microphone)
        if self.audio.microphone:
            self.audio.microphone.connect("changed", self.on_microphone_changed)
        self.event_box.connect("scroll-event", self.on_scroll)
        self.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.add(self.event_box)
        self.on_microphone_changed()

    def on_new_microphone(self, *args):
        if self.audio.microphone:
            self.audio.microphone.connect("changed", self.on_microphone_changed)
            self.on_microphone_changed()

    def toggle_mute(self, event):
        current_stream = self.audio.microphone
        if current_stream:
            current_stream.muted = not current_stream.muted
            if current_stream.muted:
                self.mic_label.set_markup(icons.mic_mute)
                self.progress_bar.add_style_class("muted")
                self.mic_label.add_style_class("muted")
            else:
                self.on_microphone_changed()
                self.progress_bar.remove_style_class("muted")
                self.mic_label.remove_style_class("muted")

    def on_scroll(self, _, event):
        if not self.audio.microphone:
            return
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            if abs(event.delta_y) > 0:
                self.audio.microphone.volume -= event.delta_y
            if abs(event.delta_x) > 0:
                self.audio.microphone.volume += event.delta_x

    def on_microphone_changed(self, *_):
        if not self.audio.microphone:
            return
        
        self.progress_bar.value = self.audio.microphone.volume / 100
        
        if self.audio.microphone.muted:
            self.mic_label.set_markup(icons.mic_mute)
            self.progress_bar.add_style_class("muted")
            self.mic_label.add_style_class("muted")
            self.set_tooltip_text("Muted")
            return
        else:
            self.progress_bar.remove_style_class("muted")
            self.mic_label.remove_style_class("muted")
        self.set_tooltip_text(f"{round(self.audio.microphone.volume)}%")
        if self.audio.microphone.volume > 74:
            self.mic_label.set_markup(icons.mic)
        elif self.audio.microphone.volume > 0:
            self.mic_label.set_markup(icons.mic)
        else:
            self.mic_label.set_markup(icons.mic_mute)

class Controls(Box):
    def __init__(self, **kwargs):
        brightness = Brightness.get_initial()
        children = []
        if (brightness.screen_brightness != -1):
            children.append(BrightnessSmall())
        children.extend([VolumeSmall(), MicSmall()])
        super().__init__(
            name="control",
            orientation="h" if not data.VERTICAL else "v",
            spacing=4,
            children=children,
            **kwargs,
        )
        self.show_all()
