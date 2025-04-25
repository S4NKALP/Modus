from fabric.widgets.centerbox import CenterBox
from fabric.widgets.stack import Stack
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.box import Box
from modules.launcher.components import (
    AppLauncher,
    BluetoothConnections,
    EmojiPicker,
    PowerMenu,
    Sh,
    WallpaperSelector,
    WifiManager,
    Calendar,
    Dashboard,
    Toolbox,
    Kanban,
    TmuxManager,
    WindowSwitcher,
    NotificationCenter,
    ClipHistory,
)


class Launcher(Window):
    def __init__(self, **kwargs):
        super().__init__(
            layer="top",
            anchor="center",
            keyboard_mode="none",
            exclusivity="normal",
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.dashboard = Dashboard(launcher=self)
        self.wallpapers = WallpaperSelector(launcher=self)
        self.power = PowerMenu(launcher=self)
        self.emoji = EmojiPicker(launcher=self)
        self.bluetooth = BluetoothConnections(launcher=self)
        self.sh = Sh(launcher=self)
        self.wifi = WifiManager()
        self.calendar = Calendar()
        self.tools = Toolbox(launcher=self)
        self.kanban = Kanban()
        self.tmux = TmuxManager(launcher=self)
        self.window_switcher = WindowSwitcher(launcher=self)
        self.notification_center = NotificationCenter(launcher=self)
        self.cliphist = ClipHistory(launcher=self)

        # Wrap the dashboard in a Box container
        self.dashboard = Box(
            name="dashboard",
            orientation="h",
            spacing=10,
            children=[self.dashboard],
        )
        self.launcher = AppLauncher(launcher=self)

        self.stack = Stack(
            name="launcher-content",
            v_expand=True,
            h_expand=True,
            transition_type="crossfade",
            transition_duration=100,
            children=[
                self.launcher,
                self.wallpapers,
                self.power,
                self.emoji,
                self.cliphist,
                self.bluetooth,
                self.sh,
                self.wifi,
                self.calendar,
                self.tools,
                self.kanban,
                self.tmux,
                self.window_switcher,
                self.notification_center,
            ],
        )

        self.launcher_box = CenterBox(
            name="launcher",
            orientation="v",
            start_children=self.stack,
            end_children=self.dashboard,
        )

        self.add(self.launcher_box)
        self.show_all()
        self.hide()
        self.add_keybinding("Escape", lambda *_: self.close())

    def close(self):
        self.set_keyboard_mode("none")
        self.hide()

        for widget in [
            self.launcher,
            self.wallpapers,
            self.power,
            self.emoji,
            self.cliphist,
            self.bluetooth,
            self.sh,
            self.wifi,
            self.calendar,
            self.tools,
            self.kanban,
            self.tmux,
            self.window_switcher,
            self.notification_center,
        ]:
            if hasattr(widget, "viewport") and widget.viewport:
                widget.viewport.hide()

        for style in [
            "launcher",
            "wallpapers",
            "power",
            "emoji",
            "cliphist",
            "bluetooth",
            "sh",
            "wifi",
            "calendar",
            "tools",
            "kanban",
            "tmux",
            "window-switcher",
            "notification-center",
        ]:
            self.stack.remove_style_class(style)

        return True

    def open(self, widget):
        widgets = {
            "launcher": self.launcher,
            "wallpapers": self.wallpapers,
            "power": self.power,
            "emoji": self.emoji,
            "cliphist": self.cliphist,
            "bluetooth": self.bluetooth,
            "sh": self.sh,
            "wifi": self.wifi,
            "calendar": self.calendar,
            "tools": self.tools,
            "kanban": self.kanban,
            "tmux": self.tmux,
            "window-switcher": self.window_switcher,
            "notification-center": self.notification_center,
        }
        self.set_keyboard_mode("exclusive")
        self.show()

        for w in widgets.values():
            w.hide()
            self.dashboard.hide()
        for style in widgets.keys():
            self.stack.remove_style_class(style)

        if widget in widgets:
            self.stack.get_style_context().add_class(widget)
            self.stack.set_visible_child(widgets[widget])
            widgets[widget].show()

            if widget == "launcher":
                self.launcher.open_launcher()
                self.launcher.search_entry.set_text("")
                self.launcher.search_entry.grab_focus()
                self.dashboard.show()

            elif widget == "wallpapers":
                self.wallpapers.search_entry.set_text("")
                self.wallpapers.search_entry.grab_focus()
                self.wallpapers.viewport.show()

            elif widget == "tmux":
                self.tmux.open_manager()
                self.tmux.search_entry.set_text("")
                self.tmux.search_entry.grab_focus()

            elif widget == "emoji":
                self.emoji.open_picker()
                self.emoji.search_entry.set_text("")
                self.emoji.search_entry.grab_focus()

            elif widget == "cliphist":
                self.cliphist.open()

            elif widget == "sh":
                self.sh.open_sh()

            elif widget == "window-switcher":
                self.window_switcher.open_switcher()

            elif widget == "notification-center":
                self.notification_center.open_center()
