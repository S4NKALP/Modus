from fabric import Fabricator
from fabric.utils import exec_shell_command
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from snippets import MaterialIcon
from services import audio

VOLUME_ICONS = {
    "muted": "volume_off",
    "low": "volume_mute",
    "medium-low": "volume_down",
    "medium-high": "volume_up",
    "high": "volume_up",
}


class VolumeIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.audio_service = audio
        self.volume_icon_button = self.create_volume_icon()

        self.volume_icon_button.connect("button-press-event", self.on_button_press)
        self.audio_service.connect("changed", self.update_volume_status)

        Fabricator(interval=1000, poll_from=self.update_volume_status)
        self.children = (self.volume_icon_button,)

    def create_volume_icon(self):
        icon = MaterialIcon(VOLUME_ICONS["muted"], size=16)
        button = Button(child=icon)
        button.icon_widget = icon
        return button

    def on_button_press(self, widget, event):
        if event.button == 1:
            self.toggle_mute()
        elif event.button == 3:
            self.open_audio_settings()

    def toggle_mute(self):
        current_stream = self.audio_service.speaker
        if current_stream:
            current_stream.muted = not current_stream.muted
            # self.update_volume_status()

    def open_audio_settings(self):
        exec_shell_command("pavucontrol")

    def update_volume_status(self, *_):
        current_stream = self.audio_service.speaker
        if current_stream:
            self.update_icon(current_stream)

        return True

    def update_icon(self, stream):
        if stream.muted:
            icon_name = VOLUME_ICONS["muted"]
            volume_percentage = 0
            tooltip_text = "Volume Muted"
        else:
            volume_level = stream.volume
            icon_name = self.get_volume_icon(volume_level)
            volume_percentage = int(volume_level)
            tooltip_text = f"Volume: {volume_percentage}%"

        self.volume_icon_button.icon_widget.set_label(icon_name)

        self.volume_icon_button.set_tooltip_text(tooltip_text)

    def get_volume_icon(self, volume_level):
        if volume_level == 0:
            return VOLUME_ICONS["low"]
        elif volume_level <= 33:
            return VOLUME_ICONS["medium-low"]
        elif volume_level <= 66:
            return VOLUME_ICONS["medium-high"]
        else:
            return VOLUME_ICONS["high"]
