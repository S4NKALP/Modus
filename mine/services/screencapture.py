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

from utils.functions import is_app_running, run_command


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
        super().__init__(**kwargs)
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
        return run_command(cmd)

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

    def check_wf_recorder(self):
        if not is_app_running("wf-recorder"):
            return False

        run_command(["pkill", "-INT", "-x", "wf-recorder"])

        if self.recording_file.exists():
            recording_file = self.recording_file.read_text().strip()
            self.send_recording_notification(recording_file)

        if self.recording_start_time_file.exists():
            self.recording_start_time_file.unlink()

        return True

    def get_default_monitor_source(self) -> str | None:
        """Return the monitor source of the default sink (system audio).

        wf-recorder defaults to the mic input. To capture the audio coming
        out of the speakers (e.g. a Zoom meeting), we need the monitor of
        the default sink (e.g. ``alsa_output.pci-...monitor``).
        """
        try:
            result = run_command(["pactl", "get-default-sink"])
            if result.returncode == 0:
                sink = (result.stdout or "").strip()
                if sink:
                    return f"{sink}.monitor"
        except FileNotFoundError:
            pass

        # PipeWire fallback: parse `wpctl status` for the default sink
        try:
            result = run_command(["wpctl", "status"])
            if result.returncode == 0:
                lines = (result.stdout or "").splitlines()
                in_sinks = False
                default_id = None
                sinks: dict[str, str] = {}
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("Sinks:"):
                        in_sinks = True
                        continue
                    if in_sinks and stripped and not stripped.startswith("─"):
                        if "Sources:" in stripped or "Filters:" in stripped:
                            in_sinks = False
                            continue
                        if stripped.startswith("*"):
                            default_id = stripped.lstrip("*").strip().split(".")[0]
                        parts = stripped.lstrip("* ").split(".", 1)
                        if len(parts) == 2:
                            sinks[parts[0]] = parts[1].split(" [")[0].strip()
                if default_id and default_id in sinks:
                    return f"{sinks[default_id]}.monitor"
        except FileNotFoundError:
            pass

        return None

    def record_video(self, output_file, *args):
        cmd = [
            "wf-recorder",
            *args,
            "-f",
            str(output_file),
            "-c",
            "libvpx-vp9",
            "--pixel-format",
            "yuv420p",
            "-F",
            "eq=brightness=0.12:contrast=1.1",
        ]
        return run_command(cmd)

    def record_video_noaudio(self, output_file, *args):
        cmd = [
            "wf-recorder",
            *args,
            "-f",
            str(output_file),
            "-c",
            "libvpx-vp9",
            "--pixel-format",
            "yuv420p",
            "-F",
            "eq=brightness=0.12:contrast=1.1",
            "--no-audio",
        ]
        return run_command(cmd)

    def screenshot(self, fullscreen=False, save_copy=True):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        command = [
            "hyprshot",
            "-s",
            "-o",
            str(self.screenshots_dir),
            "-f",
            f"{timestamp}_fabric_screenshot.png",
        ]

        command.extend(
            ["-m", "active", "-m", "output"] if fullscreen else ["-m", "region"]
        )
        command.append("-- ls")  # This is so there is something in stdout

        try:
            exec_shell_command_async(
                " ".join(command),
                self._after_screenshot,
            )
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return False

        return True

    def _after_screenshot(self, *_):
        try:
            screenshot_files = list(self.screenshots_dir.glob("*.png"))
            if screenshot_files:
                latest_file = max(screenshot_files, key=lambda f: f.stat().st_mtime)
                self.send_screenshot_notification(file_path=str(latest_file))
                time.sleep(0.2)
            else:
                # No file found after command: likely user cancelled the selection
                self.notify_send(
                    "Screenshot cancelled",
                    "Selection was cancelled",
                    icon="camera-photo-symbolic",
                )
        except Exception as e:
            logger.error(f"Screenshot notification failed: {e}")

    def record(self, fullscreen=False, no_audio=False):
        if self.is_recording:
            logger.error(
                "[SCREENRECORD] Another instance of wf-recorder is already running"
            )
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file = self.recordings_dir / f"{timestamp}.mp4"

        self._current_recording_path = str(output_file)
        self.recording_file.write_text(str(output_file))
        self.recording_start_time_file.write_text(str(int(time.time())))

        if fullscreen:
            area = ""
        else:
            geometry = exec_shell_command("slurp")
            if not geometry or not str(geometry).strip():
                self.notify_send(
                    "Recording cancelled",
                    "Selection was cancelled",
                    icon="camera-video-symbolic",
                )
                return False
            area = f"-g '{geometry}'"

        if no_audio:
            command = f"wf-recorder --file={output_file} --pixel-format yuv420p --no-audio {area}"
        else:
            monitor = self.get_default_monitor_source()
            if monitor:
                logger.info(f"[SCREENRECORD] Recording system audio from: {monitor}")
                command = (
                    f"wf-recorder --file={output_file} --pixel-format yuv420p "
                    f"--audio={monitor} {area}"
                )
            else:
                logger.warning(
                    "[SCREENRECORD] No system monitor source found, "
                    "falling back to default audio source (mic)"
                )
                command = (
                    f"wf-recorder --file={output_file} --pixel-format yuv420p "
                    f"--audio {area}"
                )

        exec_shell_command_async(command)
        self.recording_started(str(output_file))

        return True

    def stop_recording(self):
        exec_shell_command_async("killall -INT wf-recorder")
        self.recording_stopped(self._current_recording_path)
        return True

    @Property(bool, "readable", default_value=False)
    def is_recording(self):
        return is_app_running("wf-recorder")


screen_capture_service = ScreenCapture()
