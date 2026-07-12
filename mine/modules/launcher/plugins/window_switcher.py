import json
from collections.abc import Iterator

from fabric.utils import Gdk, get_desktop_applications, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin
from utils.functions import is_special_workspace, run_command


class WindowSwitcherPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "windows"

    @property
    def icon(self) -> str:
        return "preferences-system-windows-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["win", "windows"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self.windows: list[dict] = []
        self._desktop_apps = get_desktop_applications()

    def on_search(self, text: str) -> None:
        self.query_windows(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0

    def _get_windows(self) -> list[dict]:
        result = run_command(["hyprctl", "-j", "clients"], timeout=5)
        if result.returncode != 0 or not isinstance(result.stdout, str):
            return []

        clients = json.loads(result.stdout)
        filtered_clients = []

        for client in clients:
            if (
                not client.get("mapped", False)
                or not client.get("visible", True)
                or is_special_workspace(client)
            ):
                continue
            filtered_clients.append(client)

        return filtered_clients

    def _get_window_icon_pixbuf(self, window: dict):
        class_name = window.get("class", "").lower()
        title = window.get("title", "").lower()

        for app in self._desktop_apps:
            app_name = (app.name or "").lower()
            if (
                class_name in app_name
                or app_name in class_name
                or any(word in app_name for word in title.split() if len(word) > 2)
            ):
                return app.get_icon_pixbuf()
        return None

    def _get_workspace_name(self, workspace_id: int) -> str:
        result = run_command(["hyprctl", "-j", "workspaces"], timeout=3)
        if result.returncode != 0 or not isinstance(result.stdout, str):
            return f"Workspace {workspace_id}"

        workspaces = json.loads(result.stdout)
        for workspace in workspaces:
            if workspace.get("id") == workspace_id:
                return workspace.get("name", f"Workspace {workspace_id}")
        return f"Workspace {workspace_id}"

    def query_windows(self, text: str) -> None:
        self.handler.start("windows")
        self.windows = self._get_windows()

        if not self.windows:
            self._show_no_windows()
            return

        filtered_windows = self._filter_windows(text)
        # We need to check if the iterator is empty, but we can't easily do that without consuming it.
        # So we'll convert to list first if needed, or just handle the empty case in bake.
        # However, _filter_windows returns an iterator. Let's modify it to return a list or check emptiness.
        # Actually, let's just try to bake. If it returns False immediately, we can show no results?
        # But _bake_next_window_slot calls done() if empty.
        # Let's peek? No.
        # Let's just pass it. If it's empty, _bake_next_window_slot will just call done.
        # But we might want to show "No matching windows" if the filter returns nothing but windows exist.
        # So let's consume the iterator into a list for checking.
        filtered_list = list(filtered_windows)
        if not filtered_list:
            # If we had windows but none matched, we could show "No results".
            # But the original code just returned. Let's stick to that or show no results.
            # Showing no results is better UX.
            self._show_no_results()
            return

        self._query_handler = idle_add(
            self._bake_next_window_slot, iter(filtered_list), pin=True
        )

    def _filter_windows(self, text: str) -> Iterator[dict]:
        if not text.strip():
            return iter(self.windows)

        text_lower = text.lower()
        filtered_windows = []

        for window in self.windows:
            title = window.get("title", "").lower()
            class_name = window.get("class", "").lower()
            initial_class = window.get("initialClass", "").lower()

            if (
                text_lower in title
                or text_lower in class_name
                or text_lower in initial_class
            ):
                filtered_windows.append(window)

        def sort_key(window):
            title = window.get("title", "").lower()
            class_name = window.get("class", "").lower()

            if text_lower in (title, class_name):
                return 0
            if title.startswith(text_lower) or class_name.startswith(text_lower):
                return 1
            return 2

        filtered_windows.sort(key=sort_key)
        return iter(filtered_windows)

    def _show_no_windows(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot window-no-windows",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Image(icon_name="window-close", size=32),
                        Label(
                            label="No open windows found",
                            style_classes="window-no-windows-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="No windows are currently open",
            ),
            "windows",
        )
        self.handler.done()

    def _show_no_results(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot window-no-results",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No windows match your search",
                            style_classes="window-no-results-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "windows",
        )
        self.handler.done()

    def _bake_next_window_slot(self, iterator: Iterator[dict]) -> bool:
        window = next(iterator, None)
        if window is None:
            idle_add(self.handler.done)
            return False

        self._create_window_slot(window)
        return True

    def _create_window_slot(self, window: dict) -> None:
        title = window.get("title", "Unknown Window")
        class_name = window.get("class", "Unknown")
        workspace_id = window.get("workspace", {}).get("id", 0)
        workspace_name = self._get_workspace_name(workspace_id)
        icon_pixbuf = self._get_window_icon_pixbuf(window)

        display_title = title[:40] + "..." if len(title) > 40 else title
        display_class = class_name[:30] + "..." if len(class_name) > 30 else class_name

        slot_content = Box(
            orientation="h",
            spacing=12,
            children=[
                Image(pixbuf=icon_pixbuf, h_align="start", size=32)
                if icon_pixbuf
                else Image(
                    icon_name="application-x-executable", h_align="start", size=32
                ),
                Box(
                    orientation="v",
                    children=[
                        Label(
                            label=f"{display_title} • {workspace_name}",
                            style_classes="window-title",
                            h_align="start",
                            v_align="start",
                        ),
                        Label(
                            label=display_class,
                            style_classes="window-subtitle",
                            h_align="start",
                            v_align="start",
                        ),
                    ],
                ),
            ],
        )

        main_content = slot_content

        slot_widget = Button(
            style_classes="app-slot window-slot",
            child=main_content,
            tooltip_text=f"Enter: Focus window\nShift+Enter: Close window\nTitle: {title}\nClass: {class_name}\nWorkspace: {workspace_name}",
            on_clicked=lambda *_: self._focus_window(window),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, w=window: self._on_slot_key_press(widget, event, w),
        )

        self.handler.slot_ready(slot_widget, "windows")

    def _focus_window(self, window: dict) -> None:
        address = window.get("address")
        if address:
            run_command(
                ["hyprctl", "dispatch", "focuswindow", f"address:{address}"], timeout=3
            )
            self.handler.launched()

    def _close_window(self, window: dict) -> None:
        address = window.get("address")
        if address:
            run_command(
                ["hyprctl", "dispatch", "closewindow", f"address:{address}"], timeout=3
            )

    def _on_slot_key_press(self, widget, event, window: dict) -> bool:
        if not event or event.keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False

        if event.state & Gdk.ModifierType.SHIFT_MASK:
            self._close_window(window)
        else:
            self._focus_window(window)
        return True

    def handle_external(self, command: str, args: str) -> None:
        # Map external commands if needed
        pass
