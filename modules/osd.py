from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from gi.repository import GLib
from fabric.widgets.centerbox import CenterBox
from services import brightness, audio


def create_progress_bar(percentage, width=150):
    container = Box(orientation="h", name="progress-container")
    progress = Box(
        name="progress-fill", style=f"min-width: {percentage * width / 100}px;"
    )
    background = Box(name="progress-background", style=f"min-width: {width}px;")
    background.children = [progress]
    container.children = [background]
    return container


def update_progress_bar(progress_bar, percentage, width=150):
    progress_fill = progress_bar.children[0].children[0]
    progress_fill.set_style(f"min-width: {percentage * width / 100}px;")


def create_labeled_progress(label_text, value_text, percentage):
    label = Label(name="osd-label", markup=label_text)
    value = Label(name="osd-value", markup=value_text)
    header = CenterBox(orientation="h", start_children=[label], end_children=[value])
    progress = create_progress_bar(percentage)
    return Box(
        name="control-section", orientation="v", spacing=5, children=[header, progress]
    )


def get_brightness():
    return (
        round((brightness.screen_brightness / brightness.max_screen) * 100)
        if brightness.screen_brightness
        else 0
    )


def get_volume():
    return round(audio.speaker.volume) if audio.speaker else 0


class OSD(Window):
    def __init__(self):
        super().__init__(
            name="osd-menu",
            layer="overlay",
            anchor="top",
            margin="10px 0 0 0",
            keyboard_mode="on-demand",
            visible=False,
            style_classes="osd-panel",
        )
        self.last_volume = get_volume()
        self.last_brightness = get_brightness()
        self.volume_container = create_labeled_progress(
            "Speaker", str(self.last_volume), self.last_volume
        )
        self.brightness_container = create_labeled_progress(
            "Brightness", str(self.last_brightness), self.last_brightness
        )
        self.children = Box(
            orientation="h",
            spacing=10,
            children=[self.brightness_container, self.volume_container],
        )
        self.hide_timeout_id = None
        self._connect_signals()
        GLib.timeout_add(100, self._check_changes)

    def _connect_signals(self):
        audio.connect("notify::speaker", self._update_volume)
        brightness.connect("screen", self._update_brightness)

    def _update_volume(self, *_):
        volume = get_volume()
        self.volume_container.children[0].end_children[0].set_markup(str(volume))
        update_progress_bar(self.volume_container.children[1], volume)
        self._reset_timeout()

    def _update_brightness(self, *_):
        brightness_level = get_brightness()
        self.brightness_container.children[0].end_children[0].set_markup(
            str(brightness_level)
        )
        update_progress_bar(self.brightness_container.children[1], brightness_level)
        self._reset_timeout()

    def _reset_timeout(self):
        if self.hide_timeout_id:
            GLib.source_remove(self.hide_timeout_id)
        self.hide_timeout_id = GLib.timeout_add(1500, self._hide_osd)

    def _hide_osd(self):
        self.hide()
        self.hide_timeout_id = None
        return False

    def _check_changes(self):
        volume = get_volume()
        brightness_level = get_brightness()
        if volume != self.last_volume or brightness_level != self.last_brightness:
            self.last_volume, self.last_brightness = volume, brightness_level
            self.show_all()
            self._update_volume()
            self._update_brightness()
        return True
