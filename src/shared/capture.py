"""Shared capture infrastructure: backend abstraction + notifications.

Services never invoke capture tools (``hyprshot``, ``grim``, ``slurp``,
``wf-recorder``) directly.  They speak only to a :class:`CaptureBackend`,
which encapsulates the concrete tooling.  This makes it possible to add
alternative backends (GPU Screen Recorder, PipeWire, XDG Desktop Portal)
later without touching the services or the UI.

:class:`CaptureNotifier` provides the reusable ``notify-send`` plumbing used
by both the screenshot and recorder services so the notification code is not
duplicated in each.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Iterable

from fabric.utils import Gio, logger

from utils.functions import find_binary, kill_process

if TYPE_CHECKING:
    from pathlib import Path

ResultCallback = Callable[["CaptureResult"], None]
NotificationAction = tuple[str, str]
ActionCallback = Callable[[str], None]


@dataclass(slots=True)
class CaptureResult:
    """Outcome of a capture operation reported back to a service."""

    success: bool
    path: str | None = None
    cancelled: bool = False
    error: str | None = None

    @classmethod
    def ok(cls, path: str) -> CaptureResult:
        return cls(success=True, path=path)

    @classmethod
    def user_cancelled(cls) -> CaptureResult:
        return cls(success=False, cancelled=True)

    @classmethod
    def failure(cls, error: str) -> CaptureResult:
        return cls(success=False, error=error)


@dataclass(slots=True)
class ScreenshotRequest:
    """Description of a single screenshot to capture.

    :param target: ``region``, ``window``, ``active``, ``output`` or a
        specific monitor name.
    :param save_path: absolute path the resulting image is written to.
    :param show_cursor: whether the mouse cursor is included.
    :param monitor: resolved monitor name (used for ``active`` / ``output``).
    """

    target: str
    save_path: Path
    show_cursor: bool = False
    monitor: str | None = None


@dataclass(slots=True)
class RecordingRequest:
    """Description of a screen recording to start.

    :param target: ``selection``, ``active`` or a specific monitor name.
    :param output_file: absolute path the recording is written to.
    :param use_audio: whether audio is captured.
    :param show_cursor: whether the mouse cursor is recorded.
    :param monitor: resolved monitor name (used for ``active``).
    """

    target: str
    output_file: Path
    use_audio: bool = False
    show_cursor: bool = False
    monitor: str | None = None


@dataclass(slots=True)
class BackendCapabilities:
    """Static description of what a backend can do on this system."""

    tools: dict[str, bool] = field(default_factory=dict)
    can_screenshot: bool = False
    can_record: bool = False
    supports_cursor: bool = False
    supports_pause: bool = False


class CaptureBackend(ABC):
    """Abstract capture/recording backend.

    Concrete backends translate high level requests into whatever tooling
    they wrap and report the outcome through the supplied callback.
    """

    name: str = "abstract"

    @property
    @abstractmethod
    def capabilities(self) -> BackendCapabilities:
        """Return the static capabilities of this backend."""

    @abstractmethod
    def screenshot(self, request: ScreenshotRequest, on_result: ResultCallback) -> bool:
        """Capture a screenshot; return ``True`` if the attempt was launched."""

    @abstractmethod
    def start_recording(
        self, request: RecordingRequest, on_result: ResultCallback
    ) -> bool:
        """Begin a recording; return ``True`` if the attempt was launched."""

    @abstractmethod
    def stop_recording(self) -> bool:
        """Stop the active recording; return ``True`` if one was stopped."""

    def pause_recording(self) -> bool:
        """Pause the active recording. Unsupported by default."""
        return False

    def resume_recording(self) -> bool:
        """Resume a paused recording. Unsupported by default."""
        return False


class HyprlandCaptureBackend(CaptureBackend):
    """Capture backend built on ``hyprshot``, ``grim``, ``slurp`` and
    ``wf-recorder`` for Hyprland/wlroots sessions."""

    name = "hyprland"

    _RECORDER = "wf-recorder"

    def __init__(self) -> None:
        self._tools = {
            tool: find_binary(tool) is not None
            for tool in ("hyprshot", "grim", "slurp", self._RECORDER)
        }

    @property
    def capabilities(self) -> BackendCapabilities:
        tools = self._tools
        return BackendCapabilities(
            tools=dict(tools),
            can_screenshot=tools.get("hyprshot", False) or tools.get("grim", False),
            can_record=tools.get(self._RECORDER, False),
            supports_cursor=tools.get("grim", False),
            supports_pause=False,
        )

    def has_tool(self, tool: str) -> bool:
        """Return whether a wrapped tool is available on this system."""
        return self._tools.get(tool, False)

    # screenshots

    def screenshot(self, request: ScreenshotRequest, on_result: ResultCallback) -> bool:
        request.save_path.parent.mkdir(parents=True, exist_ok=True)
        if request.show_cursor and request.target in ("region", "active", "output"):
            return self._screenshot_with_cursor(request, on_result)
        return self._screenshot_hyprshot(request, on_result)

    def _screenshot_hyprshot(
        self, request: ScreenshotRequest, on_result: ResultCallback
    ) -> bool:
        if not self.has_tool("hyprshot"):
            on_result(CaptureResult.failure("hyprshot is not installed"))
            return False

        command = [
            "hyprshot",
            "-s",
            "-o",
            str(request.save_path.parent),
            "-f",
            request.save_path.name,
            *self._hyprshot_mode(request),
        ]
        return self._spawn_capture(command, request.save_path, on_result)

    @staticmethod
    def _hyprshot_mode(request: ScreenshotRequest) -> list[str]:
        target = request.target
        if target == "region":
            return ["-m", "region"]
        if target == "window":
            return ["-m", "window"]
        if target == "active":
            return ["-m", "output", "-m", request.monitor or ""]
        if target == "output":
            return ["-m", "output"]
        return ["-m", "output", "-m", target]

    def _screenshot_with_cursor(
        self, request: ScreenshotRequest, on_result: ResultCallback
    ) -> bool:
        if not self.has_tool("grim"):
            on_result(CaptureResult.failure("grim is not installed"))
            return False

        if request.target == "region":
            return self._region_with_cursor(request, on_result)

        monitor = request.monitor if request.target == "active" else None
        return self._grim_capture(request.save_path, on_result, monitor=monitor)

    def _region_with_cursor(
        self, request: ScreenshotRequest, on_result: ResultCallback
    ) -> bool:
        def on_geometry(geometry: str | None) -> None:
            if not geometry:
                on_result(CaptureResult.user_cancelled())
                return
            self._grim_capture(request.save_path, on_result, geometry=geometry)

        return self._select_geometry(on_geometry)

    def _grim_capture(
        self,
        save_path: Path,
        on_result: ResultCallback,
        geometry: str | None = None,
        monitor: str | None = None,
    ) -> bool:
        command = ["grim", "-c"]
        if geometry:
            command += ["-g", geometry]
        elif monitor:
            command += ["-o", monitor]
        command.append(str(save_path))
        return self._spawn_capture(command, save_path, on_result)

    def _spawn_capture(
        self, command: list[str], expected: Path, on_result: ResultCallback
    ) -> bool:
        def on_done(proc: Gio.Subprocess, task: Gio.Task) -> None:
            try:
                proc.wait_finish(task)
            except Exception as error:
                logger.warning(f"[capture] proc.wait_finish(task) failed: {error}")
                on_result(CaptureResult.failure(str(error)))
                return
            if expected.exists():
                on_result(CaptureResult.ok(str(expected)))
            else:
                on_result(CaptureResult.user_cancelled())

        proc = self._spawn(command, Gio.SubprocessFlags.STDERR_SILENCE)
        if proc is None:
            on_result(CaptureResult.failure(f"failed to launch {command[0]}"))
            return False
        proc.wait_async(None, on_done)
        return True

    # recording

    def start_recording(
        self, request: RecordingRequest, on_result: ResultCallback
    ) -> bool:
        if not self.has_tool(self._RECORDER):
            on_result(CaptureResult.failure(f"{self._RECORDER} is not installed"))
            return False
        request.output_file.parent.mkdir(parents=True, exist_ok=True)

        if request.target == "selection":
            return self._record_geometry(request, on_result, self._select_geometry)
        if request.target == "window":
            return self._record_geometry(request, on_result, self._select_window)

        monitor = request.monitor or request.target
        return self._launch_recorder(request, on_result, monitor=monitor)

    def _record_geometry(
        self,
        request: RecordingRequest,
        on_result: ResultCallback,
        selector: Callable[[Callable[[str | None], None]], bool],
    ) -> bool:
        def on_geometry(geometry: str | None) -> None:
            if not geometry:
                on_result(CaptureResult.user_cancelled())
                return
            self._launch_recorder(request, on_result, geometry=geometry)

        return selector(on_geometry)

    def _launch_recorder(
        self,
        request: RecordingRequest,
        on_result: ResultCallback,
        geometry: str | None = None,
        monitor: str | None = None,
    ) -> bool:
        command = [
            self._RECORDER,
            "--file",
            str(request.output_file),
            "--pixel-format",
            "yuv420p",
        ]
        if not request.use_audio:
            command.append("--no-audio")
        if request.show_cursor:
            command.append("--show-cursor")
        if geometry:
            command += ["-g", geometry]
        elif monitor:
            command += ["-o", monitor]

        proc = self._spawn(command, Gio.SubprocessFlags.NONE)
        if proc is None:
            on_result(CaptureResult.failure(f"failed to launch {self._RECORDER}"))
            return False
        on_result(CaptureResult.ok(str(request.output_file)))
        return True

    def stop_recording(self) -> bool:
        kill_process(self._RECORDER)
        return True

    # helpers

    def _select_geometry(self, on_geometry: Callable[[str | None], None]) -> bool:
        if not self.has_tool("slurp"):
            on_geometry(None)
            return False

        def on_done(proc: Gio.Subprocess, task: Gio.Task) -> None:
            try:
                _, stdout, _ = proc.communicate_utf8_finish(task)
            except Exception as e:
                logger.warning(
                    f"[capture] _, stdout, _ = proc.communicate_utf8_finish(task) failed: {e}"
                )
                on_geometry(None)
                return
            on_geometry(stdout.strip() if stdout else None)

        proc = self._spawn(
            ["slurp"],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
        )
        if proc is None:
            on_geometry(None)
            return False
        proc.communicate_utf8_async(None, None, on_done)
        return True

    def _select_window(self, on_geometry: Callable[[str | None], None]) -> bool:
        """Let the user pick a visible window and return its geometry.

        Mirrors how ``hyprshot`` implements window selection: the geometry of
        every mapped window on an active workspace is fed to ``slurp -r`` so a
        single click on a window selects it.
        """
        if not self.has_tool("slurp"):
            on_geometry(None)
            return False

        boxes = self._window_boxes()
        if not boxes:
            on_geometry(None)
            return False

        def on_done(proc: Gio.Subprocess, task: Gio.Task) -> None:
            try:
                _, stdout, _ = proc.communicate_utf8_finish(task)
            except Exception as e:
                logger.warning(
                    f"[capture] _, stdout, _ = proc.communicate_utf8_finish(task) failed: {e}"
                )
                on_geometry(None)
                return
            on_geometry(stdout.strip() if stdout else None)

        proc = self._spawn(
            ["slurp", "-r"],
            Gio.SubprocessFlags.STDIN_PIPE
            | Gio.SubprocessFlags.STDOUT_PIPE
            | Gio.SubprocessFlags.STDERR_SILENCE,
        )
        if proc is None:
            on_geometry(None)
            return False
        proc.communicate_utf8_async(boxes, None, on_done)
        return True

    @staticmethod
    def _window_boxes() -> str:
        """Build a ``slurp``-compatible box list of currently visible windows."""
        from services.modus import get_clients, get_monitors

        active_ids = {m.get("activeWorkspace", {}).get("id") for m in get_monitors()}
        boxes: list[str] = []
        for client in get_clients():
            if not client.get("mapped", True):
                continue
            if client.get("workspace", {}).get("id") not in active_ids:
                continue
            at = client.get("at")
            size = client.get("size")
            if not at or not size:
                continue
            boxes.append(f"{at[0]},{at[1]} {size[0]}x{size[1]}")
        return "\n".join(boxes)

    @staticmethod
    def _spawn(command: list[str], flags: Gio.SubprocessFlags) -> Gio.Subprocess | None:
        try:
            return Gio.Subprocess.new(command, flags)
        except Exception as error:
            logger.error(f"[CaptureBackend] Failed to spawn {command}: {error}")
            return None


class CaptureNotifier:
    """Thin wrapper around ``notify-send`` with async action handling."""

    def __init__(self, app_name: str = "Fabric Screenshot Utility") -> None:
        self._app_name = app_name

    def notify(
        self,
        title: str,
        message: str,
        *,
        icon: str | None = None,
        actions: Iterable[NotificationAction] | None = None,
        hints: Iterable[str] | None = None,
        on_action: ActionCallback | None = None,
    ) -> None:
        """Send a notification.

        :param actions: iterable of ``(id, label)`` pairs shown as buttons.
        :param hints: raw ``notify-send`` ``-h`` hint strings.
        :param on_action: invoked with the chosen action id when a button is
            pressed. When omitted the notification is fire-and-forget.
        """
        command = ["notify-send", "-a", self._app_name]
        if icon:
            command += ["-i", icon]
        for hint in hints or ():
            command += ["-h", hint]
        for action_id, label in actions or ():
            command += ["-A", f"{action_id}={label}"]
        command += [title, message]

        if on_action is None:
            self._spawn(command, Gio.SubprocessFlags.STDOUT_SILENCE)
            return
        self._spawn_with_action(command, on_action)

    def _spawn_with_action(self, command: list[str], on_action: ActionCallback) -> None:
        proc = self._spawn(command, Gio.SubprocessFlags.STDOUT_PIPE)
        if proc is None:
            return

        def on_done(process: Gio.Subprocess, task: Gio.Task) -> None:
            try:
                _, stdout, _ = process.communicate_utf8_finish(task)
            except Exception as error:
                logger.error(f"[CaptureNotifier] Failed to read action: {error}")
                return
            action = stdout.strip() if stdout else ""
            if action:
                on_action(action)

        proc.communicate_utf8_async(None, None, on_done)

    @staticmethod
    def _spawn(command: list[str], flags: Gio.SubprocessFlags) -> Gio.Subprocess | None:
        try:
            return Gio.Subprocess.new(command, flags)
        except Exception as error:
            logger.error(f"[CaptureNotifier] Failed to notify: {error}")
            return None
