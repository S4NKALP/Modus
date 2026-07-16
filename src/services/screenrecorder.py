"""Screen recording service.

Owns recording only; screenshots live in :mod:`services.screenshot`.
Recording state is held entirely in memory as Fabric properties -- no
temporary files are used.
"""

import shlex
import time
from datetime import datetime
from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import GLib, exec_shell_command_async

from shared.capture import (
    CaptureBackend,
    CaptureNotifier,
    CaptureResult,
    HyprlandCaptureBackend,
    RecordingRequest,
)
from utils.functions import is_app_running, resolve_monitor

_RECORDER_PROCESSES = ("wf-recorder", "gpu-screen-recorder")


class ScreenRecorder(Service):
    """Record the screen through a pluggable :class:`CaptureBackend`."""

    @Signal
    def started(self, path: str) -> None:
        """Emitted with the output path when a recording begins."""

    @Signal
    def stopped(self, path: str) -> None:
        """Emitted with the output path when a recording ends."""

    @Signal("paused")
    def paused_signal(self) -> None:
        """Emitted when an active recording is paused."""

    @Signal
    def resumed(self) -> None:
        """Emitted when a paused recording resumes."""

    @Signal
    def failed(self, reason: str) -> None:
        """Emitted when a recording is cancelled or fails."""

    _instance: "ScreenRecorder | None" = None

    def __new__(cls) -> "ScreenRecorder":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, backend: CaptureBackend | None = None, **kwargs) -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__(**kwargs)
        self._initialized = True

        self._backend = backend or HyprlandCaptureBackend()
        self._notifier = CaptureNotifier()

        self._recording = False
        self._paused = False
        self._output_file: str | None = None
        self._start_time: float | None = None
        self._tick_source_id: int | None = None

        self.recordings_dir = Path.home() / "Videos" / "Recordings"
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

    # -- properties --------------------------------------------------------

    @Property(bool, "readable", default_value=False)
    def recording(self) -> bool:
        """In-memory recording state managed by this service."""
        return self._recording

    @Property(bool, "readable", default_value=False)
    def paused(self) -> bool:
        """Whether the current recording is paused."""
        return self._paused

    @Property(int, "readable", default_value=0)
    def elapsed_seconds(self) -> int:
        """Seconds elapsed since the current recording started."""
        if self._start_time is None:
            return 0
        return int(time.monotonic() - self._start_time)

    @Property(str, "readable", default_value="")
    def output_file(self) -> str:
        """Path of the current or most recent recording."""
        return self._output_file or ""

    @Property(str, "readable", default_value="")
    def backend(self) -> str:
        """Name of the active capture backend."""
        return self._backend.name

    @Property(bool, "readable", default_value=False)
    def busy(self) -> bool:
        """Whether a recording is active (in-memory state)."""
        return self._recording

    @Property(bool, "readable", default_value=False)
    def available(self) -> bool:
        """Whether the backend can record on this system."""
        return self._backend.capabilities.can_record

    @Property(bool, "readable", default_value=False)
    def supports_pause(self) -> bool:
        """Whether the backend supports pause/resume."""
        return self._backend.capabilities.supports_pause

    @Property(bool, "readable", default_value=False)
    def active(self) -> bool:
        """Whether a recorder process is actually running.

        Unlike :attr:`recording`, this reflects the real process state and
        also detects recordings started outside this service.
        """
        return any(is_app_running(proc) for proc in _RECORDER_PROCESSES)

    # -- public API --------------------------------------------------------

    def start(
        self,
        target: str = "selection",
        use_audio: bool = False,
        show_cursor: bool = False,
    ) -> bool:
        """Start a recording.

        :param target: ``selection``, ``active`` or a specific monitor name.
        :param use_audio: capture audio.
        :param show_cursor: show the mouse cursor in the recording.
        :returns: ``True`` if the recording attempt was launched.
        """
        if self.active:
            self.failed("A recording is already running")
            return False
        if not self._backend.capabilities.can_record:
            self.failed("Recording backend is unavailable")
            return False

        request = self._build_request(target, use_audio, show_cursor)
        return self._backend.start_recording(request, self._on_start_result)

    def stop(self) -> bool:
        """Stop the active recording."""
        if not (self._recording or self.active):
            return False
        path = self._output_file
        self._backend.stop_recording()
        self._teardown_state()
        if path:
            self._notify_saved(path)
            self.stopped(path)
        return True

    def pause(self) -> bool:
        """Pause the active recording, if the backend supports it."""
        if not self._recording or self._paused:
            return False
        if not self._backend.pause_recording():
            return False
        self._paused = True
        self.notify("paused")
        self.paused_signal()
        return True

    def resume(self) -> bool:
        """Resume a paused recording, if the backend supports it."""
        if not self._recording or not self._paused:
            return False
        if not self._backend.resume_recording():
            return False
        self._paused = False
        self.notify("paused")
        self.resumed()
        return True

    def toggle(self) -> bool:
        """Stop when recording, otherwise start with defaults."""
        if self._recording or self.active:
            return self.stop()
        return self.start()

    # -- internals ---------------------------------------------------------

    def _build_request(
        self, target: str, use_audio: bool, show_cursor: bool
    ) -> RecordingRequest:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return RecordingRequest(
            target=target,
            output_file=self.recordings_dir / f"{timestamp}.mkv",
            use_audio=use_audio,
            show_cursor=show_cursor,
            monitor=resolve_monitor(target),
        )

    def _on_start_result(self, result: CaptureResult) -> None:
        if result.success and result.path:
            self._setup_state(result.path)
            self.started(result.path)
        elif result.cancelled:
            self._notify_cancelled()
            self.failed("cancelled")
        else:
            self.failed(result.error or "Recording failed")

    def _setup_state(self, path: str) -> None:
        self._output_file = path
        self._recording = True
        self._paused = False
        self._start_time = time.monotonic()
        self._start_tick()
        self.notify("output-file")
        self.notify("recording")
        self.notify("busy")

    def _teardown_state(self) -> None:
        self._stop_tick()
        self._recording = False
        self._paused = False
        self._start_time = None
        self.notify("recording")
        self.notify("busy")
        self.notify("elapsed-seconds")

    def _start_tick(self) -> None:
        self._stop_tick()
        self._tick_source_id = GLib.timeout_add_seconds(1, self._on_tick)

    def _stop_tick(self) -> None:
        if self._tick_source_id is not None:
            GLib.source_remove(self._tick_source_id)
            self._tick_source_id = None

    def _on_tick(self) -> bool:
        if not self._recording:
            self._tick_source_id = None
            return False
        self.notify("elapsed-seconds")
        return True

    def _notify_saved(self, path: str) -> None:
        self._notifier.notify(
            "Screencast Saved",
            f"Saved Screencast at {path}",
            icon="camera-video-symbolic",
            actions=[("files", "Show in Files"), ("view", "View")],
            on_action=lambda action: self._handle_action(action, path),
        )

    def _handle_action(self, action: str, path: str) -> None:
        match action:
            case "files":
                exec_shell_command_async(
                    f"xdg-open {shlex.quote(str(self.recordings_dir))}"
                )
            case "view":
                exec_shell_command_async(f"xdg-open {shlex.quote(path)}")

    def _notify_cancelled(self) -> None:
        self._notifier.notify(
            "Recording cancelled",
            "Selection was cancelled",
            icon="camera-video-symbolic",
        )
