import os
import subprocess
import time

from gi.repository import GLib

from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.svg import Svg


class RecordingIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", visible=False, **kwargs)

        self.script_path = get_relative_path("../../../scripts/screen-capture.sh")
        self.recording_start_time = None
        self.last_process_check = 0
        self.process_check_interval = 1.0
        self.timer_update_interval = 1000
        self.status_check_interval = 2000

        self.timer_timeout_id = None
        self.status_timeout_id = None

        self.recording_icon = Svg(
            name="indicators-icon",
            size=24,
            svg_file=get_relative_path("../../../config/assets/icons/misc/media-record.svg"),
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
        self.connect("button-press-event", self.on_button_press)
        self.hide()

        GLib.timeout_add(100, self._delayed_init)

    def on_button_press(self, *args):
        GLib.timeout_add(100, lambda: self.remove_style_class("pressed") or False)
        return False

    def is_wf_recorder_running(self):
        try:
            result = subprocess.run(
                ["pgrep", "-x", "wf-recorder"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            return result.returncode == 0
        except Exception:
            return False

    def check_recording_status(self):
        current_time = time.time()
        self.last_process_check = current_time

        try:
            is_recording = self.is_wf_recorder_running()

            if is_recording:
                if not self.get_visible():
                    self.set_visible(True)
                    if self.timer_timeout_id is None:
                        self.timer_timeout_id = GLib.timeout_add(
                            self.timer_update_interval, self.update_timer_display
                        )

                if self.recording_start_time is None:
                    self.recording_start_time = self.get_recording_start_time()

                self.update_timer_display()
            else:
                if self.get_visible():
                    self.set_visible(False)
                    self.cleanup_recording_state()

        except Exception as e:
            print(f"[DEBUG] Error checking recording status: {e}")
            if self.get_visible():
                self.set_visible(False)
                self.cleanup_recording_state()

        return True

    def update_timer_display(self):
        if not self.get_visible() or self.recording_start_time is None:
            return False

        try:
            elapsed_seconds = int(time.time() - self.recording_start_time)
            minutes = elapsed_seconds // 60
            seconds = elapsed_seconds % 60
            time_text = f"{minutes:02d}:{seconds:02d}"

            self.time_label.set_markup(time_text)
            self.set_tooltip_text(
                f"Recording in progress ({time_text}) - Click to stop"
            )

            return True
        except Exception as e:
            print(f"[DEBUG] Error updating timer display: {e}")
            return False

    def cleanup_recording_state(self):
        self.recording_start_time = None

        if self.timer_timeout_id:
            GLib.source_remove(self.timer_timeout_id)
            self.timer_timeout_id = None

    def get_recording_start_time(self):
        start_time_file = "/tmp/recording_start_time.txt"

        try:
            if not os.path.exists(start_time_file):
                return None

            file_mtime = os.path.getmtime(start_time_file)

            with open(start_time_file, "r") as f:
                content = f.read().strip()
                if content:
                    recorded_time = float(content)

                    current_time = time.time()
                    if abs(recorded_time - current_time) > 3600:
                        return file_mtime

                    return recorded_time
                else:
                    return file_mtime

        except (ValueError, OSError):
            try:
                return os.path.getmtime(start_time_file)
            except OSError:
                return None

    def on_stop_recording(self, *args):
        try:
            self.set_visible(False)
            self.cleanup_recording_state()

            def send_stop_command():
                try:
                    subprocess.Popen(
                        [self.script_path, "record", "stop"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception as e:
                    print(f"[DEBUG] Error sending stop command: {e}")

            GLib.idle_add(send_stop_command)
            GLib.timeout_add(500, self._verify_recording_stopped)
            GLib.timeout_add(1500, self._verify_recording_stopped)
            GLib.timeout_add(3000, self._verify_recording_stopped)

        except Exception:
            self.set_visible(False)
            self.cleanup_recording_state()

    def _verify_recording_stopped(self):
        try:
            if self.is_wf_recorder_running():
                if self.recording_start_time is None:
                    self.recording_start_time = self.get_recording_start_time()

                if self.recording_start_time:
                    self.set_visible(True)
                    self.update_timer_display()

                    if self.timer_timeout_id is None:
                        self.timer_timeout_id = GLib.timeout_add(
                            self.timer_update_interval, self.update_timer_display
                        )

            else:
                self.set_visible(False)
                self.cleanup_recording_state()

        except Exception:
            self.set_visible(False)
            self.cleanup_recording_state()

        return False

    def _delayed_init(self):
        try:
            self.check_recording_status()
            self.status_timeout_id = GLib.timeout_add(
                self.status_check_interval, self.check_recording_status
            )

        except Exception as e:
            print(f"[DEBUG] Error in delayed recording indicator init: {e}")
        return False

    def destroy(self):
        if self.timer_timeout_id:
            GLib.source_remove(self.timer_timeout_id)
            self.timer_timeout_id = None

        if self.status_timeout_id:
            GLib.source_remove(self.status_timeout_id)
            self.status_timeout_id = None

        super().destroy()
