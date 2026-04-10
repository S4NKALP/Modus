from typing import List
from services.screencapture import screen_capture_service
from window.launcher.plugin_base import PluginBase
from window.launcher.result import Result


class ScreencapturePlugin(PluginBase):
    """
    Plugin for taking screenshots and screen recordings using screen-capture.sh script.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Screencapture"
        self.description = "Take screenshots and screen recordings"

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
            "screenshot-region": "Take a screenshot of selected region",
            "screenshot-both": "Take a screenshot of both displays",
            "screenshot-active": "Take a screenshot of the active display",
            # Recording commands (with audio)
            "record": "Start recording main display with audio",
            "record-region": "Start recording selected region with audio",
            "record-active": "Start recording active display with audio",
            # Recording overrides
            "record-noaudio": "Start recording main display without audio",
            "record-hq": "Start high-quality recording (eDP-1)",
            "record-gif": "Start GIF recording (eDP-1)",
            # Control commands
            "stop": "Stop current recording",
            # Conversion commands
            "convert-webm": "Convert latest MKV recording to WebM format",
            "convert-iphone": "Convert latest recordings for iPhone",
            "convert-youtube": "Convert latest recordings for YouTube",
            "convert-gif": "Convert latest recordings to GIF",
            # File conversion
            "convert-file": "Convert specific file (Usage: convert-file [type] [path])",
        }

    def _activate_default_plugins(self):
        """No action needed for script cleanup."""
        pass

    def _is_recording(self):
        """Check if recording is currently active."""
        return screen_capture_service.is_recording

    def _get_command_result(self, command: str) -> Result:
        """Get a Result object for a specific command."""
        # Map aliases manually if needed
        if command == "ss":
            command = "screenshot"
        if command == "rec":
            command = "record"
        if command == "conv":
            command = "convert"

        command_info = {
            # Screenshot commands
            "screenshot": (
                "Take Screenshot (eDP-1)",
                "Capture the main display",
                "camera-photo-symbolic",
                lambda: screen_capture_service.screenshot("eDP-1"),
            ),
            "screenshot-region": (
                "Take Region Screenshot",
                "Capture a selected region",
                "camera-photo-symbolic",
                lambda: screen_capture_service.screenshot("region"),
            ),
            "screenshot-both": (
                "Take Screenshot (Both Displays)",
                "Capture both displays combined",
                "video-joined-displays-symbolic",
                lambda: screen_capture_service.screenshot("both"),
            ),
            "screenshot-active": (
                "Take Screenshot (Active)",
                "Capture the active display",
                "camera-photo-symbolic",
                lambda: screen_capture_service.screenshot("active"),
            ),
            # Recording commands (with audio)
            "record": (
                "Start Recording (eDP-1)",
                "Record the main display with audio",
                "media-record-symbolic",
                lambda: screen_capture_service.record("eDP-1"),
            ),
            "record-region": (
                "Start Region Recording",
                "Record a selected region with audio",
                "media-record-symbolic",
                lambda: screen_capture_service.record("selection"),
            ),
            "record-active": (
                "Start Recording (Active)",
                "Record the active display with audio",
                "media-record-symbolic",
                lambda: screen_capture_service.record("active"),
            ),
            # Recording overrides
            "record-noaudio": (
                "Start Recording No Audio (eDP-1)",
                "Record without audio",
                "media-record-symbolic",
                lambda: screen_capture_service.record("eDP-1", no_audio=True),
            ),
            "record-hq": (
                "Start HQ Recording (eDP-1)",
                "High-quality recording for YouTube",
                "media-record-symbolic",
                lambda: screen_capture_service.record("eDP-1", mode="hq"),
            ),
            "record-gif": (
                "Start GIF Recording (eDP-1)",
                "Record as optimized GIF",
                "media-record-symbolic",
                lambda: screen_capture_service.record("eDP-1", mode="gif"),
            ),
            # Control commands
            "stop": (
                "Stop Recording",
                "Stop the current screen recording",
                "media-playback-stop-symbolic",
                lambda: screen_capture_service.stop_recording(),
            ),
            # Conversion commands
            "convert-webm": (
                "Convert Latest to WebM",
                "Convert latest MKV recording to WebM format",
                "video-x-generic-symbolic",
                lambda: screen_capture_service.convert("webm"),
            ),
            "convert-iphone": (
                "Convert Latest for iPhone",
                "Convert latest MKV recording for iPhone",
                "video-x-generic-symbolic",
                lambda: screen_capture_service.convert("iphone"),
            ),
            "convert-youtube": (
                "Convert Latest for YouTube",
                "Convert latest recording for YouTube",
                "video-x-generic-symbolic",
                lambda: screen_capture_service.convert("youtube"),
            ),
            "convert-gif": (
                "Convert Latest to GIF",
                "Convert latest recording to GIF",
                "image-x-generic-symbolic",
                lambda: screen_capture_service.convert("gif"),
            ),
        }

        if command in command_info:
            title, subtitle, icon, action = command_info[command]
            if action is not None:  # Regular command
                return Result(
                    title=title,
                    subtitle=subtitle,
                    icon_name=icon,
                    action=action,
                    relevance=1.0,
                    plugin_name=self.display_name,
                )
            else:  # File-based command, show instruction
                return Result(
                    title=title,
                    subtitle=subtitle,
                    icon_name=icon,
                    action=lambda: None,  # No action for instruction
                    relevance=1.0,
                    plugin_name=self.display_name,
                )

        return None

    def query(self, query_string: str) -> List[Result]:
        """Search for screencapture actions based on query."""
        # Import here to avoid circular imports

        # Clean the query string
        query = query_string.strip().lower()

        results = []

        # Parse query for file-based commands
        query_parts = query.split()
        if len(query_parts) >= 3 and query_parts[0] == "convert-file":
            format_type = query_parts[1]
            file_param = " ".join(query_parts[2:])
            if format_type in ["webm", "iphone", "youtube", "gif"]:
                return [
                    Result(
                        title=f"Convert {file_param} to {format_type.upper()}",
                        subtitle=f"Convert specified file to {format_type} format",
                        icon_name=(
                            "video-x-generic-symbolic"
                            if format_type != "gif"
                            else "image-x-generic-symbolic"
                        ),
                        action=lambda fp=file_param, ft=format_type: (
                            screen_capture_service.convert(ft, fp)
                        ),
                        relevance=1.0,
                        plugin_name=self.display_name,
                    )
                ]

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
                    icon_name="media-playback-stop-symbolic",
                    action=lambda: screen_capture_service.stop_recording(),
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
                    icon_name="camera-photo-symbolic",
                    action=lambda: screen_capture_service.screenshot("eDP-1"),
                    relevance=1.0,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Take Region Screenshot",
                    subtitle="Capture a selected region",
                    icon_name="camera-photo-symbolic",
                    action=lambda: screen_capture_service.screenshot("region"),
                    relevance=0.9,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Take Screenshot (Both Displays)",
                    subtitle="Capture both displays combined",
                    icon_name="video-joined-displays-symbolic",
                    action=lambda: screen_capture_service.screenshot("both"),
                    relevance=0.8,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Take Screenshot (HDMI-A-1)",
                    subtitle="Capture HDMI display",
                    icon_name="video-display-symbolic",
                    action=lambda: screen_capture_service.screenshot("HDMI-A-1"),
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
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record("eDP-1"),
                    relevance=0.7,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Region Recording",
                    subtitle="Record a selected region",
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record("selection"),
                    relevance=0.6,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Recording (HDMI-A-1)",
                    subtitle="Record HDMI display with audio",
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record("HDMI-A-1"),
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
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record(
                        "eDP-1", no_audio=True
                    ),
                    relevance=0.65,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Region Recording No Audio",
                    subtitle="Record a selected region without audio",
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record(
                        "selection", no_audio=True
                    ),
                    relevance=0.55,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Recording No Audio (HDMI-A-1)",
                    subtitle="Record HDMI display without audio",
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record(
                        "HDMI-A-1", no_audio=True
                    ),
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
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record("eDP-1", mode="hq"),
                    relevance=0.4,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start HQ Region Recording",
                    subtitle="High-quality region recording",
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record(
                        "selection", mode="hq"
                    ),
                    relevance=0.3,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start HQ Recording (HDMI-A-1)",
                    subtitle="High-quality HDMI recording",
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record("HDMI-A-1", mode="hq"),
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
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record("eDP-1", mode="gif"),
                    relevance=0.1,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start GIF Region Recording",
                    subtitle="Record selected region as GIF",
                    icon_name="media-record-symbolic",
                    action=lambda: screen_capture_service.record(
                        "selection", mode="gif"
                    ),
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
                    icon_name="video-x-generic-symbolic",
                    action=lambda: screen_capture_service.convert("webm"),
                    relevance=0.01,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Convert Latest for iPhone",
                    subtitle="Convert latest MKV recording for iPhone compatibility",
                    icon_name="video-x-generic-symbolic",
                    action=lambda: screen_capture_service.convert("iphone"),
                    relevance=0.01,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Convert Latest for YouTube",
                    subtitle="Convert latest recording for YouTube upload",
                    icon_name="video-x-generic-symbolic",
                    action=lambda: screen_capture_service.convert("youtube"),
                    relevance=0.01,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Convert Latest to GIF",
                    subtitle="Convert latest recording to GIF format",
                    icon_name="image-x-generic-symbolic",
                    action=lambda: screen_capture_service.convert("gif"),
                    relevance=0.01,
                    plugin_name=self.display_name,
                ),
            ]
        )

        return results
