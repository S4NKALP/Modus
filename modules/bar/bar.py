from fabric.hyprland.widgets import Language
from fabric.system_tray.widgets import SystemTray
from fabric.utils import (
    FormattedString,
    bulk_replace,
    exec_shell_command_async,
    get_relative_path,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window
from gi.repository import GLib
from modules.bar.components import (
    BatteryLabel,
    SystemInfo,
    TaskBar,
    workspace,
    Indicators,
    UpdatesWidget,
)
from services import sc
import snippets.iconss as icons


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

        self.recording_indicator = Button(
            name="recording-indicator",
            child=Label(name="recorder", markup=icons.record),
            visible=False,
            on_clicked=lambda *_: sc.screencast_stop(),
        )

        sc.connect(
            "recording", lambda _, status: self.on_recording_status_change(status)
        )

        self.date_time = DateTime(formatters=["%-I:%M 󰧞 %a %d %b"], name="datetime")

        self.battery = BatteryLabel()
        self.taskbar = TaskBar()
        self.stats = SystemInfo()
        self.tray = SystemTray(name="tray", icon_size=16, spacing=4)
        self.launcher = Button(
            name="logo",
            child=Label(name="logo-name", label="󰣇 󰫿󰫰󰫵"),
            on_clicked=lambda *_: GLib.spawn_command_line_async(
                "fabric-cli exec modus 'launcher.open(\"launcher\")'"
            ),
        )
        self.updates = UpdatesWidget()
        self.indicators = Indicators()
        self.button_config = Button(
            name="button-bar",
            on_clicked=lambda *_: exec_shell_command_async(
                f"python {get_relative_path('../../config/config.py')}"
            ),
            child=Label(name="button-bar-label", markup=icons.config),
        )

        self.applets = Box(
            name="applets",
            spacing=4,
            orientation="h",
            children=[
                self.language,
                self.indicators,
            ],
        )

        self.bar = CenterBox(
            name="bar",
            start_children=Box(
                name="start-container",
                spacing=8,
                orientation="h",
                children=[self.launcher, self.workspaces, self.stats, self.updates],
            ),
            center_children=Box(
                name="center-container",
                spacing=8,
                orientation="h",
                children=self.taskbar,
            ),
            end_children=Box(
                name="end-container",
                spacing=8,
                orientation="h",
                children=[
                    self.recording_indicator,
                    self.tray,
                    self.battery,
                    self.applets,
                    self.date_time,
                    self.button_config,
                ],
            ),
        )
        super().__init__(
            layer="top",
            anchor="left bottom right",
            exclusivity="auto",
            visible=True,
            child=self.bar,
        )

        self.hidden = False

    def on_recording_status_change(self, status):
        print(f"Recording status changed: {status}")
        self.recording_indicator.set_visible(status)

    def toggle_hidden(self):
        self.hidden = not self.hidden
        if self.hidden:
            self.bar.remove_style_class("visible")
            self.bar.add_style_class("hidden")
        else:
            self.bar.remove_style_class("hidden")
            self.bar.add_style_class("visible")
