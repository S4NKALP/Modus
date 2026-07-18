from fabric.utils import GLib, logger, time
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

from services.modus import screen_recorder_service
from utils.gtk_utils import setup_cursor_hover, svg_file


class RecordingIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.recording_start_time = None
        self.timer_timeout_id = None

        self.recording_icon = svg_file("notch/media-record.svg", size=24)

        self.recording_button = Button(
            name="panel-button",
            child=self.recording_icon,
        )
        self.recording_button.connect("clicked", self.on_stop_recording)
        setup_cursor_hover(self.recording_button, "pointer")

        self.time_label = Label(
            name="notch-recording-time",
            markup="00:00",
            max_width_chars=5,
            ellipsize="none",
        )

        self.recording_box = CenterBox(
            orientation="h",
            h_expand=True,
            start_children=self.recording_button,
            end_children=self.time_label,
        )

        self.add(self.recording_box)

    def start_timer(self):
        if self.timer_timeout_id is not None:
            return

        self.recording_start_time = time.time()
        self._update_display()
        self.timer_timeout_id = GLib.timeout_add(1000, self._update_display)

    def stop_timer(self):
        self.recording_start_time = None

        if self.timer_timeout_id is not None:
            GLib.source_remove(self.timer_timeout_id)
            self.timer_timeout_id = None

    def _update_display(self):
        if self.recording_start_time is None:
            return False

        elapsed_seconds = int(time.time() - self.recording_start_time)
        minutes = elapsed_seconds // 60
        seconds = elapsed_seconds % 60

        self.time_label.set_markup(f"{minutes:02d}:{seconds:02d}")
        self.set_tooltip_text(
            f"Recording in progress ({minutes:02d}:{seconds:02d}) - Click to stop"
        )
        return True

    def on_stop_recording(self, *args):
        try:
            screen_recorder_service.stop()
            self.stop_timer()
        except Exception as e:
            logger.warning(f"[recording] screen_recorder_service.stop() failed: {e}")

    def destroy(self):
        self.stop_timer()
        super().destroy()
