import subprocess
from typing import List

from fabric.utils import get_relative_path

from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
from utils.icons import screenrecord, screenshots, ssfull, ssregion, stop


class ScreencapturePlugin(PluginBase):
    """
    Plugin for taking screenshots and screen recordings using screen-capture.sh script.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Screencapture"
        self.description = "Take screenshots and screen recordings"
        # Path to the screen-capture script
        self.script_path = get_relative_path("../../../scripts/screen-capture.sh")

    def initialize(self):
        """Initialize the screencapture plugin."""
        self.set_triggers(["sc"])

    def cleanup(self):
        """Cleanup the screencapture plugin."""
        pass

    def get_commands(self):
        """Return available commands for this plugin."""
        return {
            # Screenshot commands
            "screenshot": "Take a screenshot of the main display",
            "ss": "Take a screenshot of the main display",
            "screenshot-region": "Take a screenshot of selected region",
            "ss-region": "Take a screenshot of selected region",
            "screenshot-both": "Take a screenshot of both displays",
            "ss-both": "Take a screenshot of both displays",
            "screenshot-hdmi": "Take a screenshot of HDMI display",
            "ss-hdmi": "Take a screenshot of HDMI display",
            # Recording commands (with audio)
            "record": "Start recording main display with audio",
            "rec": "Start recording main display with audio",
            "record-region": "Start recording selected region with audio",
            "rec-region": "Start recording selected region with audio",
            "record-hdmi": "Start recording HDMI display with audio",
            "rec-hdmi": "Start recording HDMI display with audio",
            # Recording commands (no audio)
            "record-noaudio": "Start recording main display without audio",
            "rec-noaudio": "Start recording main display without audio",
            "record-noaudio-region": "Start recording selected region without audio",
            "rec-noaudio-region": "Start recording selected region without audio",
            "record-noaudio-hdmi": "Start recording HDMI display without audio",
            "rec-noaudio-hdmi": "Start recording HDMI display without audio",
            # High-quality recording commands
            "record-hq": "Start high-quality recording of main display",
            "rec-hq": "Start high-quality recording of main display",
            "record-hq-region": "Start high-quality recording of selected region",
            "rec-hq-region": "Start high-quality recording of selected region",
            "record-hq-hdmi": "Start high-quality recording of HDMI display",
            "rec-hq-hdmi": "Start high-quality recording of HDMI display",
            # GIF recording commands
            "record-gif": "Start GIF recording of main display",
            "rec-gif": "Start GIF recording of main display",
            "record-gif-region": "Start GIF recording of selected region",
            "rec-gif-region": "Start GIF recording of selected region",
            # Control commands
            "stop": "Stop current recording",
            # Conversion commands
            "convert-webm": "Convert latest MKV recording to WebM format",
            "conv-webm": "Convert latest MKV recording to WebM format",
            "convert-iphone": "Convert latest MKV recording for iPhone compatibility",
            "conv-iphone": "Convert latest MKV recording for iPhone compatibility",
            "convert-youtube": "Convert latest recording for YouTube upload",
            "conv-youtube": "Convert latest recording for YouTube upload",
            "convert-gif": "Convert latest recording to GIF format",
            "conv-gif": "Convert latest recording to GIF format",
            # Conversion commands with file input
            "convert-webm-file": "Convert specific MKV file to WebM format",
            "conv-webm-file": "Convert specific MKV file to WebM format",
            "convert-iphone-file": "Convert specific MKV file for iPhone compatibility",
            "conv-iphone-file": "Convert specific MKV file for iPhone compatibility",
            "convert-youtube-file": "Convert specific video file for YouTube upload",
            "conv-youtube-file": "Convert specific video file for YouTube upload",
            "convert-gif-file": "Convert specific video file to GIF format",
            "conv-gif-file": "Convert specific video file to GIF format",
        }

    def _run_script(self, *args):
        """Execute the screen-capture script with given arguments."""
        try:
            subprocess.Popen([self.script_path] + list(args))
        except Exception as e:
            print(f"Error running screen-capture script: {e}")

    def _run_script_with_file(self, format_type: str, file_path: str):
        """Execute the screen-capture script with file parameter."""
        try:
            subprocess.Popen([self.script_path, "convert", format_type, file_path])
        except Exception as e:
            print(f"Error running screen-capture script with file: {e}")

    def _is_recording(self):
        """Check if recording is currently active."""
        try:
            result = subprocess.run(
                [self.script_path, "status"], capture_output=True, text=True
            )
            return result.stdout.strip() == "true"
        except Exception:
            return False

    def _get_command_result(self, command: str) -> Result:
        """Get a Result object for a specific command."""
        # Import here to avoid circular imports
        from utils.icons import screenrecord, screenshots, ssfull, ssregion, stop

        command_info = {
            # Screenshot commands
            "screenshot": (
                "Take Screenshot (eDP-1)",
                "Capture the main display",
                ssfull,
                lambda: self._run_script("screenshot", "eDP-1"),
            ),
            "ss": (
                "Take Screenshot (eDP-1)",
                "Capture the main display",
                ssfull,
                lambda: self._run_script("screenshot", "eDP-1"),
            ),
            "screenshot-region": (
                "Take Region Screenshot",
                "Capture a selected region",
                ssregion,
                lambda: self._run_script("screenshot", "selection"),
            ),
            "ss-region": (
                "Take Region Screenshot",
                "Capture a selected region",
                ssregion,
                lambda: self._run_script("screenshot", "selection"),
            ),
            "screenshot-both": (
                "Take Screenshot (Both Displays)",
                "Capture both displays combined",
                screenshots,
                lambda: self._run_script("screenshot", "both"),
            ),
            "ss-both": (
                "Take Screenshot (Both Displays)",
                "Capture both displays combined",
                screenshots,
                lambda: self._run_script("screenshot", "both"),
            ),
            "screenshot-hdmi": (
                "Take Screenshot (HDMI-A-1)",
                "Capture HDMI display",
                ssfull,
                lambda: self._run_script("screenshot", "HDMI-A-1"),
            ),
            "ss-hdmi": (
                "Take Screenshot (HDMI-A-1)",
                "Capture HDMI display",
                ssfull,
                lambda: self._run_script("screenshot", "HDMI-A-1"),
            ),
            # Recording commands (with audio)
            "record": (
                "Start Recording (eDP-1)",
                "Record the main display with audio",
                screenrecord,
                lambda: self._run_script("record", "eDP-1"),
            ),
            "rec": (
                "Start Recording (eDP-1)",
                "Record the main display with audio",
                screenrecord,
                lambda: self._run_script("record", "eDP-1"),
            ),
            "record-region": (
                "Start Region Recording",
                "Record a selected region with audio",
                screenrecord,
                lambda: self._run_script("record", "selection"),
            ),
            "rec-region": (
                "Start Region Recording",
                "Record a selected region with audio",
                screenrecord,
                lambda: self._run_script("record", "selection"),
            ),
            "record-hdmi": (
                "Start Recording (HDMI-A-1)",
                "Record HDMI display with audio",
                screenrecord,
                lambda: self._run_script("record", "HDMI-A-1"),
            ),
            "rec-hdmi": (
                "Start Recording (HDMI-A-1)",
                "Record HDMI display with audio",
                screenrecord,
                lambda: self._run_script("record", "HDMI-A-1"),
            ),
            # Recording commands (no audio)
            "record-noaudio": (
                "Start Recording No Audio (eDP-1)",
                "Record the main display without audio",
                screenrecord,
                lambda: self._run_script("record-noaudio", "eDP-1"),
            ),
            "rec-noaudio": (
                "Start Recording No Audio (eDP-1)",
                "Record the main display without audio",
                screenrecord,
                lambda: self._run_script("record-noaudio", "eDP-1"),
            ),
            "record-noaudio-region": (
                "Start Region Recording No Audio",
                "Record a selected region without audio",
                screenrecord,
                lambda: self._run_script("record-noaudio", "selection"),
            ),
            "rec-noaudio-region": (
                "Start Region Recording No Audio",
                "Record a selected region without audio",
                screenrecord,
                lambda: self._run_script("record-noaudio", "selection"),
            ),
            "record-noaudio-hdmi": (
                "Start Recording No Audio (HDMI-A-1)",
                "Record HDMI display without audio",
                screenrecord,
                lambda: self._run_script("record-noaudio", "HDMI-A-1"),
            ),
            "rec-noaudio-hdmi": (
                "Start Recording No Audio (HDMI-A-1)",
                "Record HDMI display without audio",
                screenrecord,
                lambda: self._run_script("record-noaudio", "HDMI-A-1"),
            ),
            # High-quality recording commands
            "record-hq": (
                "Start HQ Recording (eDP-1)",
                "High-quality recording for YouTube",
                screenrecord,
                lambda: self._run_script("record-hq", "eDP-1"),
            ),
            "rec-hq": (
                "Start HQ Recording (eDP-1)",
                "High-quality recording for YouTube",
                screenrecord,
                lambda: self._run_script("record-hq", "eDP-1"),
            ),
            "record-hq-region": (
                "Start HQ Region Recording",
                "High-quality region recording",
                screenrecord,
                lambda: self._run_script("record-hq", "selection"),
            ),
            "rec-hq-region": (
                "Start HQ Region Recording",
                "High-quality region recording",
                screenrecord,
                lambda: self._run_script("record-hq", "selection"),
            ),
            "record-hq-hdmi": (
                "Start HQ Recording (HDMI-A-1)",
                "High-quality HDMI recording",
                screenrecord,
                lambda: self._run_script("record-hq", "HDMI-A-1"),
            ),
            "rec-hq-hdmi": (
                "Start HQ Recording (HDMI-A-1)",
                "High-quality HDMI recording",
                screenrecord,
                lambda: self._run_script("record-hq", "HDMI-A-1"),
            ),
            # GIF recording commands
            "record-gif": (
                "Start GIF Recording (eDP-1)",
                "Record as optimized GIF",
                screenrecord,
                lambda: self._run_script("record-gif", "eDP-1"),
            ),
            "rec-gif": (
                "Start GIF Recording (eDP-1)",
                "Record as optimized GIF",
                screenrecord,
                lambda: self._run_script("record-gif", "eDP-1"),
            ),
            "record-gif-region": (
                "Start GIF Region Recording",
                "Record selected region as GIF",
                screenrecord,
                lambda: self._run_script("record-gif", "selection"),
            ),
            "rec-gif-region": (
                "Start GIF Region Recording",
                "Record selected region as GIF",
                screenrecord,
                lambda: self._run_script("record-gif", "selection"),
            ),
            # Control commands
            "stop": (
                "Stop Recording",
                "Stop the current screen recording",
                stop,
                lambda: self._run_script("record", "stop"),
            ),
            # Conversion commands
            "convert-webm": (
                "Convert Latest to WebM",
                "Convert latest MKV recording to WebM format",
                screenrecord,
                lambda: self._run_script("convert", "webm"),
            ),
            "conv-webm": (
                "Convert Latest to WebM",
                "Convert latest MKV recording to WebM format",
                screenrecord,
                lambda: self._run_script("convert", "webm"),
            ),
            "convert-iphone": (
                "Convert Latest for iPhone",
                "Convert latest MKV recording for iPhone compatibility",
                screenrecord,
                lambda: self._run_script("convert", "iphone"),
            ),
            "conv-iphone": (
                "Convert Latest for iPhone",
                "Convert latest MKV recording for iPhone compatibility",
                screenrecord,
                lambda: self._run_script("convert", "iphone"),
            ),
            "convert-youtube": (
                "Convert Latest for YouTube",
                "Convert latest recording for YouTube upload",
                screenrecord,
                lambda: self._run_script("convert", "youtube"),
            ),
            "conv-youtube": (
                "Convert Latest for YouTube",
                "Convert latest recording for YouTube upload",
                screenrecord,
                lambda: self._run_script("convert", "youtube"),
            ),
            "convert-gif": (
                "Convert Latest to GIF",
                "Convert latest recording to GIF format",
                screenrecord,
                lambda: self._run_script("convert", "gif"),
            ),
            "conv-gif": (
                "Convert Latest to GIF",
                "Convert latest recording to GIF format",
                screenrecord,
                lambda: self._run_script("convert", "gif"),
            ),
            # File-based conversion commands (these will be handled specially)
            "convert-webm-file": (
                "Convert File to WebM",
                "Type filename after command (e.g., convert-webm-file video.mkv)",
                screenrecord,
                None,  # Will be handled in query method
            ),
            "conv-webm-file": (
                "Convert File to WebM",
                "Type filename after command (e.g., conv-webm-file video.mkv)",
                screenrecord,
                None,  # Will be handled in query method
            ),
            "convert-iphone-file": (
                "Convert File for iPhone",
                "Type filename after command (e.g., convert-iphone-file video.mkv)",
                screenrecord,
                None,  # Will be handled in query method
            ),
            "conv-iphone-file": (
                "Convert File for iPhone",
                "Type filename after command (e.g., conv-iphone-file video.mkv)",
                screenrecord,
                None,  # Will be handled in query method
            ),
            "convert-youtube-file": (
                "Convert File for YouTube",
                "Type filename after command (e.g., convert-youtube-file video.mkv)",
                screenrecord,
                None,  # Will be handled in query method
            ),
            "conv-youtube-file": (
                "Convert File for YouTube",
                "Type filename after command (e.g., conv-youtube-file video.mkv)",
                screenrecord,
                None,  # Will be handled in query method
            ),
            "convert-gif-file": (
                "Convert File to GIF",
                "Type filename after command (e.g., convert-gif-file video.mkv)",
                screenrecord,
                None,  # Will be handled in query method
            ),
            "conv-gif-file": (
                "Convert File to GIF",
                "Type filename after command (e.g., conv-gif-file video.mkv)",
                screenrecord,
                None,  # Will be handled in query method
            ),
        }

        if command in command_info:
            title, subtitle, icon, action = command_info[command]
            if action is not None:  # Regular command
                return Result(
                    title=title,
                    subtitle=subtitle,
                    icon_markup=icon,
                    action=action,
                    relevance=1.0,
                    plugin_name=self.display_name,
                )
            else:  # File-based command, show instruction
                return Result(
                    title=title,
                    subtitle=subtitle,
                    icon_markup=icon,
                    action=lambda: None,  # No action for instruction
                    relevance=1.0,
                    plugin_name=self.display_name,
                )

        return None

    def query(self, query_string: str) -> List[Result]:
        """Search for screencapture actions based on query."""
        # Import here to avoid circular imports
        from utils.icons import screenrecord, screenshots, ssfull, ssregion, stop

        # Clean the query string
        query = query_string.strip().lower()

        results = []

        # Check for file-based conversion commands with parameters
        file_conversion_commands = {
            "convert-webm-file": "webm",
            "conv-webm-file": "webm",
            "convert-iphone-file": "iphone",
            "conv-iphone-file": "iphone",
            "convert-youtube-file": "youtube",
            "conv-youtube-file": "youtube",
            "convert-gif-file": "gif",
            "conv-gif-file": "gif",
        }

        # Parse query for file-based commands
        query_parts = query.split()
        if len(query_parts) >= 2:
            command = query_parts[0]
            file_param = " ".join(query_parts[1:])

            if command in file_conversion_commands:
                format_type = file_conversion_commands[command]
                return [Result(
                    title=f"Convert {file_param} to {format_type.upper()}",
                    subtitle=f"Convert specified file to {format_type} format",
                    icon_markup=screenrecord,
                    action=lambda fp=file_param, ft=format_type: self._run_script_with_file(ft, fp),
                    relevance=1.0,
                    plugin_name=self.display_name,
                )]

        # Check if query matches a command and return it as a result
        command_result = self._get_command_result(query)
        if command_result:
            return [command_result]

        # Check recording status
        is_recording = self._is_recording()

        # If recording is active, show stop button first with highest relevance
        if is_recording:
            results.append(
                Result(
                    title="Stop Recording",
                    subtitle="Stop the current screen recording",
                    icon_markup=stop,
                    action=lambda: self._run_script("record", "stop"),
                    relevance=2.0,  # Highest relevance to appear at top
                    plugin_name=self.display_name,
                )
            )

        # Screenshot actions
        results.extend(
            [
                Result(
                    title="Take Screenshot",
                    subtitle="Capture the entire screen (eDP-1)",
                    icon_markup=ssfull,
                    action=lambda: self._run_script("screenshot", "eDP-1"),
                    relevance=1.0,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Take Region Screenshot",
                    subtitle="Capture a selected region",
                    icon_markup=ssregion,
                    action=lambda: self._run_script("screenshot", "selection"),
                    relevance=0.9,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Take Screenshot (Both Displays)",
                    subtitle="Capture both displays combined",
                    icon_markup=screenshots,
                    action=lambda: self._run_script("screenshot", "both"),
                    relevance=0.8,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Take Screenshot (HDMI-A-1)",
                    subtitle="Capture HDMI display",
                    icon_markup=ssfull,
                    action=lambda: self._run_script("screenshot", "HDMI-A-1"),
                    relevance=0.7,
                    plugin_name=self.display_name,
                ),
            ]
        )

        # Standard recording actions
        results.extend(
            [
                Result(
                    title="Start Recording (eDP-1)",
                    subtitle="Record the main display with audio",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record", "eDP-1"),
                    relevance=0.7,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Region Recording",
                    subtitle="Record a selected region",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record", "selection"),
                    relevance=0.6,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Recording (HDMI-A-1)",
                    subtitle="Record HDMI display with audio",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record", "HDMI-A-1"),
                    relevance=0.5,
                    plugin_name=self.display_name,
                ),
            ]
        )

        # No-audio recording actions
        results.extend(
            [
                Result(
                    title="Start Recording No Audio (eDP-1)",
                    subtitle="Record the main display without audio",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record-noaudio", "eDP-1"),
                    relevance=0.65,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Region Recording No Audio",
                    subtitle="Record a selected region without audio",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record-noaudio", "selection"),
                    relevance=0.55,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Recording No Audio (HDMI-A-1)",
                    subtitle="Record HDMI display without audio",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record-noaudio", "HDMI-A-1"),
                    relevance=0.45,
                    plugin_name=self.display_name,
                ),
            ]
        )

        # High-quality recording actions
        results.extend(
            [
                Result(
                    title="Start HQ Recording (eDP-1)",
                    subtitle="High-quality recording for YouTube",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record-hq", "eDP-1"),
                    relevance=0.4,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start HQ Region Recording",
                    subtitle="High-quality region recording",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record-hq", "selection"),
                    relevance=0.3,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start HQ Recording (HDMI-A-1)",
                    subtitle="High-quality HDMI recording",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record-hq", "HDMI-A-1"),
                    relevance=0.2,
                    plugin_name=self.display_name,
                ),
            ]
        )

        # GIF recording actions
        results.extend(
            [
                Result(
                    title="Start GIF Recording (eDP-1)",
                    subtitle="Record as optimized GIF",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record-gif", "eDP-1"),
                    relevance=0.1,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start GIF Region Recording",
                    subtitle="Record selected region as GIF",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("record-gif", "selection"),
                    relevance=0.05,
                    plugin_name=self.display_name,
                ),
            ]
        )

        # Conversion actions
        results.extend(
            [
                Result(
                    title="Convert Latest to WebM",
                    subtitle="Convert latest MKV recording to WebM format",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("convert", "webm"),
                    relevance=0.01,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Convert Latest for iPhone",
                    subtitle="Convert latest MKV recording for iPhone compatibility",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("convert", "iphone"),
                    relevance=0.01,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Convert Latest for YouTube",
                    subtitle="Convert latest recording for YouTube upload",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("convert", "youtube"),
                    relevance=0.01,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Convert Latest to GIF",
                    subtitle="Convert latest recording to GIF format",
                    icon_markup=screenrecord,
                    action=lambda: self._run_script("convert", "gif"),
                    relevance=0.01,
                    plugin_name=self.display_name,
                ),
            ]
        )

        return results
