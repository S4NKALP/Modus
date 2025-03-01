from fabric.hyprland.widgets import Language
from fabric.system_tray.widgets import SystemTray
from fabric.utils import (
    FormattedString,
    bulk_replace,
    exec_shell_command_async,
    get_relative_path,
    bulk_connect,
)
from fabric.widgets.shapes import Corner
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window
from gi.repository import GLib
from modules.bar.components import (
    Battery,
    Metrics,
    workspace,
    SystemIndicators,
)
from services import sc
import utils.icons as icons


class Tray(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", **kwargs)  # Ensure vertical layout

        self.tray = Box(
            orientation="v",
            name="traybox",
            children=[
                SystemTray(name="tray", orientation="v", icon_size=16, spacing=4)
            ],
        )
        self.button = Button(
            child=Label(name="tray-revealer", markup=icons.chevron_down),
        )

        self.revealer = Revealer(transition_type="slide-up", transition_duration=1000)
        self.revealer.add(self.tray)

        bulk_connect(
            self.button,
            {
                "enter-notify-event": self._on_enter,
                "leave-notify-event": self._on_leave,
                "button-press-event": self.toggle_revealer,
            },
        )

        self.add(self.button)
        self.add(self.revealer)

    def _on_enter(self, *args):
        self.button.set_cursor("pointer")

    def _on_leave(self, *args):
        self.button.set_cursor("default")

    def toggle_revealer(self, *args):
        new_state = not self.revealer.get_reveal_child()
        self.revealer.set_reveal_child(new_state)
        new_icon = icons.chevron_up if new_state else icons.chevron_down
        self.button.get_child().set_markup(new_icon)


class Bar(Window):
    def __init__(self):
        self.workspaces = Button(child=workspace, name="workspaces")
        self.language = Language(
            formatter=FormattedString(
                "{replace_lang(language)}",
                replace_lang=lambda lang: bulk_replace(
                    lang,
                    (r".*Eng.*", r".*Nep.*"),
                    ("en", "np"),
                    regex=True,
                ),
            ),
        )
        self.bar_content = CenterBox(name="bar", orientation="v")
        self.recording_indicator = Button(
            name="recording-indicator",
            child=Label(name="recorder", markup=icons.record),
            visible=False,
            on_clicked=lambda *_: sc.screencast_stop(),
        )

        sc.connect("recording", self.on_recording_status_change)

        self.date_time = DateTime(
            v_align="center",
            formatters=["%I\n%M \n󰧞 \n%a\n%d\n%b"],
            name="datetime",
        )
        self.battery = Battery()
        self.launcher = Button(
            name="logo",
            child=Label(
                h_align="center",
                v_align="center",
                name="logo-name",
                label="󰣇 \n󰫿\n󰫰\n󰫵",
            ),
            on_clicked=lambda *_: GLib.spawn_command_line_async(
                "fabric-cli exec modus 'launcher.open(\"launcher\")'"
            ),
        )
        self.button_config = Button(
            name="button-bar",
            on_clicked=lambda *_: exec_shell_command_async(
                f"python {get_relative_path('../../config/config.py')}"
            ),
            child=Label(name="button-bar-label", markup=icons.config),
        )
        self.stats = Metrics()
        self.tray = Tray()
        self.indicators = SystemIndicators()
        self.applets = Box(
            name="system-indicators",
            spacing=4,
            orientation="v",
            children=[self.language, self.indicators],
        )

        self.bar_content.end_children = [
            Box(
                name="end-container",
                orientation="v",
                spacing=4,
                children=[
                    self.recording_indicator,
                    self.tray,
                    self.battery,
                    self.applets,
                    self.date_time,
                    self.button_config,
                ],
            ),
        ]
        self.bar_content.start_children = [
            Box(
                name="start-container",
                orientation="v",
                spacing=4,
                children=[self.launcher, self.workspaces, self.stats],
            ),
        ]

        super().__init__(
            layer="top",
            anchor="top left bottom",
            exclusivity="auto",
            visible=True,
            child=self.bar_content,
        )
        self.hidden = False

    def on_recording_status_change(self, _, status):
        self.recording_indicator.set_visible(status)

    def toggle_hidden(self):
        self.hidden = not self.hidden
        if self.hidden:
            self.bar_content.add_style_class("hidden")
            self.bar_content.remove_style_class("visible")
            self.set_property("visible", False)
        else:
            self.bar_content.add_style_class("visible")
            self.bar_content.remove_style_class("hidden")
            self.set_property("visible", True)


class ScreenCorners(Window):
    def __init__(self):
        super().__init__(
            layer="top",
            anchor="top left bottom right",
            pass_through=True,
            child=Box(
                orientation="vertical",
                children=[
                    Box(
                        children=[
                            self.make_corner("top-left"),
                            Box(h_expand=True),
                            self.make_corner("top-right"),
                        ]
                    ),
                    Box(v_expand=True),
                    Box(
                        children=[
                            self.make_corner("bottom-left"),
                            Box(h_expand=True),
                            self.make_corner("bottom-right"),
                        ]
                    ),
                ],
            ),
        )

    def make_corner(self, orientation) -> Box:
        return Box(
            h_expand=False,
            v_expand=False,
            name="bar-corner",
            children=Corner(
                orientation=orientation,
                size=15,
            ),
        )
