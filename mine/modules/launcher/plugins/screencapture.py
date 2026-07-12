from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin
from services import screen_capture_service


class ScreenCapturePlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "screen_capture"

    @property
    def icon(self) -> str:
        return "camera-photo-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["screen", "sc"]

    def __init__(self, handler):
        super().__init__(handler)
        self.service = screen_capture_service

    def on_search(self, text: str) -> None:
        self.query_screen_capture(text)

    def stop(self):
        pass

    def is_recording(self):
        return self.service.is_recording

    def query_screen_capture(self, text: str) -> None:
        self._show_main_options()

    def _show_main_options(self):
        self.handler.start("screen_capture")

        options = [
            ("Screenshot Selection", "camera-photo-symbolic", "screenshot selection"),
            ("Screenshot Fullscreen", "camera-photo-symbolic", "screenshot fullscreen"),
            ("Record Selection", "camera-video-symbolic", "record selection"),
            ("Record Fullscreen", "camera-video-symbolic", "record fullscreen"),
            ("Record Selection No Audio", "camera-video-symbolic", "record no audio"),
            (
                "Record Fullscreen No Audio",
                "camera-video-symbolic",
                "record fullscreen no audio",
            ),
        ]

        if self.is_recording():
            options.insert(
                0, ("Stop Recording", "media-playback-stop-symbolic", "stop")
            )

        for title, icon, command in options:
            self.handler.slot_ready(
                Button(
                    style_classes="app-slot",
                    child=Box(
                        orientation="h",
                        spacing=12,
                        children=[
                            Image(icon_name=icon, style_classes="app-icon"),
                            Label(
                                label=title,
                                style_classes="app-name",
                                h_align="start",
                            ),
                        ],
                    ),
                    on_clicked=lambda _, cmd=command: self._execute_command(cmd),
                ),
                "screen_capture",
            )

        self.handler.done()

    def _execute_command(self, command):
        self.handler.launched()

        actions = {
            "stop": lambda: self.service.stop_recording(),
            "screenshot selection": lambda: self.service.screenshot(fullscreen=False),
            "screenshot fullscreen": lambda: self.service.screenshot(fullscreen=True),
            "record selection": lambda: self.service.record(
                fullscreen=False, no_audio=False
            ),
            "record fullscreen": lambda: self.service.record(
                fullscreen=True, no_audio=False
            ),
            "record no audio": lambda: self.service.record(
                fullscreen=False, no_audio=True
            ),
            "record fullscreen no audio": lambda: self.service.record(
                fullscreen=True, no_audio=True
            ),
        }

        # Add aliases
        aliases = {
            "region": "screenshot selection",
            "full": "screenshot fullscreen",
            "select": "screenshot selection",
        }

        cmd = aliases.get(command, command)

        if cmd in actions:
            actions[cmd]()

    def handle_external(self, command: str, args: str) -> None:
        if args:
            self._execute_command(args)
        else:
            self.handler.launched()
