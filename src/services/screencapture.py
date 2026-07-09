import json
from datetime import datetime
from pathlib import Path

from fabric import Service, Signal
from fabric.core.service import Property
from fabric.utils import (
    Gio,
    exec_shell_command,
    exec_shell_command_async,
    logger,
    time,
)

from utils.functions import is_app_running, kill_process


class ScreenCapture(Service):
    """Service for screen capture and recording functionality"""

    @Signal
    def screenshot_taken(self, path: str) -> None:
        """Signal emitted when screenshot is taken."""

    @Signal
    def recording_started(self, path: str) -> None:
        """Signal emitted when recording starts."""

    @Signal
    def recording_stopped(self, path: str) -> None:
        """Signal emitted when recording stops."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs):
        if getattr(self, "_initialized", False):
            return

        super().__init__(**kwargs)
        self._initialized = True
        self.home = Path.home()
        self.screenshots_dir = self.home / "Pictures" / "Screenshots"
        self.recordings_dir = self.home / "Videos" / "Recordings"
        self.recording_file = Path("/tmp/recording.txt")
        self.recording_start_time_file = Path("/tmp/recording_start_time.txt")

        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

    def notify_send(self, title, message, icon=None, actions=None):
        cmd = ["notify-send", "-a", "Modus"]

        if icon:
            cmd.extend(["-i", str(icon)])

        if actions:
            for action in actions:
                cmd.extend(["-A", f"{action}={action}"])

        cmd.extend([title, message])
        try:
            Gio.Subprocess.new(
                cmd,
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except Exception:
            pass

    def send_screenshot_notification(self, file_path=None):
        cmd = ["notify-send"]
        cmd.extend(
            [
                "-A",
                "files=Show in Files",
                "-A",
                "view=View",
                "-A",
                "edit=Edit",
                "-i",
                "camera-photo-symbolic",
                "-a",
                "Fabric Screenshot Utility",
                "-h",
                f"STRING:image-path:{file_path}",
                "Screenshot Saved",
                f"Saved Screenshot at {file_path}",
            ]
            if file_path
            else ["Screenshot Sent to Clipboard"]
        )

        proc: Gio.Subprocess = Gio.Subprocess.new(cmd, Gio.SubprocessFlags.STDOUT_PIPE)

        def do_callback(process: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, stderr = process.communicate_utf8_finish(task)
            except Exception:
                logger.error(
                    f"[SCREENSHOT] Failed read notification action with error {stderr}"
                )
                return

            match stdout.strip("\n"):
                case "files":
                    exec_shell_command_async(f"xdg-open {self.screenshots_dir}")
                case "view":
                    exec_shell_command_async(f"xdg-open {file_path}")
                case "edit":
                    exec_shell_command_async(f"satty -f {file_path}")

        proc.communicate_utf8_async(None, None, do_callback)
        self.screenshot_taken(file_path)

    def send_recording_notification(self, file_path):
        cmd = ["notify-send"]
        cmd.extend(
            [
                "-A",
                "files=Show in Files",
                "-A",
                "view=View",
                "-i",
                "camera-video-symbolic",
                "-a",
                "Fabric Screenshot Utility",
                "Screencast Saved",
                f"Saved Screencast at {file_path}",
            ]
        )

        proc: Gio.Subprocess = Gio.Subprocess.new(cmd, Gio.SubprocessFlags.STDOUT_PIPE)

        def do_callback(process: Gio.Subprocess, task: Gio.Task):
            try:
                _, stdout, stderr = process.communicate_utf8_finish(task)
            except Exception:
                logger.error(
                    f"[SCREENCAST] Failed read notification action with error {stderr}"
                )
                return

            match stdout.strip("\n"):
                case "files":
                    exec_shell_command_async(f"xdg-open {self.recordings_dir}")
                case "view":
                    exec_shell_command_async(f"xdg-open {file_path}")

        proc.communicate_utf8_async(None, None, do_callback)
        self.recording_stopped(file_path)

    def _get_active_monitor(self):
        """Get the name of the currently focused monitor."""
        try:
            monitors_json = exec_shell_command("hyprctl monitors -j")
            if monitors_json:
                monitors = json.loads(monitors_json)
                for monitor in monitors:
                    if monitor.get("focused"):
                        return monitor.get("name")
        except Exception as e:
            logger.error(f"[SCREENSHOT] Failed to get active monitor: {e}")
        return "eDP-1"  # Fallback

    def screenshot(self, target="region", output_dir=None, show_cursor=False):
        """
        Take a screenshot.
        :param target: 'region', 'window', 'active', 'output', or a display name
        :param output_dir: where to save; defaults to self.screenshots_dir
        :param show_cursor: include the mouse cursor in the capture
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        save_dir = Path(output_dir).expanduser() if output_dir else self.screenshots_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        # When cursor is needed we call grim directly (hyprshot has no cursor flag).
        # This covers region and fullscreen; window mode still falls back to hyprshot.
        if show_cursor and target in ("region", "active", "output"):
            return self._screenshot_with_cursor(target, save_dir, timestamp)

        command = [
            "hyprshot",
            "-s",
            "-o",
            str(save_dir),
            "-f",
            f"{timestamp}.png",
        ]

        if target == "region":
            command.extend(["-m", "region"])
        elif target == "window":
            command.extend(["-m", "window"])
        elif target == "active":
            active_monitor = self._get_active_monitor()
            command.extend(["-m", "output", "-m", active_monitor])
        elif target == "output":
            command.extend(["-m", "output"])
        else:
            command.extend(["-m", "output", "-m", target])

        expected = save_dir / f"{timestamp}.png"

        def on_capture(proc, task, *_):
            try:
                proc.wait_finish(task)
                if expected.exists():
                    self.send_screenshot_notification(file_path=str(expected))
                else:
                    self.notify_send(
                        "Screenshot cancelled",
                        "Selection was cancelled",
                        icon="camera-photo-symbolic",
                    )
                    self.screenshot_taken(None)
            except Exception as e:
                logger.error(f"Screenshot notification failed: {e}")
                self.screenshot_taken(None)

        try:
            proc = Gio.Subprocess.new(command, Gio.SubprocessFlags.STDERR_SILENCE)
            proc.wait_async(None, on_capture)
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return False

        return True

    def _screenshot_with_cursor(
        self, target: str, save_dir: Path, timestamp: str
    ) -> bool:
        """Use grim -c directly so the cursor is included in the capture."""
        out_file = save_dir / f"{timestamp}.png"

        if target == "region":
            geo_proc = Gio.Subprocess.new(
                ["slurp"],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
            try:
                geo_proc.wait(None)
            except Exception:
                pass
            if geo_proc.get_exit_status() != 0:
                self.notify_send(
                    "Screenshot cancelled",
                    "Selection was cancelled",
                    icon="camera-photo-symbolic",
                )
                self.screenshot_taken(None)
                return True
            _, geo_bytes, _ = geo_proc.communicate(None)
            geo = geo_bytes.decode().strip() if geo_bytes else ""
            if not geo:
                self.notify_send(
                    "Screenshot cancelled",
                    "Selection was cancelled",
                    icon="camera-photo-symbolic",
                )
                self.screenshot_taken(None)
                return True
            cmd = ["grim", "-c", "-g", geo, str(out_file)]
        else:
            monitor = self._get_active_monitor() if target == "active" else None
            cmd = ["grim", "-c"]
            if monitor:
                cmd.extend(["-o", monitor])
            cmd.append(str(out_file))

        expected = out_file

        def on_grim_done(proc, task, *_):
            try:
                proc.wait_finish(task)
                if expected.exists():
                    self.send_screenshot_notification(file_path=str(expected))
                else:
                    self.notify_send(
                        "Screenshot cancelled",
                        "Selection was cancelled",
                        icon="camera-photo-symbolic",
                    )
                    self.screenshot_taken(None)
            except Exception as e:
                logger.error(f"Screenshot notification failed: {e}")
                self.screenshot_taken(None)

        proc = Gio.Subprocess.new(cmd, Gio.SubprocessFlags.NONE)
        proc.wait_async(None, on_grim_done)
        return True

    def record(self, target="selection", use_audio=False, show_cursor=False):
        """
        Start recording.
        :param target: 'selection', 'active', a monitor name like 'eDP-1', etc.
        :param use_audio: capture system/mic audio (removes --no-audio)
        :param show_cursor: show mouse cursor in the recording
        """
        if self.is_recording:
            logger.error(
                "[SCREENRECORD] Another instance of wf-recorder is already running"
            )
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file = self.recordings_dir / f"{timestamp}.mkv"

        self._current_recording_path = str(output_file)
        self.recording_file.write_text(str(output_file))
        self.recording_start_time_file.write_text(str(int(time.time())))

        cmd = [
            "wf-recorder",
            "--file",
            str(output_file),
            "--pixel-format",
            "yuv420p",
        ]

        if not use_audio:
            cmd.append("--no-audio")

        if show_cursor:
            cmd.append("--show-cursor")

        if target == "selection":
            try:
                geometry = exec_shell_command("slurp 2>/dev/null")
            except Exception:
                self.notify_send(
                    "Recording cancelled",
                    "Selection was cancelled",
                    icon="camera-video-symbolic",
                )
                return False
            if not geometry or not str(geometry).strip():
                self.notify_send(
                    "Recording cancelled",
                    "Selection was cancelled",
                    icon="camera-video-symbolic",
                )
                return False
            cmd.extend(["-g", geometry])
        elif target == "active":
            cmd.extend(["-o", self._get_active_monitor()])
        else:
            cmd.extend(["-o", target])

        Gio.Subprocess.new(cmd, Gio.SubprocessFlags.NONE)

        self.recording_started(str(output_file))
        return True

    def stop_recording(self):
        kill_process("wf-recorder")

        path = getattr(self, "_current_recording_path", None)
        if not path and self.recording_file.exists():
            path = self.recording_file.read_text().strip()

        if path:
            self.send_recording_notification(path)

        if self.recording_start_time_file.exists():
            self.recording_start_time_file.unlink()

        if self.recording_file.exists():
            self.recording_file.unlink()

        return True

    @Property(bool, "readable", default_value=False)
    def is_recording(self):
        return is_app_running("wf-recorder") or is_app_running("gpu-screen-recorder")


def __getattr__(name):
    if name == "screen_capture_service":
        import sys

        return sys.modules["services.modus"].screen_capture_service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
