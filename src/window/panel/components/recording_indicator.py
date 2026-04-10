from fabric.utils import GLib, os, time
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from services.screencapture import screen_capture_service

from utils.utils import setup_cursor_hover, svg_file


class RecordingIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", visible=True, **kwargs)

        self.recording_start_time = None
        self.last_process_check = 0
        self.process_check_interval = 1.0
        self.timer_update_interval = 1000
        self.status_check_interval = 2000

        self.timer_timeout_id = None
        self.status_timeout_id = None

        self.recording_icon = svg_file("misc/media-record.svg", size=24)

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

        # Prevent container.show_all() from forcing this visible when no recording
        try:
            self.set_no_show_all(True)
        except Exception:
            pass

        self.connect("clicked", self.on_stop_recording)
        try:
            setup_cursor_hover(self, "pointer")
        except Exception:
            pass
        self.connect("button-press-event", self.on_button_press)
        self.set_visible(False)

        GLib.timeout_add(100, self._delayed_init)

    def on_button_press(self, *args):
        GLib.timeout_add(100, lambda: self.remove_style_class("pressed") or False)
        return False

    def is_recorder_running(self):
        return screen_capture_service.is_recording

    def check_recording_status(self):
        current_time = time.time()
        self.last_process_check = current_time

        try:
            is_recording = self.is_recorder_running()

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
                # Ensure it stays hidden when not recording
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
        wf_file = "/tmp/recording_start_time.txt"
        gpu_file = "/tmp/gpu_recording_start_time.txt"

        def read_timestamp(path):
            try:
                with open(path, "r") as f:
                    content = f.read().strip()
                    if content:
                        t = float(content)
                        if abs(t - time.time()) <= 3600:
                            return t
                    return os.path.getmtime(path)
            except (OSError, ValueError):
                return None

        if os.path.exists(wf_file):
            t = read_timestamp(wf_file)
            if t:
                print("[DEBUG] Using wf-recorder start time")
                return t

        if os.path.exists(gpu_file):
            t = read_timestamp(gpu_file)
            if t:
                print("[DEBUG] Using gpu-screen-recorder start time")
                return t

        print("[DEBUG] No start time file found, using current time")
        return time.time()

    def on_stop_recording(self, *args):
        try:
            self.set_visible(False)
            self.cleanup_recording_state()
            screen_capture_service.stop_recording()

            GLib.timeout_add(500, self._verify_recording_stopped)
            GLib.timeout_add(1500, self._verify_recording_stopped)
            GLib.timeout_add(3000, self._verify_recording_stopped)

        except Exception:
            self.set_visible(False)
            self.cleanup_recording_state()

    def _verify_recording_stopped(self):
        try:
            if self.is_recorder_running():
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
