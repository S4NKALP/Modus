"""Backwards-compatible facade over the split capture services.

The screenshot and recording logic now live in :mod:`services.screenshot`
and :mod:`services.screenrecorder`.  This module keeps the historical
``ScreenCapture`` API and its ``screenshot-taken`` / ``recording-started``
/ ``recording-stopped`` signals so existing widgets keep working while new
code can depend on the focused services directly.
"""

from pathlib import Path

from fabric.core.service import Property, Service, Signal

from services.screenrecorder import ScreenRecorder
from services.screenshot import Screenshot


class ScreenCapture(Service):
    """Facade delegating to :class:`Screenshot` and :class:`ScreenRecorder`."""

    @Signal
    def screenshot_taken(self, path: str) -> None:
        """Emitted after a screenshot attempt (``None`` path on cancel/fail)."""

    @Signal
    def recording_started(self, path: str) -> None:
        """Emitted when a recording starts."""

    @Signal
    def recording_stopped(self, path: str) -> None:
        """Emitted when a recording stops."""

    _instance: "ScreenCapture | None" = None

    def __new__(cls) -> "ScreenCapture":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs) -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__(**kwargs)
        self._initialized = True

        self._screenshot = Screenshot()
        self._recorder = ScreenRecorder()

        self.screenshots_dir = self._screenshot.screenshots_dir
        self.recordings_dir = self._recorder.recordings_dir

        self._screenshot.connect("captured", self._on_captured)
        self._screenshot.connect("failed", self._on_screenshot_failed)
        self._recorder.connect("started", self._on_recording_started)
        self._recorder.connect("stopped", self._on_recording_stopped)

    @property
    def screenshot_service(self) -> Screenshot:
        """The underlying screenshot service."""
        return self._screenshot

    @property
    def recorder_service(self) -> ScreenRecorder:
        """The underlying recorder service."""
        return self._recorder

    def screenshot(
        self,
        target: str = "region",
        output_dir: str | Path | None = None,
        show_cursor: bool = False,
    ) -> bool:
        """Take a screenshot. See :meth:`Screenshot.screenshot`."""
        return self._screenshot.screenshot(
            target, output_dir=output_dir, show_cursor=show_cursor
        )

    def record(
        self,
        target: str = "selection",
        use_audio: bool = False,
        show_cursor: bool = False,
    ) -> bool:
        """Start a recording. See :meth:`ScreenRecorder.start`."""
        return self._recorder.start(
            target, use_audio=use_audio, show_cursor=show_cursor
        )

    def stop_recording(self) -> bool:
        """Stop the active recording."""
        return self._recorder.stop()

    @Property(bool, "readable", default_value=False)
    def is_recording(self) -> bool:
        """Whether a recorder process is currently running."""
        return self._recorder.active

    def _on_captured(self, _service: Screenshot, path: str) -> None:
        self.screenshot_taken(path)

    def _on_screenshot_failed(self, _service: Screenshot, _reason: str) -> None:
        self.screenshot_taken(None)

    def _on_recording_started(self, _service: ScreenRecorder, path: str) -> None:
        self.recording_started(path)

    def _on_recording_stopped(self, _service: ScreenRecorder, path: str) -> None:
        self.recording_stopped(path)


def __getattr__(name: str):
    if name == "screen_capture_service":
        import sys

        return sys.modules["services.modus"].screen_capture_service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
