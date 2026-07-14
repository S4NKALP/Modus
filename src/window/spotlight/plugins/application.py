import time
from typing import Any

from fabric.utils import DesktopApp, get_desktop_applications, logger

from utils.functions import fuzzy_score
from window.spotlight.api import SearchResult, SpotlightPlugin


class ApplicationPlugin(SpotlightPlugin):
    id = "applications"
    name = "Applications"
    icon = "system-search-symbolic"
    keywords: list[str] = []
    searchable = True
    priority = 10

    def __init__(self, context):
        super().__init__(context)
        self._desktop_apps: list[DesktopApp] = []
        self._apps_loaded_at: float = 0.0
        self._apps_ttl: float = 1.0

    def initialize(self) -> None:
        self._desktop_apps = get_desktop_applications()

    def cleanup(self) -> None:
        self._desktop_apps = []

    def search(self, query: str, token: Any) -> list[SearchResult]:
        if not query:
            return []

        # Re-scan (throttled) so newly installed .desktop files appear
        # without a restart, while avoiding a disk scan on every keystroke.
        now = time.monotonic()
        if now - self._apps_loaded_at > self._apps_ttl:
            try:
                self._desktop_apps = get_desktop_applications()
                self._apps_loaded_at = now
            except Exception as e:
                logger.warning(
                    f"[application] self._desktop_apps = get_desktop_applications() failed: {e}"
                )

        results: list[SearchResult] = []
        for app in self._desktop_apps:
            display_name = getattr(app, "display_name", "") or ""
            if not display_name:
                continue

            raw_score = fuzzy_score(query, display_name)
            if raw_score <= 0:
                continue

            score = raw_score / 100.0

            results.append(
                SearchResult(
                    id=getattr(app, "desktop_id", "") or display_name,
                    title=display_name,
                    subtitle=getattr(app, "description", "") or "",
                    icon_name="",
                    score=score,
                    action=lambda a=app: self._launch_app(a),
                    render_type="app",
                    plugin_name=self.name,
                    plugin_id=self.id,
                    metadata={"desktop_app": app},
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:10]

    @staticmethod
    def _launch_app(app: DesktopApp) -> None:
        from globalmenu.launch import launch_desktop_app

        launch_desktop_app(app)


PLUGIN = ApplicationPlugin
