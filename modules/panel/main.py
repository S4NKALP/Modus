from fabric.system_tray.widgets import SystemTray
from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.svg import Svg
from utils.wayland import WaylandWindow as Window

from modules.panel.components.enhanced_system_tray import apply_enhanced_system_tray
from modules.panel.components.indicators import Indicators
from modules.panel.components.menubar import MenuBar
from modules.panel.components.recording_indicator import RecordingIndicator

# Apply enhanced system tray icon handling
apply_enhanced_system_tray()


class Panel(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="bar",
            layer="top",
            anchor="left top right",
            exclusivity="auto",
            visible=False,
        )

        self.launcher = kwargs.get("launcher", None)
        self.menubar = MenuBar()

        self.imac = Button(
            name="panel-button",
            child=Svg(
                size=24,
                svg_file=get_relative_path("../../config/assets/icons/logo.svg"),
            ),
            on_clicked=lambda *_: self.menubar.show_system_dropdown(self.imac),
        )
        self.notch_spot = Box(
            name="notch-spot",
            size=(200, 24),
            h_expand=True,
            v_expand=True,
            children=Label(label="notch"),
        )

        self.tray = SystemTray(name="system-tray", spacing=4, icon_size=20)

        self.tray_revealer = Revealer(
            name="tray-revealer",
            child=self.tray,
            child_revealed=False,
            transition_type="slide-left",
            transition_duration=300,
        )

        self.chevron_button = Button(
            name="panel-button",
            child=Svg(
                size=18,
                svg_file=get_relative_path(
                    "../../config/assets/icons/chevron-right.svg"
                ),
            ),
            on_clicked=self.toggle_tray,
        )

        self.indicators = Indicators()

        self.search = Button(
            name="panel-button",
            on_clicked=lambda *_: self.search_apps(),
            child=Svg(
                size=20,
                svg_file=get_relative_path("../../config/assets/icons/search.svg"),
            ),
        )

        self.controlcenter = Button(
            name="panel-button",
            child=Svg(
                size=24,
                svg_file=get_relative_path(
                    "../../config/assets/icons/control-center.svg"
                ),
            ),
        )
        self.recording_indicator = RecordingIndicator()

        self.children = CenterBox(
            name="panel",
            start_children=Box(
                name="modules-left",
                children=[
                    self.imac,
                    self.menubar,
                ],
            ),
            # center_children=Box(
            #     name="modules-center",
            #     children=self.notch_spot,
            # ),
            end_children=Box(
                name="modules-right",
                spacing=4,
                orientation="h",
                children=[
                    self.recording_indicator,
                    self.tray_revealer,
                    self.chevron_button,
                    self.indicators,
                    self.search,
                    self.controlcenter,
                    DateTime(name="date-time", formatters=["%a %b %d %I:%M"]),
                ],
            ),
        )

        return self.show_all()

    def search_apps(self):
        self.launcher.show_launcher()

    def toggle_tray(self, *_):
        current_state = self.tray_revealer.child_revealed
        self.tray_revealer.child_revealed = not current_state

        if self.tray_revealer.child_revealed:
            self.chevron_button.get_child().set_from_file(
                get_relative_path("../../config/assets/icons/chevron-left.svg")
            )
        else:
            self.chevron_button.get_child().set_from_file(
                get_relative_path("../../config/assets/icons/chevron-right.svg")
            )
