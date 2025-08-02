from fabric.system_tray.widgets import SystemTray
from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.revealer import Revealer
from fabric.widgets.svg import Svg
from modules.controlcenter.main import ModusControlCenter
from modules.notification.notification_center import NotificationCenter
from modules.panel.components.enhanced_system_tray import apply_enhanced_system_tray
from modules.panel.components.indicators import (
    BatteryIndicator,
    BluetoothIndicator,
    NetworkIndicator,
)
from modules.panel.components.menubar import MenuBar
from modules.panel.components.recording_indicator import RecordingIndicator
from utils.roam import modus_service
from widgets.mousecapture import MouseCapture
from widgets.wayland import WaylandWindow as Window

# Apply enhanced system tray icon handling
apply_enhanced_system_tray()


class Panel(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="bar",
            title="modus",
            layer="top",
            anchor="left top right",
            exclusivity="auto",
            visible=False,
        )

        self.launcher = kwargs.get("launcher", None)
        self.menubar = MenuBar(parent_window=self)

        self.imac = Button(
            name="panel-button",
            child=Svg(
                size=23,
                svg_file=get_relative_path("../../config/assets/icons/misc/logo.svg"),
            ),
            on_clicked=lambda *_: self.menubar.show_system_dropdown(self.imac),
        )

        # DND indicator
        self.dnd_icon = Svg(
            size=34,
            svg_file=get_relative_path(
                "../../config/assets/icons/applets/dnd-clear.svg"
            ),
        )

        self.dnd_indicator = Button(
            name="dnd-indicator",
            child=self.dnd_icon,
            style="opacity: 0.2;",
            visible=True,
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
                size=16,
                svg_file=get_relative_path(
                    "../../config/assets/icons/misc/chevron-right.svg"
                ),
            ),
            on_clicked=self.toggle_tray,
        )

        self.indicators = Box(
            name="indicators",
            orientation="h",
            spacing=4,
            children=[
                BatteryIndicator(),
                NetworkIndicator(),
                BluetoothIndicator(),
            ],
        )

        self.search = Button(
            name="panel-button",
            on_clicked=lambda *_: self.search_apps(),
            child=Svg(
                size=22,
                svg_file=get_relative_path("../../config/assets/icons/misc/search.svg"),
            ),
        )

        self.control_center = MouseCapture(
            layer="top", child_window=ModusControlCenter()
        )

        self.control_center_button = Button(
            name="control-center-button",
            style_classes="button",
            on_clicked=self.control_center.toggle_mousecapture,
            child=Svg(
                size=22,
                svg_file=get_relative_path(
                    "../../config/assets/icons/misc/control-center.svg"
                ),
            ),
        )

        # Notification Center with MouseCapture
        self.notification_center = MouseCapture(
            layer="overlay", child_window=NotificationCenter()
        )

        # Clickable DateTime for notification center
        self.datetime_button = Button(
            name="datetime-button",
            on_clicked=self.notification_center.toggle_mousecapture,
            child=DateTime(name="date-time", formatters=["%a %b %d %I:%M %P"]),
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
            center_children=Box(
                name="modules-center",
                children=self.recording_indicator,
            ),
            end_children=Box(
                name="modules-right",
                spacing=4,
                orientation="h",
                children=[
                    self.dnd_indicator,
                    self.tray_revealer,
                    self.chevron_button,
                    self.indicators,
                    self.search,
                    self.control_center_button,
                    self.datetime_button,
                ],
            ),
        )

        # Connect to DND state changes
        modus_service.connect("dont-disturb-changed", self.on_dnd_changed)
        # Set initial DND state
        self.update_dnd_indicator(modus_service.dont_disturb)

        return self.show_all()

    def search_apps(self):
        self.launcher.show_launcher()

    def toggle_tray(self, *_):
        current_state = self.tray_revealer.child_revealed
        self.tray_revealer.child_revealed = not current_state

        if self.tray_revealer.child_revealed:
            self.chevron_button.get_child().set_from_file(
                get_relative_path("../../config/assets/icons/misc/chevron-left.svg")
            )
        else:
            self.chevron_button.get_child().set_from_file(
                get_relative_path("../../config/assets/icons/misc/chevron-right.svg")
            )

    def on_dnd_changed(self, _, dnd_state):
        """Handle DND state changes from the service."""
        self.update_dnd_indicator(dnd_state)

    def update_dnd_indicator(self, dnd_enabled):
        """Update the DND indicator opacity based on DND state."""
        if dnd_enabled:
            # 100% opacity when DND is enabled
            self.dnd_indicator.set_style("opacity: 1.0;")
        else:
            # 20% opacity when DND is disabled
            self.dnd_indicator.set_style("opacity: 0.2;")
