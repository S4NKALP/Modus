from fabric.bluetooth import BluetoothClient
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.utils import get_relative_path
from fabric.widgets.svg import Svg

import utils.icons as icons
from services.network import NetworkClient
from gi.repository import GLib
from services.battery import Battery as BatteryService


class WifiIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.network = NetworkClient()
        self.wifi_icon = Svg(
            name="indicators-icon",
            size=24,
            svg_file=get_relative_path("../../../config/assets/icons/wifi.svg"),
        )

        self.add(self.wifi_icon)

        self.network.connect("ready", self.on_network_ready)

        if self.network.is_ready:
            self.setup_signals()

    def on_network_ready(self, *args):
        self.setup_signals()

    def setup_signals(self):
        self.network.connect("changed", self.on_network_changed)
        self.network.connect("wifi-device-added", self.on_wifi_device_added)
        self.network.connect("wifi-device-removed", self.on_wifi_device_removed)
        self.network.connect("ethernet-device-added", self.on_ethernet_device_added)
        self.network.connect("ethernet-device-removed", self.on_ethernet_device_removed)

        if self.network.wifi_device:
            self.network.wifi_device.connect("changed", self.on_wifi_changed)
            self.network.wifi_device.connect("ap-added", self.on_wifi_changed)
            self.network.wifi_device.connect("ap-removed", self.on_wifi_changed)

        if self.network.ethernet_device:
            self.network.ethernet_device.connect("changed", self.on_ethernet_changed)

        self.update_state()

    def update_state(self):
        if (
            self.network.ethernet_device
            and self.network.ethernet_device.state == "activated"
        ):
            self.wifi_icon.set_from_file(get_relative_path("../../../config/assets/icons/wifi.svg"))
            tooltip = f"Connected to Ethernet ({self.network.ethernet_device.speed})"
            self.set_tooltip_text(tooltip)
            return

        if not self.network.wifi_device:
            self.wifi_icon.set_from_file(get_relative_path("../../../config/assets/icons/wifi-off.svg"))
            tooltip = "No WiFi device found"
        elif not self.network.wifi_device.wireless_enabled:
            self.wifi_icon.set_from_file(get_relative_path("../../../config/assets/icons/wifi-off.svg"))
            tooltip = "WiFi disabled"
        else:
            active_ap = self.network.wifi_device.active_access_point
            if active_ap:
                strength = active_ap.strength
                # Use wifi.svg for all connected states since we don't have signal strength icons
                self.wifi_icon.set_from_file(get_relative_path("../../../config/assets/icons/wifi.svg"))
                tooltip = f"Connected to {active_ap.ssid} ({strength}%)"
            else:
                self.wifi_icon.set_from_file(get_relative_path("../../../config/assets/icons/wifi-off.svg"))
                tooltip = "Not connected"

        self.set_tooltip_text(tooltip)

    def on_wifi_device_added(self, *args):
        self.network.wifi_device.connect("changed", self.on_wifi_changed)
        self.network.wifi_device.connect("ap-added", self.on_wifi_changed)
        self.network.wifi_device.connect("ap-removed", self.on_wifi_changed)
        self.update_state()

    def on_wifi_device_removed(self, *args):
        self.update_state()

    def on_network_changed(self, *args):
        self.update_state()

    def on_wifi_changed(self, *args):
        self.update_state()

    def on_ethernet_device_added(self, *args):
        if self.network.ethernet_device:
            self.network.ethernet_device.connect("changed", self.on_ethernet_changed)
        self.update_state()

    def on_ethernet_device_removed(self, *args):
        self.update_state()

    def on_ethernet_changed(self, *args):
        self.update_state()


class BluetoothIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.bluetooth = BluetoothClient()

        # Use SVG icons instead of font icons
        self.bt_icon = Svg(
            name="bt-icon",
            size=20,
            svg_file=get_relative_path("../../../config/assets/icons/bluetooth.svg"),
        )
        self.add(self.bt_icon)

        self.bluetooth.connect("changed", self.on_bluetooth_changed)
        self.bluetooth.connect("device-added", self.on_device_added)
        self.bluetooth.connect("device-removed", self.on_device_removed)

        self.update_state()

    def update_state(self):
        if not self.bluetooth.enabled:
            self.bt_icon.set_from_file(get_relative_path("../../../config/assets/icons/bluetooth-off.svg"))
            tooltip = "Bluetooth disabled"
        else:
            connected_devices = self.bluetooth.connected_devices
            if connected_devices:
                self.bt_icon.set_from_file(get_relative_path("../../../config/assets/icons/bluetooth.svg"))
                if len(connected_devices) == 1:
                    device = connected_devices[0]
                    tooltip = f"Connected to {device.alias}"
                    if device.battery_percentage > 0:
                        tooltip += f" ({device.battery_percentage:.0f}%)"
                else:
                    tooltip = f"Connected to {len(connected_devices)} devices"
            else:
                self.bt_icon.set_from_file(get_relative_path("../../../config/assets/icons/bluetooth.svg"))
                tooltip = "No devices connected"

        self.set_tooltip_text(tooltip)

    def on_bluetooth_changed(self, *args):
        self.update_state()

    def on_device_added(self, _, address):
        self.update_state()

    def on_device_removed(self, _, address):
        self.update_state()

