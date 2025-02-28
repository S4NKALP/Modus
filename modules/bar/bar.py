from typing import Literal
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
    UpdatesWidget,
)
from services import sc
import utils.icons as icons


class StatusBarCorner(Box):
    def __init__(self, corner: Literal["top-right", "top-left"]):
        super().__init__(
            style="margin-bottom: 15px;",
            name="bar-corner",
            children=Corner(
                orientation=corner,
                size=15,
            ),
        )


class Tray(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tray = Box(
            name="left-tray",
            children=[SystemTray(name="tray", icon_size=16, spacing=4)],
        )
        self.profile = Button(
            child=Label(name="tray-revealer", markup=icons.chevron_left)
        )
        self.revealer = Revealer(transition_type="slide-left", transition_duration=1000)
        self.revealer.add(self.tray)

        bulk_connect(
            self.profile,
            {
                "enter-notify-event": self._on_enter,
                "leave-notify-event": self._on_leave,
                "button-press-event": self.toggle_revealer,
            },
        )

        self.add(self.profile)
        self.add(self.revealer)

    def _on_enter(self, *args):
        self.profile.set_cursor("pointer")

    def _on_leave(self, *args):
        self.profile.set_cursor("default")

    def toggle_revealer(self, *args):
        new_state = not self.revealer.get_reveal_child()
        self.revealer.set_reveal_child(new_state)
        new_icon = icons.chevron_right if new_state else icons.chevron_left
        self.profile.get_child().set_markup(new_icon)


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
        self.bar_content = CenterBox(name="center-bar")
        self.recording_indicator = Button(
            name="recording-indicator",
            child=Label(name="recorder", markup=icons.record),
            visible=False,
            on_clicked=lambda *_: sc.screencast_stop(),
        )

        sc.connect("recording", self.on_recording_status_change)

        self.date_time = DateTime(formatters=["%-I:%M 󰧞 %a %d %b"], name="datetime")
        self.battery = Battery()
        self.launcher = Button(
            name="logo",
            child=Label(name="logo-name", label="󰣇 󰫿󰫰󰫵"),
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
        self.updates = UpdatesWidget()
        self.tray = Tray()
        self.indicators = SystemIndicators()
        self.applets = Box(
            name="system-indicators",
            spacing=4,
            orientation="h",
            children=[self.language, self.indicators],
        )

        self.bar_content.end_children = [
            StatusBarCorner("top-right"),
            Box(
                name="bar",
                spacing=4,
                children=[
                    self.recording_indicator,
                    self.tray,
                    self.battery,
                    self.applets,
                    self.date_time,
                    self.button_config,
                ],
                style_classes="end-container",
            ),
        ]

        self.bar_content.start_children = [
            Box(
                name="bar",
                spacing=4,
                children=[self.launcher, self.workspaces, self.stats, self.updates],
                style_classes="start-container",
            ),
            StatusBarCorner("top-left"),
        ]

        super().__init__(
            layer="top",
            anchor="left top right",
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
