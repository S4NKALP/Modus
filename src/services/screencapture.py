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

from utils.functions import is_app_running, run_command, kill_process


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

        kill_process("wf-recorder")

        if self.recording_file.exists():
            recording_file = self.recording_file.read_text().strip()
            self.send_recording_notification(recording_file)

        if self.recording_start_time_file.exists():
            self.recording_start_time_file.unlink()

        return True

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

    def screenshot(self, target="region"):
        """
        Take a screenshot.
        :param target: 'region', 'active', 'output', 'both', or a specific display name like 'eDP-1'
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        screenshot_path = self.screenshots_dir / f"{timestamp}.png"

        if target == "both":
            # Special case for multiple displays, similar to the shell script
            temp_edp = self.screenshots_dir / f"{timestamp}_eDP-1.png"
            temp_hdmi = self.screenshots_dir / f"{timestamp}_HDMI-A-1.png"

            cmd = f"grim -c -o eDP-1 {temp_edp} && grim -c -o HDMI-A-1 {temp_hdmi} && montage {temp_edp} {temp_hdmi} -tile 2x1 -geometry +0+0 {screenshot_path} && rm {temp_edp} {temp_hdmi}"
            exec_shell_command_async(
                cmd, lambda *_: self.send_screenshot_notification(str(screenshot_path))
            )
            return True

        command = [
            "hyprshot",
            "-s",
            "-o",
            str(self.screenshots_dir),
            "-f",
            f"{timestamp}.png",
        ]

        if target == "region":
            command.extend(["-m", "region"])
        elif target == "active":
            active_monitor = self._get_active_monitor()
            command.extend(["-m", "output", "-m", active_monitor])
        elif target == "output":
            command.extend(["-m", "output"])
        else:
            # Specific display name
            command.extend(["-m", "output", "-m", target])

        command.append("-- ls")

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

    def record(self, target="selection", no_audio=False, mode="standard"):
        """
        Start recording.
        :param target: 'selection', 'eDP-1', 'HDMI-A-1', etc.
        :param no_audio: bool
        :param mode: 'standard', 'hq', 'gif'
        """
        if self.is_recording:
            logger.error(
                "[SCREENRECORD] Another instance of wf-recorder is already running"
            )
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        ext = "mp4" if mode == "hq" else "gif" if mode == "gif" else "mkv"
        output_file = self.recordings_dir / f"{timestamp}.{ext}"

        self._current_recording_path = str(output_file)
        self.recording_file.write_text(str(output_file))
        self.recording_start_time_file.write_text(str(int(time.time())))

        area = ""
        if target == "selection":
            geometry = exec_shell_command("slurp")
            if not geometry or not str(geometry).strip():
                self.notify_send(
                    "Recording cancelled",
                    "Selection was cancelled",
                    icon="camera-video-symbolic",
                )
                return False
            area = f"-g '{geometry}'"
        elif target == "active":
            active_monitor = self._get_active_monitor()
            area = f"-o {active_monitor}"
        else:
            area = f"-o {target}"

        if mode == "gif":
            # GIF optimized recording (lower fps, temp mkv then convert)
            temp_video = f"/tmp/gif_recording_{int(time.time())}.mkv"
            self.recording_file.write_text(temp_video)  # Update tracking to temp file
            command = f"wf-recorder -f {temp_video} -c libvpx-vp9 -r 15 --pixel-format yuv420p --no-audio {area}"

            def after_gif_recording(*_):
                if Path(temp_video).exists():
                    self.notify_send("Converting to GIF", "Processing recording...")
                    conv_cmd = f"ffmpeg -i {temp_video} -vf 'fps=15,scale=iw:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle' -loop 0 {output_file}"
                    exec_shell_command_async(
                        conv_cmd,
                        lambda *_: (
                            Path(temp_video).unlink(),
                            self.send_recording_notification(str(output_file)),
                        ),
                    )

            exec_shell_command_async(command, after_gif_recording)
        elif mode == "hq":
            # High quality preset
            preset_flags = "-c h264_vaapi -p 'preset=slow' -p 'crf=18' -r 60 -b 8000000 -B 192000 -g 30"
            if no_audio:
                preset_flags += " --no-audio"
            command = f"wf-recorder --file={output_file} --pixel-format yuv420p {preset_flags} {area}"
            exec_shell_command_async(command)
        else:
            # Standard mode
            audio_flag = "--no-audio" if no_audio else ""
            command = f"wf-recorder --file={output_file} --pixel-format yuv420p {audio_flag} {area}"
            exec_shell_command_async(command)

        self.recording_started(str(output_file))
        return True

    def stop_recording(self):
        kill_process("wf-recorder")
        if hasattr(self, "_current_recording_path"):
            self.recording_stopped(self._current_recording_path)
        return True

    def convert(self, format_type, file_path=None):
        """
        Convert video to specified format.
        :param format_type: 'webm', 'iphone', 'youtube', 'gif'
        :param file_path: Optional path to specific file
        """
        if not file_path:
            # Find latest recording
            files = list(self.recordings_dir.glob("*.[mkv|mp4]*"))
            if not files:
                self.notify_send("Conversion Error", "No recordings found to convert")
                return False
            file_path = str(max(files, key=lambda f: f.stat().st_mtime))

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            self.notify_send("Conversion Error", f"File not found: {file_path}")
            return False

        output_path = file_path_obj.with_suffix(f".{format_type}")
        if format_type == "iphone":
            output_path = file_path_obj.with_name(f"{file_path_obj.stem}-iphone.mp4")
        elif format_type == "youtube":
            output_path = file_path_obj.with_name(f"{file_path_obj.stem}-youtube.mp4")

        self.notify_send(
            f"Converting to {format_type.upper()}", f"Processing: {file_path_obj.name}"
        )

        if format_type == "webm":
            cmd = f"ffmpeg -y -i {file_path} -c:v libvpx -b:v 1M -c:a libvorbis {output_path}"
        elif format_type == "iphone":
            cmd = f"ffmpeg -y -i {file_path} -vcodec h264 -acodec aac {output_path}"
        elif format_type == "youtube":
            cmd = f"ffmpeg -y -i {file_path} -c:v libx264 -profile:v high -preset slow -crf 18 -pix_fmt yuv420p -c:a aac -b:a 384k -movflags +faststart {output_path}"
        elif format_type == "gif":
            cmd = f"ffmpeg -i {file_path} -vf 'fps=15,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle' -loop 0 {output_path}"
        else:
            return False

        def on_done(*_):
            self.notify_send(
                f"{format_type.upper()} Conversion Success",
                f"Saved to {output_path.name}",
            )
            if format_type == "gif":
                exec_shell_command_async(f"wl-copy < {output_path}")

        exec_shell_command_async(cmd, on_done)
        return True

    @Property(bool, "readable", default_value=False)
    def is_recording(self):
        return is_app_running("wf-recorder") or is_app_running("gpu-screen-recorder")


screen_capture_service = ScreenCapture()