class Battery(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v", visible=True, **kwargs
        )

        self._battery = BatteryService()
        self._battery.changed.connect(self.update_battery)

        self.icon = Svg(
            name="indicators-icon",
            size=24,
            svg_file=get_relative_path("../../../config/assets/icons/battery/battery-100.svg"),
        )
        self.battery_button = Button(
            child=self.icon,
        )

        self.battery_box = Box(
            name="battery-box",
            orientation="h",
            children=[self.battery_button],
        )

        self.battery_button.set_has_tooltip(True)
        self.battery_box.set_has_tooltip(True)

        self.battery_button.connect("query-tooltip", self.on_query_tooltip)
        self.battery_box.connect("query-tooltip", self.on_query_tooltip)

        self.add(self.battery_box)

        GLib.idle_add(self.update_battery)

    def on_query_tooltip(self, *_):
        tooltip = _[-1]
        tooltip.set_markup(self.get_tooltip_text())
        return True

    def get_tooltip_text(self):
        if not self._battery.is_present:
            return "No battery detected"

        percentage = self._battery.percentage
        state = self._battery.state

        capacity = int(float(self._battery.capacity.rstrip("%")))
        tooltip_points = []

        if state == "FULLY_CHARGED":
            status = f"{icons.battery_full} Fully Charged"
        elif state == "CHARGING":
            status = f"{icons.bat_charging} Charging"
        elif percentage <= 15 and state == "DISCHARGING":
            status = f"{icons.bat_alert} Low Battery"
        elif state == "DISCHARGING":
            status = f"{icons.battery_0} Discharging"
        else:
            status = "Battery"
        tooltip_points.append(f"• Status: {status}")

        tooltip_points.append(f"• Level: {int(percentage)}%")
        tooltip_points.append(f"• Battery Health: {capacity}%")

        power_profile = self._battery.power_profile
        if power_profile:
            if power_profile == "power-saver":
                profile_icon = icons.power_saving
            elif power_profile == "performance":
                profile_icon = icons.power_performance
            else:
                profile_icon = icons.power_balanced
            tooltip_points.append(f"• Profile: {profile_icon} {power_profile}")

        temp = self._battery.temperature
        if temp != "N/A":
            tooltip_points.append(f"• Temperature: {temp}")

        if state == "CHARGING":
            time_to_full = self._battery.time_to_full
            if time_to_full:
                tooltip_points.append(f"• Time until full: {time_to_full}")
        elif state == "DISCHARGING":
            time_to_empty = self._battery.time_to_empty
            if time_to_empty:
                tooltip_points.append(f"• Time remaining: {time_to_empty}")

        return "\n".join(tooltip_points)

    def update_battery(self, *_):
        if not self._battery.is_present:
            self.set_visible(False)
            return True

        percentage = self._battery.percentage
        state = self._battery.state
        charging = state in ["CHARGING", "FULLY_CHARGED"]

        if percentage <= 15 and not charging:
            self.icon.add_style_class("alert")
        else:
            self.icon.remove_style_class("alert")

        if state == "FULLY_CHARGED" or (percentage >= 100 and state == "CHARGING"):
            self.icon.set_from_file(get_relative_path("../../../config/assets/icons/battery/battery-100-charging.svg"))
        elif state == "CHARGING":
            # Calculate battery level and use corresponding charging icon
            level = min(100, max(0, int(percentage // 10) * 10))
            if level == 0 and percentage > 0:
                level = 10
            icon_name = f"battery-{level:03d}-charging.svg"
            self.icon.set_from_file(get_relative_path(f"../../../config/assets/icons/battery/{icon_name}"))
        else:
            # Calculate battery level and use corresponding icon
            level = min(100, max(0, int(percentage // 10) * 10))
            if level == 0 and percentage > 0:
                level = 10
            icon_name = f"battery-{level:03d}.svg"
            self.icon.set_from_file(get_relative_path(f"../../../config/assets/icons/battery/{icon_name}"))

        self.set_visible(True)
        return True


class Indicators(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="indicators",
            orientation="h",
            spacing=10,
            children=[
                Battery(),
                WifiIndicator(),
                BluetoothIndicator(),
            ],
            **kwargs,
        )
        self.show_all()
