"""
Screencapture plugin for the launcher.
Provides screenshot and screen recording functionality.
"""

from typing import List

from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
from services.screencapture import ScreenCapture
from utils.icons import screenrecord, screenshots, ssfull, ssregion, stop


class ScreencapturePlugin(PluginBase):
    """
    Plugin for taking screenshots and screen recordings.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Screencapture"
        self.description = "Take screenshots and screen recordings"
        self.screencapture = ScreenCapture()

    def initialize(self):
        """Initialize the screencapture plugin."""
        self.set_triggers(["sc", "sc "])

    def cleanup(self):
        """Cleanup the screencapture plugin."""
        pass

    def query(self, query_string: str) -> List[Result]:
        """Search for screencapture actions based on query."""
        # Remove the trigger word from the query
        query = query_string.replace("screencapture", "").strip().lower()

        results = []

        # If recording is active, show stop button first
        if self.screencapture.is_recording:
            results.append(
                Result(
                    title="Stop Recording",
                    subtitle="Stop the current screen recording",
                    icon_markup=stop,
                    action=self.screencapture.screencast_stop,
                    relevance=1.0,
                    plugin_name=self.display_name,
                )
            )
            return results

        # Screenshot actions
        results.extend(
            [
                Result(
                    title="Take Screenshot",
                    subtitle="Capture the entire screen",
                    icon_markup=ssfull,
                    action=lambda: self.screencapture.screenshot(fullscreen=True),
                    relevance=1.0,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Take Region Screenshot",
                    subtitle="Capture a selected region",
                    icon_markup=ssregion,
                    action=lambda: self.screencapture.screenshot(fullscreen=False),
                    relevance=0.9,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Take Screenshot (Clipboard Only)",
                    subtitle="Capture and copy to clipboard",
                    icon_markup=screenshots,
                    action=lambda: self.screencapture.screenshot(save_copy=False),
                    relevance=0.8,
                    plugin_name=self.display_name,
                ),
            ]
        )

        # Screen recording actions
        results.extend(
            [
                Result(
                    title="Start Fullscreen Recording",
                    subtitle="Record the entire screen",
                    icon_markup=screenrecord,
                    action=lambda: self.screencapture.screencast_start(fullscreen=True),
                    relevance=0.7,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Region Recording",
                    subtitle="Record a selected region",
                    icon_markup=screenrecord,
                    action=lambda: self.screencapture.screencast_start(
                        fullscreen=False
                    ),
                    relevance=0.6,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Fullscreen Recording with Audio",
                    subtitle="Record entire screen with system audio",
                    icon_markup=screenrecord,
                    action=lambda: self.screencapture.screencast_start(
                        fullscreen=True, audio=True
                    ),
                    relevance=0.5,
                    plugin_name=self.display_name,
                ),
                Result(
                    title="Start Region Recording with Audio",
                    subtitle="Record selected region with system audio",
                    icon_markup=screenrecord,
                    action=lambda: self.screencapture.screencast_start(
                        fullscreen=False, audio=True
                    ),
                    relevance=0.4,
                    plugin_name=self.display_name,
                ),
            ]
        )

        return results
