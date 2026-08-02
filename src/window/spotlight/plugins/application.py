import os
from typing import Any

from fabric.utils import DesktopApp, logger
from gi.repository import Gio

from utils.functions import fuzzy_score, get_desktop_apps, invalidate_desktop_apps_cache
from window.spotlight.api import SearchResult, SpotlightPlugin


def _get_desktop_dirs() -> list[str]:
    dirs: list[str] = []
    xdg_data = os.environ.get("XDG_DATA_HOME", "")
    if xdg_data:
        dirs.append(os.path.join(xdg_data, "applications"))
    home = os.path.expanduser("~")
    dirs.append(os.path.join(home, ".local", "share", "applications"))
    xdg_data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    for d in xdg_data_dirs.split(":"):
        dirs.append(os.path.join(d, "applications"))
    dirs.append("/var/lib/flatpak/exports/share/applications")
    dirs.append(
        os.path.join(
            home, ".local", "share", "flatpak", "exports", "share", "applications"
        )
    )
    seen: set[str] = set()
    unique: list[str] = []
    for d in dirs:
        real = os.path.realpath(d)
        if real not in seen and os.path.isdir(real):
            seen.add(real)
            unique.append(real)
    return unique


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
        self._dirty: bool = True
        self._monitors: list[Gio.FileMonitor] = []

    def initialize(self) -> None:
        self._desktop_apps = get_desktop_apps()
        self._dirty = False
        self._start_watching()

    def _start_watching(self) -> None:
        for path in _get_desktop_dirs():
            try:
                gf = Gio.File.new_for_path(path)
                monitor = gf.monitor_directory(Gio.FileMonitorFlags.NONE, None)
                monitor.connect("changed", self._on_dir_changed)
                self._monitors.append(monitor)
            except Exception as e:
                logger.warning(f"[application] monitor {path} failed: {e}")

    def _on_dir_changed(self, _monitor, _file, _other, event):
        if event in (
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.DELETED,
            Gio.FileMonitorEvent.MOVED_IN,
            Gio.FileMonitorEvent.MOVED_OUT,
        ):
            invalidate_desktop_apps_cache()
            self._dirty = True

    def cleanup(self) -> None:
        for m in self._monitors:
            m.cancel()
        self._monitors.clear()
        self._desktop_apps = []

    def search(self, query: str, token: Any) -> list[SearchResult]:
        if not query:
            return []

        if self._dirty:
            try:
                self._desktop_apps = get_desktop_apps()
                self._dirty = False
            except Exception as e:
                logger.warning(f"[application] get_desktop_apps() failed: {e}")

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
        from window.globalmenu.launch import launch_desktop_app

        launch_desktop_app(app)


PLUGIN = ApplicationPlugin
