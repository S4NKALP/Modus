from fabric.utils import GLib
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window

from modules.osd.components.base import BaseOSDContainer
from services import Audio


class MicrophoneOSDContainer(BaseOSDContainer):
    def __init__(self, window: Window, **kwargs):
        super().__init__(window, **kwargs)
        self.audio = Audio(controller_name="fabric-osd-microphone")
        self._last_muted = None
        self._connected_mics = set()
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.icon = Image(
            icon_name="microphone-sensitivity-muted-symbolic", icon_size=26
        )
        self.label = Label()

        self.update_icon(True)  # Start with muted state
        self.update_label(True)
        self.children = self.icon, self.label

    def _connect_specific_signals(self):
        # Connect to audio service changed signal
        self.audio.connect("changed", self._on_audio_changed)

        # Connect to microphones list changes
        self.audio.connect("notify::microphones", self._on_microphones_ready)

        # Connect to default microphone changes
        self.audio.connect("notify::microphone", self._on_default_microphone_changed)

        # Initial connection to all existing microphones
        self._on_microphones_ready()

        # Defer initialization to allow services to initialize
        GLib.timeout_add(100, self._initialize_state)

    def _initialize_state(self):
        """Initialize the microphone mute state after component setup."""
        mic = self.audio.microphone
        if mic:
            is_muted = mic.muted
            self._last_muted = is_muted
            self.update_icon(is_muted)
            self.update_label(is_muted)
        return False

    def _on_microphones_ready(self, *_):
        """Called when audio microphones list changes."""
        for mic in self.audio.microphones:
            if mic not in self._connected_mics:
                mic.connect("notify::is-muted", self._on_mute_changed)
                self._connected_mics.add(mic)

    def _on_default_microphone_changed(self, *_):
        """Handle default microphone changes."""
        mic = self.audio.microphone
        if mic:
            self._on_mute_changed(mic)

    def _on_audio_changed(self, *_):
        """Handle general audio service changes."""
        mic = self.audio.microphone
        if mic:
            self._on_mute_changed(mic)

    def _on_mute_changed(self, microphone, *_):
        """Handle microphone mute changes for any microphone."""
        is_muted = microphone.muted

        # Only update and show if mute state actually changed
        if self._last_muted is None or is_muted != self._last_muted:
            self._last_muted = is_muted
            self.update_icon(is_muted)
            self.update_label(is_muted)
            self.show_microphone_osd()

    def update_icon(self, is_muted: bool):
        """Update icon based on mute state."""
        icon_name = (
            "microphone-sensitivity-muted-symbolic"
            if is_muted
            else "microphone-sensitivity-high-symbolic"
        )
        self.icon.set_from_icon_name(icon_name, 26)

        # Add style classes for styling
        self.icon.style_classes = "mic-muted" if is_muted else "mic-unmuted"

    def update_label(self, is_muted: bool):
        """Update label based on mute state."""
        self.label.set_text("Microphone MUTED" if is_muted else "Microphone ON")
        self.label.style_classes = "mic-muted" if is_muted else "mic-unmuted"

    def show_microphone_osd(self):
        """Trigger the OSD to show."""
        if self.osd:
            self.osd.show_microphone_osd()
        else:
            self.update()

    def update(self, *_):
        """Override to update display before showing OSD."""
        mic = self.audio.microphone
        if mic:
            self._last_muted = mic.muted
            self.update_icon(mic.muted)
            self.update_label(mic.muted)
        super().update()
