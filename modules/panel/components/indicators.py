from fabric.bluetooth import BluetoothClient
from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.svg import Svg
from services.network import NetworkService
from services.battery import Battery
from utils.roam import modus_service


class BluetoothIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(name="bluetooth-indicator", orientation="h", **kwargs)

        self.bluetooth = BluetoothClient()
        self.bt_icon = Svg(
            name="bt-icon",
            size=20,
            svg_file=get_relative_path("../../../config/assets/icons/bluetooth.svg"),
        )

        self.bt_button = Button(name="bt-button", child=self.bt_icon)

        self.add(self.bt_button)

        modus_service.connect("bluetooth-changed", self.on_bluetooth_changed)
        self.bluetooth.connect("changed", self.on_bluetooth_direct_changed)
        self.bluetooth.connect("device-added", self.on_device_added)
        self.bluetooth.connect("device-removed", self.on_device_removed)

        self.update_modus_service_bluetooth_state()
        self.update_state()

    def update_state(self):
        if not self.bluetooth.enabled:
            self.bt_icon.set_from_file(
                get_relative_path("../../../config/assets/icons/bluetooth-off.svg")
            )
            tooltip = "Bluetooth disabled"
        else:
            connected_devices = self.bluetooth.connected_devices
            if connected_devices:
                self.bt_icon.set_from_file(
                    get_relative_path("../../../config/assets/icons/bluetooth.svg")
                )
                if len(connected_devices) == 1:
                    device = connected_devices[0]
                    tooltip = f"Connected to {device.alias}"
                    if device.battery_percentage > 0:
                        tooltip += f" ({device.battery_percentage:.0f}%)"
                else:
                    tooltip = f"Connected to {len(connected_devices)} devices"
            else:
                self.bt_icon.set_from_file(
                    get_relative_path("../../../config/assets/icons/bluetooth.svg")
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


class NetworkIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(name="network-indicator", orientation="h", **kwargs)

        self.network_service = NetworkService()

        self.network_icon = Svg(
            name="network-icon",
            size=25,
            svg_file=get_relative_path("../../../config/assets/icons/wifi.svg"),
        )

        self.network_button = Button(name="network-button", child=self.network_icon)

        self.add(self.network_button)
        modus_service.connect("wlan-changed", self.on_wlan_changed)
        self.network_service.connect("device-ready", self.on_device_ready)

        self.update_modus_service_wlan_state()
        self.update_state()

    def on_wlan_changed(self, service, new_wlan_state):
        self.update_state()

    def on_device_ready(self, *args):
        if self.network_service.wifi_device:
            self.network_service.wifi_device.connect(
                "changed", self.on_network_direct_changed
            )

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
        primary_device = self.network_service.primary_device
        wlan_state = "disconnected"

        if primary_device == "wifi" and self.network_service.wifi_device:
            wifi = self.network_service.wifi_device
            if not wifi.enabled:
                wlan_state = "disabled"
            elif wifi.internet == "activated":
                wlan_state = f"connected:{wifi.ssid}"
                if wifi.strength >= 0:
                    wlan_state += f":{wifi.strength}%"
            elif wifi.internet == "activating":
                wlan_state = f"connecting:{wifi.ssid}"
            else:
                wlan_state = "enabled"

        elif primary_device == "wired" and self.network_service.ethernet_device:
            ethernet = self.network_service.ethernet_device
            if ethernet.internet == "activated":
                wlan_state = "ethernet:connected"
                if hasattr(ethernet, "speed") and ethernet.speed > 0:
                    wlan_state += f":{ethernet.speed}Mbps"
            elif ethernet.internet == "activating":
                wlan_state = "ethernet:connecting"
            else:
                wlan_state = "ethernet:disconnected"

        modus_service.wlan = wlan_state

    def update_state(self):
        primary_device = self.network_service.primary_device
        tooltip = "No network connection"
        icon_file = "wifi-off.svg"

        if primary_device == "wifi" and self.network_service.wifi_device:
            wifi = self.network_service.wifi_device
            if not wifi.enabled:
                icon_file = "wifi-off.svg"
                tooltip = "WiFi disabled"
            elif wifi.internet == "activated":
                icon_file = "wifi.svg"
                tooltip = f"Connected to {wifi.ssid}"
                if wifi.strength >= 0:
                    tooltip += f" ({wifi.strength}%)"
            elif wifi.internet == "activating":
                icon_file = "wifi.svg"
                tooltip = f"Connecting to {wifi.ssid}..."
            else:
                icon_file = "wifi-off.svg"
                tooltip = "WiFi disconnected"

        elif primary_device == "wired" and self.network_service.ethernet_device:
            ethernet = self.network_service.ethernet_device
            if ethernet.internet == "activated":
                icon_file = "ethernet.svg"
                tooltip = "Ethernet connected"
                if hasattr(ethernet, "speed") and ethernet.speed > 0:
                    tooltip += f" ({ethernet.speed} Mbps)"
            elif ethernet.internet == "activating":
                icon_file = "wifi.svg"
                tooltip = "Ethernet connecting..."
            else:
                icon_file = "wifi-off.svg"
                tooltip = "Ethernet disconnected"

        self.network_icon.set_from_file(
            get_relative_path(f"../../../config/assets/icons/{icon_file}")
        )
        self.network_button.set_tooltip_text(tooltip)


class BatteryIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(name="battery-indicator", orientation="h", **kwargs)

        self.battery_service = Battery()

        self.battery_icon = Svg(
            name="battery-icon",
            size=25,
            svg_file=get_relative_path("../../../config/assets/icons/battery.svg"),
        )

        self.battery_button = Button(name="battery-button", child=self.battery_icon)

        self.add(self.battery_button)
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

    def get_battery_icon_level(self, percentage):
        if percentage >= 90:
            return "100"
        elif percentage >= 80:
            return "090"
        elif percentage >= 70:
            return "080"
        elif percentage >= 60:
            return "070"
        elif percentage >= 50:
            return "060"
        elif percentage >= 40:
            return "050"
        elif percentage >= 30:
            return "040"
        elif percentage >= 20:
            return "030"
        elif percentage >= 10:
            return "020"
        else:
            return "010"

    def get_battery_icon_file(self, percentage, is_charging):
        level = self.get_battery_icon_level(percentage)
        suffix = "-charging" if is_charging else ""
        return f"battery/battery-{level}{suffix}.svg"

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
        else:
            percentage = self.battery_service.percentage
            state = self.battery_service.state
            is_charging = state in ["CHARGING", "FULLY_CHARGED"]

            icon_file = self.get_battery_icon_file(percentage, is_charging)
            tooltip = self.get_battery_tooltip(percentage, state)

        # Update icon and tooltip
        self.battery_icon.set_from_file(
            get_relative_path(f"../../../config/assets/icons/{icon_file}")
        )
        self.battery_button.set_tooltip_text(tooltip)
