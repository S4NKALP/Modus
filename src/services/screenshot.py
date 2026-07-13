"""Screenshot service.

Owns screenshot capture only; recording lives in
:mod:`services.screenrecorder`.  The service resolves the desired target
into a concrete request, hands it to a :class:`CaptureBackend`, then raises
notifications and signals based on the result.
"""

from datetime import datetime
from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import exec_shell_command_async

from shared.capture import (
    CaptureBackend,
    CaptureNotifier,
    CaptureResult,
    HyprlandCaptureBackend,
    ScreenshotRequest,
)
from utils.functions import find_binary


class Screenshot(Service):
    """Capture screenshots through a pluggable :class:`CaptureBackend`."""

    @Signal
    def captured(self, path: str) -> None:
        """Emitted with the saved path when a screenshot succeeds."""

    @Signal
    def failed(self, reason: str) -> None:
        """Emitted when a screenshot is cancelled or fails."""

    _instance: "Screenshot | None" = None

    def __new__(cls) -> "Screenshot":
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
        self._busy = False
        self._last_file: str | None = None
        self._has_satty = find_binary("satty") is not None

        self.screenshots_dir = Path.home() / "Pictures" / "Screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    # -- properties --------------------------------------------------------

    @Property(bool, "readable", default_value=False)
    def busy(self) -> bool:
        """Whether a capture is currently in progress."""
        return self._busy

    @Property(str, "readable", default_value="")
    def last_file(self) -> str:
        """Path of the most recently captured screenshot."""
        return self._last_file or ""

    @Property(str, "readable", default_value="")
    def backend(self) -> str:
        """Name of the active capture backend."""
        return self._backend.name

    @Property(bool, "readable", default_value=False)
    def available(self) -> bool:
        """Whether the backend can take screenshots on this system."""
        return self._backend.capabilities.can_screenshot

    @Property(bool, "readable", default_value=False)
    def can_edit(self) -> bool:
        """Whether an external editor (``satty``) is available."""
        return self._has_satty

    # -- public API --------------------------------------------------------

    def screenshot(
        self,
        target: str = "region",
        output_dir: str | Path | None = None,
        show_cursor: bool = False,
    ) -> bool:
        """Take a screenshot.

        :param target: ``region``, ``window``, ``active``, ``output`` or a
            specific monitor name.
        :param output_dir: destination directory; defaults to the standard
            screenshots directory.
        :param show_cursor: include the mouse cursor in the capture.
        :returns: ``True`` if the capture attempt was launched.
        """
        if not self._backend.capabilities.can_screenshot:
            self._fail("Screenshot backend is unavailable")
            return False

        request = self._build_request(target, output_dir, show_cursor)
        self._set_busy(True)
        launched = self._backend.screenshot(request, self._on_result)
        if not launched:
            self._set_busy(False)
        return launched

    # -- internals ---------------------------------------------------------

    def _build_request(
        self, target: str, output_dir: str | Path | None, show_cursor: bool
    ) -> ScreenshotRequest:
        save_dir = Path(output_dir).expanduser() if output_dir else self.screenshots_dir
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        monitor = self._resolve_monitor(target)
        return ScreenshotRequest(
            target=target,
            save_path=save_dir / f"{timestamp}.png",
            show_cursor=show_cursor,
            monitor=monitor,
        )

    @staticmethod
    def _resolve_monitor(target: str) -> str | None:
        if target != "active":
            return None
        from services.modus import get_active_monitor_name

        return get_active_monitor_name()

    def _on_result(self, result: CaptureResult) -> None:
        self._set_busy(False)
        if result.success and result.path:
            self._on_success(result.path)
        elif result.cancelled:
            self._notify_cancelled()
            self.failed("cancelled")
        else:
            self._fail(result.error or "Screenshot failed")

    def _on_success(self, path: str) -> None:
        self._last_file = path
        self.notify("last-file")
        self._notify_saved(path)
        self.captured(path)

    def _notify_saved(self, path: str) -> None:
        actions = [("files", "Show in Files"), ("view", "View")]
        if self._has_satty:
            actions.append(("edit", "Edit"))
        self._notifier.notify(
            "Screenshot Saved",
            f"Saved Screenshot at {path}",
            icon="camera-photo-symbolic",
            actions=actions,
            hints=[f"STRING:image-path:{path}"],
            on_action=lambda action: self._handle_action(action, path),
        )

    def _handle_action(self, action: str, path: str) -> None:
        match action:
            case "files":
                exec_shell_command_async(f"xdg-open {self.screenshots_dir}")
            case "view":
                exec_shell_command_async(f"xdg-open {path}")
            case "edit":
                exec_shell_command_async(f"satty -f {path}")

    def _notify_cancelled(self) -> None:
        self._notifier.notify(
            "Screenshot cancelled",
            "Selection was cancelled",
            icon="camera-photo-symbolic",
        )

    def _fail(self, reason: str) -> None:
        self.failed(reason)

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.notify("busy")
