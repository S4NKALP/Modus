from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.system_tray.widgets import SystemTray
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.hyprland.widgets import ActiveWindow
from fabric.utils import truncate, FormattedString

from modules.bar.components.workspaces import workspace
from modules.bar.components.language import LanguageWidget
from modules.bar.components.auto_hide import AutoHideBarController
from modules.corners import MyCorner
from modules.bar.components.power_menu import Power
from modules.bar.components.system_indicators import SystemIndicators
from modules.bar.components.metrics import Metrics


class Bar(Window):
    """Main bar widget for the desktop environment."""

    def __init__(self):
        super().__init__(
            layer="top",
            anchor="top",
            visible=True,
        )

        self.active_window = ActiveWindow(
            name="active-window",
            h_expand=True,
            h_align="fill",
            formatter=FormattedString(
                f"{{'Desktop' if not win_class or win_class == 'unknown' else win_class}}",
                truncate=truncate,
            ),
        )
        self.workspaces = Button(
            name="workspaces",
            child=workspace,
        )

        self.language = LanguageWidget()
        self.date_time = DateTime(name="date-time", formatters=["%-I:%M:%p 󰧞 %a %d %b"])
        self.tray = SystemTray(name="tray", spacing=4, icon_size=16)
        self.power_menu = Power()
        self.system_indicators = SystemIndicators()
        self.metrics = Metrics()
        
        # Main bar content

        self.bar = CenterBox(
            name="bar",
            start_children=Box(spacing=4, orientation="h", children=self.workspaces),
            center_children=Box(
                spacing=4, orientation="h", children=self.active_window
            ),
            end_children=Box(
                spacing=4,
                orientation="h",
                children=[
                    self.date_time,
                    self.metrics,
                    self.system_indicators,
                    self.tray,
                    self.power_menu,
                ],
            ),
        )

        # Event handling and corners
        self.eventbox = EventBox()
        self.eventbox.add(self.bar)

        self.corner_left = Box(
            name="bar-corner-left",
            orientation="v",
            h_align="start",
            children=[
                MyCorner("top-right"),
                Box(),
            ],
        )
        self.corner_left.set_margin_start(56)

        self.corner_right = Box(
            name="bar-corner-right",
            orientation="v",
            h_align="end",
            children=[
                MyCorner("top-left"),
                Box(),
            ],
        )
        self.corner_right.set_margin_end(56)
        self.main_box = Box(
            name="bar-container",
            orientation="h",
            h_expand=True,
            children=[
                self.corner_left,
                self.eventbox,
                self.corner_right,
            ],
        )

        # Add hover activator
        self.hover_activator = EventBox(name="hover-activator", v_align="start")
        self.hover_activator.set_size_request(-1, 1)

        # Root container
        self.root_box = Box(
            orientation="v", children=[self.main_box, self.hover_activator]
        )
        self.add(self.root_box)

        # Setup auto-hide controller
        self.auto_hide = AutoHideBarController(self)

        # Connect event handlers for hover
        self.eventbox.connect("enter-notify-event", self.auto_hide.on_bar_enter)
        self.eventbox.connect("leave-notify-event", self.auto_hide.on_bar_leave)
        self.hover_activator.connect(
            "enter-notify-event", self.auto_hide.on_hover_enter
        )

        self.show_all()
