from fabric.system_tray.widgets import SystemTray
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window

from services.config import on_config_change, get_config_all
from services.modus import notification_service

from utils.roam import modus_service
from utils.utils import setup_cursor_hover, svg_file
from window.controlcenter.main import ModusControlCenter
from window.notification.notification_center import NotificationCenter
from window.panel.components.enhanced_system_tray import apply_enhanced_system_tray
from window.panel.components.globalmenu import GlobalMenu
from window.panel.components.indicators import (
    BatteryIndicator,
    BluetoothIndicator,
    NetworkIndicator,
)
from window.panel.components.recording_indicator import RecordingIndicator
from window.panel.components.workspace import WorkspaceIndicator

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

        self.control_center_btn = Button(
            name="panel-button",
            child=svg_file("misc/control-center.svg", size=22),
        )
        setup_cursor_hover(self.control_center_btn, "pointer")

        self.control_center = ModusControlCenter(
            parent=self, pointing_to=self.control_center_btn
        )
        self.control_center_btn.connect(
            "clicked",
            lambda *_: self.control_center.toggle(),
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

        self.notification_center = NotificationCenter(
            parent=self, pointing_to=self.notification_center_btn
        )

        self.datetime_btn = Button(
            name="panel-button",
            child=DateTime(name="date-time", formatters=["%a %-d %b %I:%M %P"]),
        )
        setup_cursor_hover(self.datetime_btn, "pointer")

        self.workspace_indicator = WorkspaceIndicator()
        self.recording_indicator = RecordingIndicator()

        # Create persistent indicators
        self.battery_indicator = BatteryIndicator()
        self.network_indicator = NetworkIndicator()
        self.bluetooth_indicator = BluetoothIndicator()

        self.indicators = Box(
            name="indicators",
            orientation="h",
            spacing=4,
            children=[
                self.battery_indicator,
                self.network_indicator,
                self.bluetooth_indicator,
            ],
        )

        # Create boxes and mount
        self.left_box = Box(name="window-left")
        self.center_box = Box(name="window-center", children=self.recording_indicator)
        self.right_box = Box(name="window-right", spacing=4, orientation="h")

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
        self._rebuild_layout_from_config(get_config_all())

        # Live updates
        on_config_change(self._on_config_changed)

        self._update_tray_visibility()
        self.show()

    def on_dnd_changed(self, _, dnd_state):
        self.update_notification_icon()  # Update notification icon when DND changes

    def on_notification_count_changed(self, service, *args):
        self.update_notification_icon()

    def on_notification_icon_clicked(self, *args):
        count = notification_service.count
        if count > 0:
            self.notification_center.toggle()

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

    def _rebuild_layout_from_config(self, config_data=None):
        if config_data is None:
            config_data = get_config_all()

        # Update indicator visibility directly
        battery_visible = config_data.get("battery", True)
        network_visible = config_data.get("network", True)
        bluetooth_visible = config_data.get("bluetooth", True)

        self.battery_indicator.set_visible(battery_visible)
        self.network_indicator.set_visible(network_visible)
        self.bluetooth_indicator.set_visible(bluetooth_visible)

        # Ensure they update their internal state
        if battery_visible:
            self.battery_indicator.update_state()
        if network_visible:
            self.network_indicator.update_state()
        if bluetooth_visible:
            self.bluetooth_indicator.update_state()

        # Left
        left_children = []
        if config_data.get("imac_button", True):
            left_children.append(self.imac)
        if config_data.get("global_menu", True):
            left_children.append(self.globalmenu)

        for child in left_children:
            child.show()
        self.left_box.children = left_children

        # Right
        right_children = []
        if config_data.get("workspace_indicator", True):
            right_children.append(self.workspace_indicator)

        if config_data.get("systray", True):
            right_children.extend([self.tray_revealer, self.chevron_button])

        right_children.append(self.indicators)

        if config_data.get("search", True):
            right_children.append(self.search)
        if config_data.get("control_center", True):
            right_children.append(self.control_center_btn)
        if config_data.get("date_time", True):
            right_children.append(self.datetime_btn)
        if config_data.get("notification_center", True):
            right_children.append(self.notification_center_btn)

        for child in right_children:
            child.show()
        self.right_box.children = right_children

        self.indicators.show()
        self._update_tray_visibility()
        self.show()

        # Force a layout recalculation
        self.queue_resize()

    def _on_config_changed(self, new_config, old_config):
        print("[Panel] Config changed, checking keys...")
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
        changed_keys = [k for k in keys if new_config.get(k) != old_config.get(k)]
        if changed_keys:
            print(f"[Panel] Rebuilding due to changes in: {changed_keys}")
            self._rebuild_layout_from_config(new_config)

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

    def destroy(self):
        """Clean up all signals and components"""
        try:
            modus_service.disconnect_by_func(self.on_dnd_changed)
            notification_service.disconnect_by_func(self.on_notification_count_changed)
            from services.config import _config_handlers

            if self._on_config_changed in _config_handlers:
                _config_handlers.remove(self._on_config_changed)
        except Exception:
            pass

        # Destroy components
        for component in [
            self.globalmenu,
            self.workspace_indicator,
            self.recording_indicator,
            self.indicators,
        ]:
            try:
                component.destroy()
            except Exception:
                pass

        # Destroy MouseCapture windows
        for mc in [self.control_center, self.notification_center]:
            try:
                mc.destroy()
            except Exception:
                pass

        super().destroy()
