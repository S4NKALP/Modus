from fabric.audio.service import Audio
from fabric.widgets.box import Box
from snippets import MaterialIcon


class MicrophoneIndicator(Box):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.audio_service = Audio()
        self.microphone_icon = self.create_microphone_icon()

        self.audio_service.connect("microphone_changed", self.update_microphone_status)
        self.update_microphone_status()

        self.children = (self.microphone_icon,)

    def create_microphone_icon(self):
        return MaterialIcon("mic_off", size=16)

    def update_microphone_status(self, *args):
        current_microphone = self.audio_service.microphone

        if current_microphone:
            is_muted = current_microphone.muted
            icon_name = "mic_off" if is_muted else "mic"

            self.microphone_icon.set_label(icon_name)
            self.microphone_icon.set_visible(is_muted)
        else:
            self.microphone_icon.set_visible(False)

        return True
