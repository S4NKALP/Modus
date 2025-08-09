from fabric.bluetooth import BluetoothClient
from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.svg import Svg

from modules.controlcenter.battery import BatteryControl
from modules.controlcenter.bluetooth import BluetoothConnections
from modules.controlcenter.wifi import WifiConnections
from services.battery import Battery
from services.network import NetworkClient
from utils.roam import modus_service
from widgets.mousecapture import DropDownMouseCapture
from widgets.wayland import WaylandWindow as Window


class BluetoothIndicator(Box):
    def __init__(self, show_window=True, **kwargs):
        super().__init__(name="bluetooth-indicator", orientation="h", **kwargs)
        self.show_window = show_window

        self.bluetooth = BluetoothClient()
        self.bt_icon = Svg(
            name="bt-icon",
            size=18,
            svg_file=get_relative_path(
                "../../../config/assets/icons/applets/bluetooth-clear.svg"
            ),
        )

        self.bt_button = Button(
            name="bt-button", child=self.bt_icon, on_clicked=self.on_bluetooth_clicked
        )

        self.add(self.bt_button)

        # Create Bluetooth control center widget only if show_window is True
        if self.show_window:
            self.bluetooth_window = Window(
                layer="overlay",
                title="modus",
                anchor="top right",
                margin="2px 10px 0px 0px",
                exclusivity="auto",
                keyboard_mode="on-demand",
                name="bluetooth-control-window",
                visible=False,
            )

            self.bluetooth_widget = BluetoothConnections(self, show_back_button=False)
            self.bluetooth_window.children = [self.bluetooth_widget]

            # Create mouse capture for Bluetooth widget
            self.bluetooth_mousecapture = DropDownMouseCapture(
                layer="top", child_window=self.bluetooth_window
            )
        else:
            self.bluetooth_window = None
            self.bluetooth_widget = None
            self.bluetooth_mousecapture = None

        modus_service.connect("bluetooth-changed", self.on_bluetooth_changed)
        self.bluetooth.connect("changed", self.on_bluetooth_direct_changed)
        self.bluetooth.connect("device-added", self.on_device_added)
        self.bluetooth.connect("device-removed", self.on_device_removed)

        self.update_modus_service_bluetooth_state()
        self.update_state()

    def update_state(self):
        if not self.bluetooth.enabled:
            self.bt_icon.set_from_file(
                get_relative_path(
                    "../../../config/assets/icons/applets/bluetooth-off-clear.svg"
                )
            )
            tooltip = "Bluetooth disabled"
        else:
            connected_devices = self.bluetooth.connected_devices
            if connected_devices:
                self.bt_icon.set_from_file(
                    get_relative_path(
                        "../../../config/assets/icons/applets/bluetooth-clear.svg"
                    )
                )
                if len(connected_devices) >= 1:
                    self.bt_icon.set_from_file(
                        get_relative_path(
                            "../../../config/assets/icons/applets/bluetooth-paired.svg"
                        )
                    )
                    device = connected_devices[0]
                    tooltip = f"Connected to {device.alias}"
                    if device.battery_percentage > 0:
                        tooltip += f" ({device.battery_percentage:.0f}%)"
                else:
                    tooltip = f"Connected to {len(connected_devices)} devices"
            else:
                self.bt_icon.set_from_file(
                    get_relative_path(
                        "../../../config/assets/icons/applets/bluetooth-clear.svg"
                    )
                )
                tooltip = "No devices connected"

        self.bt_button.set_tooltip_text(tooltip)

    def on_bluetooth_changed(self, service, new_bluetooth_state):
        self.update_state()

    def on_bluetooth_direct_changed(self, *args):
        self.update_modus_service_bluetooth_state()
        self.update_state()

    def on_device_added(self, _, address):
        self.update_modus_service_bluetooth_state()
        self.update_state()

    def on_device_removed(self, _, address):
        self.update_modus_service_bluetooth_state()
        self.update_state()

    def update_modus_service_bluetooth_state(self):
        if not self.bluetooth.enabled:
            bluetooth_state = "disabled"
        else:
            connected_devices = self.bluetooth.connected_devices
            if connected_devices:
                if len(connected_devices) == 1:
                    device = connected_devices[0]
                    bluetooth_state = f"connected:{device.alias}"
                    if (
                        hasattr(device, "battery_percentage")
                        and device.battery_percentage > 0
                    ):
                        bluetooth_state += f":{device.battery_percentage:.0f}%"
                else:
                    bluetooth_state = f"connected:{len(connected_devices)}_devices"
            else:
                bluetooth_state = "enabled"

        modus_service.bluetooth = bluetooth_state

    def on_bluetooth_clicked(self, *args):
        """Handle Bluetooth indicator click"""
        if self.show_window and self.bluetooth_mousecapture:
            self.bluetooth_mousecapture.toggle_mousecapture()

    def close_bluetooth(self, *args):
        """Close Bluetooth control center"""
        if self.show_window and self.bluetooth_mousecapture:
            self.bluetooth_mousecapture.hide_child_window()

    def hide_controlcenter(self, *args):
        """Hide Bluetooth control center"""
        if self.show_window and self.bluetooth_mousecapture:
            self.bluetooth_mousecapture.hide_child_window()


