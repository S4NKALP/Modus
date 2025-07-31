import subprocess
import time

from gi.repository import GLib

from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.svg import Svg

# FIX: Make the timer consistent with the recording start time


class RecordingIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", visible=False, **kwargs)

        self.script_path = get_relative_path("../../../scripts/screen-capture.sh")
        self.recording_start_time = None

        self.recording_icon = Svg(
            name="indicators-icon",
            size=24,
            svg_file=get_relative_path("../../../config/assets/icons/media-record.svg"),
        )
        self.time_label = Label(
            name="recording-time-label",
            markup="00:00",
            max_width_chars=5,
            ellipsize="none",
        )

        self.recording_box = Box(
            orientation="h",
            spacing=2,
            children=[self.recording_icon, self.time_label],
            size=(80, -1),
        )

        self.add(self.recording_box)

        self.connect("clicked", self.on_stop_recording)
        self.hide()

        GLib.timeout_add(1, self._delayed_init)

    def check_recording_status(self):
        try:
            result = subprocess.run(
                [self.script_path, "status"], capture_output=True, text=True, timeout=2
            )
            is_recording = result.stdout.strip() == "true"

            if is_recording:
                if not self.get_visible():
                    self.show()

                # Get the recording start time if we don't have it
                if self.recording_start_time is None:
                    self.recording_start_time = self.get_recording_start_time()

                # Update the recording time display
                if self.recording_start_time:
                    elapsed_seconds = int(time.time() - self.recording_start_time)
                    minutes = elapsed_seconds // 60
                    seconds = elapsed_seconds % 60
                    time_text = f"{minutes:02d}:{seconds:02d}"
                    self.time_label.set_markup(time_text)
                    self.set_tooltip_text(
                        f"Recording in progress ({minutes:02d}:{
                            seconds:02d}) - Click to stop"
                    )
                else:
                    self.set_tooltip_text("Recording in progress - Click to stop")
            else:
                if self.get_visible():
                    self.hide()
                    self.recording_start_time = None

        except Exception:
            # If we can't check status, hide the indicator
            if self.get_visible():
                self.hide()
                self.recording_start_time = None

        return True  # Continue the timeout

    def get_recording_start_time(self):
        """Get the recording start time from the file"""
        try:
            with open("/tmp/recording_start_time.txt", "r") as f:
                return float(f.read().strip())
        except Exception:
            return None

    def on_stop_recording(self, *args):
        try:
            subprocess.Popen([self.script_path, "record", "stop"])
        except Exception as e:
            print(f"Error stopping recording: {e}")

    def _delayed_init(self):
        try:
            self.check_recording_status()
            self.timeout_id = GLib.timeout_add(5000, self.check_recording_status)
        except Exception as e:
            print(f"[DEBUG] Error in delayed recording indicator init: {e}")
        return False  # Don't repeat this timeout
