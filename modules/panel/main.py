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
from modules.panel.components.workspace import WorkspaceIndicator
from utils.roam import modus_service
from widgets.mousecapture import MouseCapture
from widgets.wayland import WaylandWindow as Window
from services.modus import notification_service

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
                size=16,
                svg_file=get_relative_path("../../config/assets/icons/misc/logo.svg"),
            ),
            on_clicked=lambda *_: self.menubar.show_system_dropdown(self.imac),
        )

        # DND indicator - REMOVED

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

        # Notification Center Icon
        self.notification_icon = Svg(
            size=22,
            svg_file=get_relative_path(
                "../../config/assets/icons/notifications/notification-inactive.svg"
            ),
        )

        self.notification_center_icon_button = Button(
            name="notification-center-icon-button",
            child=self.notification_icon,
            on_clicked=self.on_notification_icon_clicked,
        )

        # Clickable DateTime for notification center
        self.datetime_button = Button(
            name="datetime-button",
            on_clicked=self.notification_center.toggle_mousecapture,
            child=DateTime(name="date-time", formatters=["%a %-d %b %I:%M %P"]),
        )

        self.recording_indicator = RecordingIndicator()

        # Workspace indicator
        self.workspace_indicator = WorkspaceIndicator()

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
                    self.workspace_indicator,
                    self.tray_revealer,
                    self.chevron_button,
                    self.indicators,
                    self.search,
                    self.control_center_button,
                    self.datetime_button,
                    self.notification_center_icon_button,
                ],
            ),
        )

        # Connect to DND state changes for notification icon
        modus_service.connect("dont-disturb-changed", self.on_dnd_changed)

        # Connect to notification service for icon state updates
        notification_service.connect("notify::count", self.on_notification_count_changed)
        
        # Set initial notification icon state
        self.update_notification_icon()

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
        self.update_notification_icon()  # Update notification icon when DND changes

    def on_notification_count_changed(self, service, *args):
        """Handle notification count changes from the service."""
        self.update_notification_icon()

    def on_notification_icon_clicked(self, *args):
        """Handle notification icon clicks - only open center if there are notifications."""
        count = notification_service.count
        if count > 0:
            # Only open notification center if there are notifications
            self.notification_center.toggle_mousecapture()
        # Do nothing if no notifications

    def update_notification_icon(self):
        """Update the notification icon based on count and DND state."""
        count = notification_service.count
        dnd_enabled = modus_service.dont_disturb
        
        if dnd_enabled:
            # DND is enabled - show disabled icon
            icon_file = "notification-disabled.svg"
        elif count > 0:
            # Has notifications - show active icon
            icon_file = "notification-active.svg"
        else:
            # No notifications - show inactive icon
            icon_file = "notification-inactive.svg"
        
        icon_path = get_relative_path(f"../../config/assets/icons/notifications/{icon_file}")
        self.notification_icon.set_from_file(icon_path)