class NetworkIndicator(Box):
    def __init__(self, show_window=True, **kwargs):
        super().__init__(name="network-indicator", orientation="h", **kwargs)
        self.show_window = show_window

        self.network_service = NetworkClient()

        self.network_icon = Svg(
            name="network-icon",
            size=18,
            svg_file=get_relative_path(
                "../../../config/assets/icons/applets/wifi-clear.svg"
            ),
        )

        self.network_button = Button(
            name="network-button",
            child=self.network_icon,
            on_clicked=self.on_wifi_clicked,
        )

        self.add(self.network_button)

        # Create WiFi control center widget only if show_window is True
        if self.show_window:
            self.wifi_window = Window(
                layer="overlay",
                title="modus",
                anchor="top right",
                margin="2px 10px 0px 0px",
                exclusivity="auto",
                keyboard_mode="on-demand",
                name="wifi-control-window",
                visible=False,
            )

            self.wifi_widget = WifiConnections(self, show_back_button=False)
            self.wifi_window.children = [self.wifi_widget]

            # Create mouse capture for WiFi widget
            self.wifi_mousecapture = DropDownMouseCapture(
                layer="top", child_window=self.wifi_window
            )
        else:
            self.wifi_window = None
            self.wifi_widget = None
            self.wifi_mousecapture = None

        modus_service.connect("wlan-changed", self.on_wlan_changed)
        self.network_service.connect("wifi-device-added", self.on_wifi_device_added)
        self.network_service.connect(
            "ethernet-device-added", self.on_ethernet_device_added
        )
        self.network_service.connect("changed", self.on_network_changed)

        self.update_modus_service_wlan_state()
        self.update_state()

    def on_wlan_changed(self, service, new_wlan_state):
        self.update_state()

    def on_wifi_device_added(self, *args):
        """Called when WiFi device is added"""
        if self.network_service.wifi_device:
            self.network_service.wifi_device.connect(
                "changed", self.on_network_direct_changed
            )
        self.update_modus_service_wlan_state()
        self.update_state()

    def on_ethernet_device_added(self, *args):
        """Called when Ethernet device is added"""
        if self.network_service.ethernet_device:
            self.network_service.ethernet_device.connect(
                "changed", self.on_network_direct_changed
            )
        self.update_modus_service_wlan_state()
        self.update_state()

    def on_network_direct_changed(self, *args):
        self.update_modus_service_wlan_state()
        self.update_state()

    def on_network_changed(self, *args):
        self.update_modus_service_wlan_state()
        self.update_state()

    def update_modus_service_wlan_state(self):
        wlan_state = "disconnected"

        # Check WiFi first (prioritize WiFi over Ethernet)
        if self.network_service.wifi_device:
            wifi = self.network_service.wifi_device
            if not wifi.wireless_enabled:
                wlan_state = "disabled"
            elif wifi.active_access_point:
                ap = wifi.active_access_point
                wlan_state = f"connected:{ap.ssid}"
                if ap.strength >= 0:
                    wlan_state += f":{ap.strength}%"
            else:
                wlan_state = "enabled"

        # Check Ethernet if WiFi is not connected
        elif self.network_service.ethernet_device:
            ethernet = self.network_service.ethernet_device
            if ethernet.internet == "activated":
                wlan_state = "ethernet:connected"
                if hasattr(ethernet, "speed") and ethernet.speed:
                    wlan_state += f":{ethernet.speed}"
            elif ethernet.internet == "activating":
                wlan_state = "ethernet:connecting"
            else:
                wlan_state = "ethernet:disconnected"

        modus_service.wlan = wlan_state

    def update_state(self):
        tooltip = "No network connection"
        icon_file = "wifi-off-clear.svg"

        # Check WiFi first (prioritize WiFi over Ethernet)
        if self.network_service.wifi_device:
            wifi = self.network_service.wifi_device
            if not wifi.wireless_enabled:
                icon_file = "wifi-off-clear.svg"
                tooltip = "WiFi disabled"
            elif wifi.active_access_point:
                ap = wifi.active_access_point
                icon_file = "wifi-clear.svg"
                tooltip = f"Connected to {ap.ssid}"
                if ap.strength >= 0:
                    tooltip += f" ({ap.strength}%)"
            else:
                icon_file = "wifi-off-clear.svg"
                tooltip = "WiFi disconnected"

        # Check Ethernet if WiFi is not connected
        elif self.network_service.ethernet_device:
            ethernet = self.network_service.ethernet_device
            if ethernet.internet == "activated":
                icon_file = "network-wired.svg"
                tooltip = "Ethernet connected"
                if hasattr(ethernet, "speed") and ethernet.speed:
                    tooltip += f" ({ethernet.speed})"
            elif ethernet.internet == "activating":
                icon_file = "network-wired.svg"
                tooltip = "Ethernet connecting..."
            else:
                icon_file = "network-wired-offline.svg"
                tooltip = "Ethernet disconnected"

        self.network_icon.set_from_file(
            get_relative_path(f"../../../config/assets/icons/applets/{icon_file}")
        )
        self.network_button.set_tooltip_text(tooltip)

    def on_wifi_clicked(self, *args):
        """Handle WiFi indicator click"""
        if self.show_window and self.wifi_mousecapture:
            self.wifi_mousecapture.toggle_mousecapture()

    def close_wifi(self, *args):
        """Close WiFi control center"""
        if self.show_window and self.wifi_mousecapture:
            self.wifi_mousecapture.hide_child_window()

    def hide_controlcenter(self, *args):
        """Hide WiFi control center"""
        if self.show_window and self.wifi_mousecapture:
            self.wifi_mousecapture.hide_child_window()


