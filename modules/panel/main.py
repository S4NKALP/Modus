from fabric.system_tray.widgets import SystemTray
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window

from modules.controlcenter.main import ModusControlCenter
from modules.notification.notification_center import NotificationCenter
from modules.panel.components.enhanced_system_tray import apply_enhanced_system_tray
from modules.panel.components.globalmenu import GlobalMenu
from modules.panel.components.indicators import (
    BatteryIndicator,
    BluetoothIndicator,
    NetworkIndicator,
)
from modules.panel.components.recording_indicator import RecordingIndicator
from modules.panel.components.workspace import WorkspaceIndicator
from services.config import get_config, on_config_change
from services.modus import notification_service
from utils.roam import modus_service
from utils.utils import setup_cursor_hover, svg_file
from widgets.mousecapture import MouseCapture

apply_enhanced_system_tray()


class Panel(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="bar",
            title="modus",
            layer="top",
            anchor="left top right",
            exclusivity="auto",
            visible=True,
            all_visible=False,
        )
        self.globalmenu = GlobalMenu(parent_window=self)

        self.imac = Button(
            name="panel-button",
            child=svg_file("misc/logo.svg", size=18),
            on_clicked=lambda *_: self.globalmenu.show_system_dropdown((self.imac)),
        )
        setup_cursor_hover(self.imac, "pointer")

        self.tray = SystemTray(name="panel-button", spacing=4, icon_size=20)

        self.tray_revealer = Revealer(
            name="tray-revealer",
            child=self.tray,
            child_revealed=False,
            transition_type="slide-left",
            transition_duration=300,
        )

        self.chevron_button = Button(
            name="panel-button",
            child=svg_file("misc/chevron-right.svg", size=16),
            on_clicked=self.toggle_tray,
        )
        setup_cursor_hover(self.chevron_button, "pointer")

        # Hide tray elements if empty
        self.tray.connect("add", self._update_tray_visibility)
        self.tray.connect("remove", self._update_tray_visibility)

        self.indicators = Box(
            name="indicators",
            orientation="h",
            spacing=4,
        )

        self.search = Button(
            name="panel-button", child=svg_file("misc/search.svg", size=22)
        )
        setup_cursor_hover(self.search, "pointer")

        self.control_center = MouseCapture(
            layer="top", child_window=ModusControlCenter()
        )

        self.control_center_btn = Button(
            name="panel-button",
            child=svg_file("misc/control-center.svg", size=22),
            on_clicked=self.control_center.toggle_mousecapture,
        )
        setup_cursor_hover(self.control_center_btn, "pointer")

        self.notification_center = MouseCapture(
            layer="overlay", child_window=NotificationCenter()
        )

        self.notification_icon = svg_file(
            "notifications/notification-inactive.svg", size=22
        )

        self.notification_center_btn = Button(
            name="panel-button",
            child=self.notification_icon,
            on_clicked=self.on_notification_icon_clicked,
        )
        setup_cursor_hover(self.notification_center_btn, "pointer")

        self.datetime_btn = Button(
            name="panel-button",
            child=DateTime(name="date-time", formatters=["%a %-d %b %I:%M %P"]),
        )
        setup_cursor_hover(self.datetime_btn, "pointer")

        self.workspace_indicator = WorkspaceIndicator()
        self.recording_indicator = RecordingIndicator()

        # Create boxes and mount, to allow live updates
        self.left_box = Box(name="modules-left")
        self.center_box = Box(name="modules-center", children=self.recording_indicator)
        self.right_box = Box(name="modules-right", spacing=4, orientation="h")

        self.children = CenterBox(
            name="panel",
            start_children=self.left_box,
            center_children=self.center_box,
            end_children=self.right_box,
        )

        # Connect to DND state changes for notification icon
        modus_service.connect("dont-disturb-changed", self.on_dnd_changed)

        # Connect to notification service for icon state updates
        notification_service.connect(
            "notify::count", self.on_notification_count_changed
        )

        # Set initial notification icon state
        self.update_notification_icon()

        # Initial layout build
        self._rebuild_layout_from_config()

        # Live updates
        on_config_change(self._on_config_changed)

        self._update_tray_visibility()
        self.show_all()

    def on_dnd_changed(self, _, dnd_state):
        self.update_notification_icon()  # Update notification icon when DND changes

    def on_notification_count_changed(self, service, *args):
        self.update_notification_icon()

    def on_notification_icon_clicked(self, *args):
        count = notification_service.count
        if count > 0:
            # Only open notification center if there are notifications
            self.notification_center.toggle_mousecapture()
        # Do nothing if no notifications

    def update_notification_icon(self):
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

        self.notification_icon.dynamic_file(f"notifications/{icon_file}")

    def _rebuild_layout_from_config(self):
        # Left
        left_children = []
        if get_config("imac_button", True):
            left_children.append(self.imac)
        if get_config("global_menu", True):
            left_children.append(self.globalmenu)
        self.left_box.children = left_children

        # Indicators (create fresh instances on each rebuild)
        indicators_children = []
        if get_config("battery", True):
            indicators_children.append(BatteryIndicator())
        if get_config("network", True):
            indicators_children.append(NetworkIndicator())
        if get_config("bluetooth", True):
            indicators_children.append(BluetoothIndicator())
        self.indicators.children = indicators_children

        # Right
        right_children = []
        if get_config("workspace_indicator", True):
            right_children.append(self.workspace_indicator)

        if get_config("systray", True):
            right_children.extend([self.tray_revealer, self.chevron_button])

        right_children.append(self.indicators)

        if get_config("search", True):
            right_children.append(self.search)
        if get_config("control_center", True):
            right_children.append(self.control_center_btn)
        if get_config("date_time", True):
            right_children.append(self.datetime_btn)
        if get_config("notification_center", True):
            right_children.append(self.notification_center_btn)

        self.right_box.children = right_children
        self._update_tray_visibility()
        self.show_all()

    def _on_config_changed(self, new_config, old_config):
        keys = {
            "imac_button",
            "global_menu",
            "workspace_indicator",
            "systray",
            "battery",
            "network",
            "bluetooth",
            "search",
            "control_center",
            "date_time",
            "notification_center",
        }
        if any(new_config.get(k) != old_config.get(k) for k in keys):
            self._rebuild_layout_from_config()

        # Always update tray visibility on config change just in case
        self._update_tray_visibility()

    def _update_tray_visibility(self, *_):
        # We check if there are any visible children in the tray
        visible_children = [
            child for child in self.tray.get_children() if child.get_visible()
        ]
        has_items = len(visible_children) > 0

        self.tray_revealer.set_visible(has_items)
        self.chevron_button.set_visible(has_items)

        if not has_items:
            # Reset state if it becomes hidden
            self.tray_revealer.child_revealed = False
            self.chevron_button.get_child().dynamic_file("misc/chevron-right.svg")
            # Add extra spacing between workspace indicator and indicators when tray is hidden
            self.indicators.set_margin_left(10)
        else:
            self.indicators.set_margin_left(0)

    def toggle_tray(self, *_):
        current_state = self.tray_revealer.child_revealed
        self.tray_revealer.child_revealed = not current_state

        if self.tray_revealer.child_revealed:
            self.chevron_button.get_child().dynamic_file("misc/chevron-left.svg")
        else:
            self.chevron_button.get_child().dynamic_file("misc/chevron-right.svg")
