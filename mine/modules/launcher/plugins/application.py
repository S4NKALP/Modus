from collections.abc import Iterator
from fabric.utils import DesktopApp, get_desktop_applications, os
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from thefuzz import fuzz, process

from modules.launcher.base import LauncherPlugin


class ApplicationPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "applications"

    @property
    def icon(self) -> str:
        return "system-search-symbolic"

    @property
    def keywords(self) -> list[str]:
        return []  # Default handler, no specific keywords

    def __init__(self, handler):
        super().__init__(handler)
        self._desktop_apps = []

    def stop(self):
        # No cleanup needed for application plugin
        pass

    def on_search(self, text: str) -> None:
        self.query_applications(text)

    def query_applications(self, text: str) -> None:
        if not text:
            return self.handler.done()
        self.handler.start("applications")
        self._desktop_apps = get_desktop_applications()
        filtered_apps: Iterator[DesktopApp] = iter(
            app
            for app, _ in process.extract(
                text,
                self._desktop_apps,
                scorer=fuzz.WRatio,
                processor=lambda app: getattr(app, "display_name", app) or "",
                limit=10,
            )
        )

        for app in filtered_apps:
            self.handler.slot_ready(
                Button(
                    style_classes="app-slot",
                    child=Box(
                        orientation="h",
                        spacing=12,
                        children=[
                            Image(
                                pixbuf=app.get_icon_pixbuf(), h_align="start", size=32
                            ),
                            Box(
                                orientation="v",
                                children=[
                                    Label(
                                        label=app.display_name or "Unknown",
                                        v_align="start",
                                        h_align="start",
                                        style_classes="app-title",
                                    )
                                ],
                            ).build(
                                lambda box, _: app.description
                                and box.add(
                                    Label(
                                        label=app.description,
                                        max_chars_width=42,
                                        ellipsization="middle",
                                        justification="center",
                                        style_classes="app-description",
                                        v_align="start",
                                        h_align="start",
                                    )
                                )
                            ),
                        ],
                    ),
                    tooltip_text=app.description,
                    on_clicked=lambda *_, app=app: (
                        self.launch_app(app),
                        self.handler.launched(),
                    ),
                ),
                "applications",
            )

        self.handler.done()

    def launch_app(self, app):
        old_cwd = os.getcwd()
        os.chdir(os.path.expanduser("~"))
        try:
            app.launch()
        finally:
            os.chdir(old_cwd)