class BatteryIndicator(Box):
    def __init__(self, show_window=True, **kwargs):
        super().__init__(name="battery-indicator", orientation="h", **kwargs)
        self.show_window = show_window

        self.battery_service = Battery()

        self.battery_icon = Svg(
            name="battery-icon",
            size=23,
            svg_file=get_relative_path(
                "../../../config/assets/icons/battery/battery-100.svg"
            ),
        )

        self.battery_button = Button(
            name="battery-button",
            child=self.battery_icon,
            on_clicked=self.on_battery_clicked,
        )

        self.battery_label = Label(name="battery-label", label="--- %")

        self.add(self.battery_label)
        self.add(self.battery_button)

        # Create Battery control center widget only if show_window is True
        if self.show_window:
            self.battery_window = Window(
                layer="overlay",
                title="modus",
                anchor="top right",
                margin="2px 200px 0px 0px",
                exclusivity="auto",
                keyboard_mode="on-demand",
                name="battery-control-window",
                visible=False,
            )

            self.battery_widget = BatteryControl(self, show_back_button=False)
            self.battery_window.children = [self.battery_widget]

            # Create mouse capture for Battery widget
            self.battery_mousecapture = DropDownMouseCapture(
                layer="top", child_window=self.battery_window
            )
        else:
            self.battery_window = None
            self.battery_widget = None
            self.battery_mousecapture = None

        modus_service.connect("battery-changed", self.on_battery_changed)
        self.battery_service.connect("changed", self.on_battery_direct_changed)

        self.update_modus_service_battery_state()
        self.update_state()

    def on_battery_changed(self, service, new_battery_state):
        self.update_state()

    def on_battery_direct_changed(self, *args):
        self.update_modus_service_battery_state()
        self.update_state()

    def update_modus_service_battery_state(self):
        if not self.battery_service.is_present:
            battery_state = "not_present"
        else:
            percentage = self.battery_service.percentage
            state = self.battery_service.state.lower()

            battery_state = f"{state}:{percentage}%"

            if state == "discharging":
                time_to_empty = self.battery_service.time_to_empty
                if time_to_empty != "N/A":
                    battery_state += f":{time_to_empty}"
            elif state == "charging":
                time_to_full = self.battery_service.time_to_full
                if time_to_full != "N/A":
                    battery_state += f":{time_to_full}"

        modus_service.battery = battery_state

    def get_battery_tooltip(self, percentage, state):
        tooltip = f"Battery: {percentage}%"

        if state == "CHARGING":
            tooltip += " (Charging)"
            time_to_full = self.battery_service.time_to_full
            if time_to_full != "N/A":
                tooltip += f" - {time_to_full} until full"
        elif state == "DISCHARGING":
            time_to_empty = self.battery_service.time_to_empty
            if time_to_empty != "N/A":
                tooltip += f" - {time_to_empty} remaining"
        elif state == "FULLY_CHARGED":
            tooltip += " (Fully charged)"

        return tooltip

    def update_state(self):
        if not self.battery_service.is_present:
            icon_file = "battery.svg"
            tooltip = "No battery detected"
            percentage_text = "N/A"
        else:
            percentage = self.battery_service.percentage
            state = self.battery_service.state
            is_charging = state in ["CHARGING", "FULLY_CHARGED"]

            icon_file = Battery.get_battery_icon_file(
                percentage, is_charging, base_path="../../../config/assets/icons/"
            )
            tooltip = self.get_battery_tooltip(percentage, state)
            percentage_text = f"{percentage}%"

        # Update icon, tooltip, and percentage label
        self.battery_icon.set_from_file(get_relative_path(icon_file))
        self.battery_button.set_tooltip_text(tooltip)
        self.battery_label.set_label(percentage_text)

    def on_battery_clicked(self, *args):
        """Handle Battery indicator click"""
        if self.show_window and self.battery_mousecapture:
            self.battery_mousecapture.toggle_mousecapture()

    def close_battery(self, *args):
        """Close Battery control center"""
        if self.show_window and self.battery_mousecapture:
            self.battery_mousecapture.hide_child_window()

    def hide_controlcenter(self, *args):
        """Hide Battery control center"""
        if self.show_window and self.battery_mousecapture:
            self.battery_mousecapture.hide_child_window()
