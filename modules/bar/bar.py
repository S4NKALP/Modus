from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.label import Label
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
import utils.icons as icons


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

        # Tray setup
        self._setup_tray()

        self.power_menu = Power()
        self.system_indicators = SystemIndicators()
        self.metrics = Metrics()

        # Main bar content

        self.bar = CenterBox(
            name="bar",
            # start_children=Box(spacing=4, orientation="h", children=self.workspaces),
            center_children=Box(
                spacing=4,
                orientation="h",
                children=[
                    self.workspaces,
                    self.active_window,
                    self.date_time,
                    self.metrics,
                    self.system_indicators,
                    self.tray_button,
                    self.tray_revealer,
                    self.power_menu,
                ],
            ),
            # end_children=Box(
            #     spacing=4,
            #     orientation="h",
            #     children=[
            #         self.date_time,
            #         self.tray_button,
            #         self.tray_revealer,
            #         self.power_menu,
            #     ],
            # ),
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

    def _setup_tray(self):
        """Setup the system tray with reveal functionality."""
        self.tray = SystemTray(name="tray", spacing=4, icon_size=16)
        self.tray_revealer = Revealer(
            name="tray-revealer",
            transition_type="slide-left",
            transition_duration=200,
            child=self.tray,
            reveal_child=False,
        )
        self.tray_label = Label(markup=icons.chevron_left)
        self.tray_button = EventBox(name="tray-button", child=self.tray_label)
        self.tray_button.connect("button-press-event", self._toggle_tray)

    def _toggle_tray(self, *args):
        """Toggle the tray visibility and update the icon."""
        is_revealed = not self.tray_revealer.get_reveal_child()
        self.tray_revealer.set_reveal_child(is_revealed)
        self.tray_label.set_markup(
            icons.chevron_right if is_revealed else icons.chevron_left
        )
