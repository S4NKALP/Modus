from fabric.utils import GLib

from modules.launcher.base import LauncherPlugin
from services.google_lens import GoogleLens


class GoogleLensPlugin(LauncherPlugin):
    def __init__(self, handler):
        super().__init__(handler)
        self.lens_service = GoogleLens.get_initial()

    @property
    def name(self) -> str:
        return "Google Lens"

    @property
    def icon(self) -> str:
        return "camera-photo-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["lens", "google lens"]

    def on_search(self, text: str) -> None:
        pass

    def on_activate(self) -> None:
        self.handler.launched()
        GLib.timeout_add(200, self.lens_service.search)

    def on_deactivate(self) -> None:
        pass

    def on_submit(self, text: str) -> None:
        pass
