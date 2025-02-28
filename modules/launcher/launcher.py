from fabric.widgets.centerbox import CenterBox
from fabric.widgets.stack import Stack
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.box import Box
from modules.launcher.components import (
    AppLauncher,
    BluetoothConnections,
    Cliphist,
    Emoji,
    PowerMenu,
    Sh,
    TodoManager,
    WallpaperSelector,
    WifiManager,
    Calendar,
    Dashboard,
)


class Launcher(Window):
    def __init__(self, **kwargs):
        super().__init__(
            layer="top",
            anchor="center",
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.dashboard = Dashboard(launcher=self)
        self.wallpapers = WallpaperSelector(launcher=self)
        self.power = PowerMenu(launcher=self)
        self.emoji = Emoji(launcher=self)
        self.cliphist = Cliphist(launcher=self)
        self.todo = TodoManager()
        self.bluetooth = BluetoothConnections(launcher=self)
        self.sh = Sh(launcher=self)
        self.wifi = WifiManager()
        self.calendar = Calendar()

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
                self.todo,
                self.bluetooth,
                self.sh,
                self.wifi,
                self.calendar,
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
        self.add_keybinding("Escape", self._on_escape)

    def _on_escape(self, *args):
        return self.close()

    def close(self):
        self.set_keyboard_mode("none")
        self.hide()

        for widget in [
            self.launcher,
            self.wallpapers,
            self.power,
            self.emoji,
            self.cliphist,
            self.todo,
            self.bluetooth,
            self.sh,
            self.wifi,
            self.calendar,
        ]:
            if hasattr(widget, "viewport") and widget.viewport:
                widget.viewport.hide()

        for style in [
            "launcher",
            "wallpapers",
            "power",
            "emoji",
            "cliphist",
            "todo",
            "bluetooth",
            "sh",
            "wifi",
            "calendar",
        ]:
            self.stack.remove_style_class(style)

        return True

    def open(self, widget):
        self.set_keyboard_mode("exclusive")
        self.show()

        widgets = {
            "launcher": self.launcher,
            "wallpapers": self.wallpapers,
            "power": self.power,
            "emoji": self.emoji,
            "cliphist": self.cliphist,
            "todo": self.todo,
            "bluetooth": self.bluetooth,
            "sh": self.sh,
            "wifi": self.wifi,
            "calendar": self.calendar,
        }

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

            elif widget == "emoji":
                self.emoji.open_launcher()
                self.emoji.search_entry.set_text("")
                self.emoji.search_entry.grab_focus()

            elif widget == "cliphist":
                self.cliphist.open_launcher()
                self.cliphist.search_entry.set_text("")
                self.cliphist.search_entry.grab_focus()

            elif widget == "todo":
                self.todo.open_launcher()
                self.todo.todo_entry.set_text("")
                self.todo.todo_entry.grab_focus()

            elif widget == "sh":
                self.sh.open_launcher()
                self.sh.search_entry.set_text("")
                self.sh.search_entry.grab_focus()
