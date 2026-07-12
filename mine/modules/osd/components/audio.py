from fabric.widgets.image import Image
from fabric.widgets.scale import ScaleMark
from fabric.widgets.wayland import WaylandWindow as Window

from modules.osd.components.animated_scale import AnimatedScale
from modules.osd.components.base import BaseOSDContainer
from services import Audio


class AudioOSDContainer(BaseOSDContainer):
    def __init__(self, window: Window, **kwargs):
        super().__init__(window, **kwargs)
        self.audio = Audio(controller_name="fabric-osd")
        self._last_volume = None
        self._last_muted = None
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.icon = Image(icon_name="audio-volume-medium-symbolic", icon_size=26)
        self.scale = AnimatedScale(
            marks=(ScaleMark(value=i) for i in range(1, 100, 10)),
            value=70,
            min_value=0,
            max_value=100,
            inverted=False,
            increments=(1, 1),
            orientation=self.get_orientation(),
            on_state_flags_changed=lambda sc, *_: (
                self.unfocus() if not (sc.get_state_flags() & 2) else None,
            ),
            on_value_changed=lambda *_: self.is_hovered()
            and self._on_user_volume_change(),
        )
        self.children = self.icon, self.scale

    def _connect_specific_signals(self):
        # Connect to audio service changed signal (catches all audio changes including mute)
        self.audio.connect("changed", self._on_audio_changed)

        self.audio.connect(
            "notify::speaker",
            self._on_speaker_ready,
        )

        # If speaker already exists, connect now
        if self.audio.speaker:
            self._on_speaker_ready()

    def _on_speaker_ready(self, *_):
        """Called when audio speaker is ready."""
        speaker = self.audio.speaker
        if not speaker:
            return

        # Initialize state
        self._last_volume = round(speaker.volume)
        self._last_muted = speaker.muted

        # Connect to speaker signals
        speaker.connect("notify::volume", self._on_volume_changed)
        speaker.connect("notify::is-muted", self._on_mute_changed)

        # Initial update
        self.scale.animate_value(speaker.volume)
        self._update_volume_display()

    def _on_audio_changed(self, *_):
        """Handle general audio service changes (includes mute changes)."""
        if not self.audio.speaker:
            return

        # Check if mute state changed
        current_muted = self.audio.speaker.muted
        if self._last_muted is None or current_muted != self._last_muted:
            self._last_muted = current_muted
            self._update_volume_display()
            # Trigger parent OSD to show
            if self.osd:
                self.osd.show_audio_osd()

    def _on_volume_changed(self, speaker, *_):
        """Handle volume changes from the system."""
        if not speaker or self.is_hovered():
            # User is dragging slider, don't update
            return

        new_volume = round(speaker.volume)

        # Only animate if volume actually changed
        if self._last_volume is None or abs(new_volume - self._last_volume) > 0:
            self._last_volume = new_volume
            self.scale.animate_value(new_volume)
            self._update_volume_display(new_volume)
            # Trigger parent OSD to show
            if self.osd:
                self.osd.show_audio_osd()

    def _on_mute_changed(self, speaker, *_):
        """Handle mute state changes."""
        if not speaker:
            return

        new_muted = speaker.muted

        # Only update if mute state changed
        if self._last_muted is None or self._last_muted != new_muted:
            self._last_muted = new_muted
            self._update_volume_display()
            # Trigger parent OSD to show
            if self.osd:
                self.osd.show_audio_osd()

    def _on_user_volume_change(self):
        """Called when user drags the slider."""
        if not self.audio.speaker or not self.is_hovered():
            return

        new_volume = self.scale.value
        self.audio.speaker.set_volume(new_volume)
        self._last_volume = round(new_volume)
        self._update_volume_display(new_volume)

    def _update_volume_display(self, volume=None):
        """Update icon and scale styling based on volume and mute state."""
        if not self.audio.speaker:
            return

        current_volume = (
            round(self.audio.speaker.volume) if volume is None else round(volume)
        )
        is_muted = self.audio.speaker.muted

        # Update muted styling
        if is_muted or current_volume == 0:
            self.scale.add_style_class("muted")
            self.icon.set_from_icon_name("audio-volume-muted-symbolic", 26)
        else:
            self.scale.remove_style_class("muted")
            # Update icon based on volume level
            if current_volume >= 80:
                icon_name = "audio-volume-high-symbolic"
            elif current_volume < 50:
                icon_name = "audio-volume-low-symbolic"
            else:
                icon_name = "audio-volume-medium-symbolic"

            self.icon.set_from_icon_name(icon_name, 26)

    def update(self, *_):
        """Override to update display before showing OSD."""
        # Update the display with current speaker state
        if self.audio.speaker:
            speaker = self.audio.speaker
            self._last_volume = round(speaker.volume)
            self._last_muted = speaker.muted
            self.scale.animate_value(speaker.volume)
            self._update_volume_display()

        # Call parent's update to show the OSD
        super().update()
