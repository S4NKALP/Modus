from fabric.core.service import Service, Signal
from fabric.utils import Gdk, logger

from window.desktop.main import DesktopWidgetWindow, position_manager


class DesktopWidgetService(Service):
    _instance: "DesktopWidgetService | None" = None

    @staticmethod
    def get_instance() -> "DesktopWidgetService":
        if DesktopWidgetService._instance is None:
            DesktopWidgetService._instance = DesktopWidgetService()
        return DesktopWidgetService._instance

    @Signal
    def widgets_changed(self, monitor_id: int) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._windows: dict[int, DesktopWidgetWindow] = {}

        display = Gdk.Display.get_default()
        if display:
            display.connect("monitor-added", self._on_monitor_added)
            display.connect("monitor-removed", self._on_monitor_removed)

        self._sync_monitors()

        for mid, win in self._windows.items():
            win.rebuild()

    def _sync_monitors(self) -> None:
        display = Gdk.Display.get_default()
        current = set(range(display.get_n_monitors()))
        existing = set(self._windows.keys())
        for mid in existing - current:
            self._remove_window(mid)
        for mid in current - existing:
            self._add_window(mid)

    def _add_window(self, monitor_id: int) -> None:
        if monitor_id in self._windows:
            return
        win = DesktopWidgetWindow(monitor_id)
        self._windows[monitor_id] = win
        logger.info(f"[DesktopWidgetService] window created for monitor {monitor_id}")

    def _remove_window(self, monitor_id: int) -> None:
        win = self._windows.pop(monitor_id, None)
        if win:
            win.destroy()
            logger.info(
                f"[DesktopWidgetService] window removed for monitor {monitor_id}"
            )

    def _on_monitor_added(self, _display, _monitor) -> None:
        logger.info("[DesktopWidgetService] monitor added, resyncing...")
        self._sync_monitors()

    def _on_monitor_removed(self, _display, _monitor) -> None:
        logger.info("[DesktopWidgetService] monitor removed, resyncing...")
        self._sync_monitors()

    def place(
        self, monitor_id: int, key: str, px: float = 0.02, py: float = 0.04
    ) -> bool:
        position_manager.save_position(monitor_id, key, px, py)
        win = self._windows.get(monitor_id)
        if win:
            win.add_widget(key, px, py)
        self.widgets_changed(monitor_id)
        return True

    def remove(self, monitor_id: int, key: str) -> bool:
        removed = position_manager.remove(monitor_id, key)
        if not removed:
            return False
        win = self._windows.get(monitor_id)
        if win:
            win.remove_widget(key)
        self.widgets_changed(monitor_id)
        return True

    def get_window(self, monitor_id: int) -> "DesktopWidgetWindow | None":
        return self._windows.get(monitor_id)
