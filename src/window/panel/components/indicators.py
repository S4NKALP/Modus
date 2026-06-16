from fabric.utils import logger
from fabric.bluetooth import BluetoothClient
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from services.battery import Battery
from services.network import NetworkClient
from shared.window.battery_widget import BatteryControl
from shared.window.applet_window import AppletWindow
from utils.functions import format_duration, get_wifi_icon_for_strength
from utils.roam import modus_service
from utils.utils import setup_cursor_hover, svg_file
from window.controlcenter.bluetooth import BluetoothConnections
from window.controlcenter.wifi import WifiConnections


def create_control_window(name_prefix, parent=None, pointing_to=None):
    return AppletWindow(
        parent=parent,
        pointing_to=pointing_to,
        layer="overlay",
        title="modus",
        anchor="top right",
        margin="2px 10px 0px 0px",
        exclusivity="auto",
        name=f"{name_prefix}-window",
        visible=False,
    )


def setup_control_center(
    show_window, name_prefix, widget_class, parent, pointing_to=None, **widget_kwargs
):
    if not show_window:
        return None, None

    window = create_control_window(name_prefix, parent=parent, pointing_to=pointing_to)
    widget = widget_class(parent, **widget_kwargs)
    window.children = [widget]

    return window, widget


def handle_indicator_click(window):
    if window:
        window.toggle()


def hide_control_center(window):
    if window:
        window.hide()


class BluetoothIndicator(Box):
    def __init__(self, show_window=True, **kwargs):
        super().__init__(name="bluetooth-indicator", orientation="h", **kwargs)
        self.show_window = show_window

        self.bluetooth = BluetoothClient()
        self.bt_icon = svg_file("applets/bluetooth-clear.svg", size=22)

        self.bt_button = Button(
            name="bt-button", child=self.bt_icon, on_clicked=self.on_bluetooth_clicked
        )

        self.add(self.bt_button)

        # Set pointer cursor on hover
        setup_cursor_hover(self.bt_button, "pointer")

        # Setup control center using shared function
        (
            self.bluetooth_window,
            self.bluetooth_widget,
        ) = setup_control_center(
            self.show_window,
            "bluetooth",
            BluetoothConnections,
            self,
            pointing_to=self.bt_button,
            show_back_button=False,
        )

        modus_service.connect("bluetooth-changed", self.on_bluetooth_changed)
        self.bluetooth.connect("changed", self.on_bluetooth_direct_changed)
        self.bluetooth.connect("device-added", self.on_device_added)
        self.bluetooth.connect("device-removed", self.on_device_removed)

        self.update_modus_service_bluetooth_state()
        self.update_state()

    def update_state(self):
        if not self.bluetooth.enabled:
            self.bt_icon.dynamic_file("applets/bluetooth-off-clear.svg")
            tooltip = "Bluetooth disabled"
        else:
            connected_devices = self.bluetooth.connected_devices
            if connected_devices:
                self.bt_icon.dynamic_file("applets/bluetooth-clear.svg")
                if len(connected_devices) >= 1:
                    self.bt_icon.dynamic_file("applets/bluetooth-paired.svg")
                    device = connected_devices[0]
                    tooltip = f"Connected to {device.alias}"
                    if device.battery_percentage > 0:
                        tooltip += f" ({device.battery_percentage:.0f}%)"
                else:
                    tooltip = f"Connected to {len(connected_devices)} devices"
            else:
                self.bt_icon.dynamic_file("applets/bluetooth-clear.svg")
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
        handle_indicator_click(self.bluetooth_window)

    def close_bluetooth(self, *args):
        hide_control_center(self.bluetooth_window)

    def hide_controlcenter(self, *args):
        hide_control_center(self.bluetooth_window)


class NetworkIndicator(Box):
    def __init__(self, show_window=True, **kwargs):
        super().__init__(name="network-indicator", orientation="h", **kwargs)
        self.show_window = show_window

        self.network_service = NetworkClient()

        self.network_icon = svg_file("applets/wifi-clear.svg", size=22)

        self.network_button = Button(
            name="network-button",
            child=self.network_icon,
            on_clicked=self.on_wifi_clicked,
        )

        self.add(self.network_button)

        # Set pointer cursor on hover
        setup_cursor_hover(self.network_button, "pointer")

        # Setup control center using shared function
        (
            self.wifi_window,
            self.wifi_widget,
        ) = setup_control_center(
            self.show_window,
            "wifi",
            WifiConnections,
            self,
            pointing_to=self.network_button,
            show_back_button=False,
        )
        if self.wifi_window:
            self.wifi_window._pointing_widget = self.network_button

        modus_service.connect("wlan-changed", self.on_wlan_changed)
        self.network_service.connect("device-ready", self.on_wifi_device_added)
        self.network_service.connect("device-ready", self.on_ethernet_device_added)
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

        if self.network_service.wifi_device:
            wifi = self.network_service.wifi_device
            if not wifi.enabled:
                wlan_state = "disabled"
            elif wifi.ssid:
                wlan_state = f"connected:{wifi.ssid}"
                if wifi.strength >= 0:
                    wlan_state += f":{wifi.strength}%"
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
            if not wifi.enabled:
                icon_file = "wifi-off-clear.svg"
                tooltip = "WiFi disabled"
            elif wifi.ssid:
                wifi_icon_path = get_wifi_icon_for_strength(wifi.strength)
                self.network_icon.set_from_file(wifi_icon_path)
                tooltip = f"Connected to {wifi.ssid}"
                if wifi.strength >= 0:
                    tooltip += f" ({wifi.strength}%)"
                self.network_button.set_tooltip_text(tooltip)
                return  # Early return to avoid setting icon again
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

        self.network_icon.dynamic_file(f"applets/{icon_file}")
        self.network_button.set_tooltip_text(tooltip)

    def on_wifi_clicked(self, *args):
        handle_indicator_click(self.wifi_window)

    def close_wifi(self, *args):
        hide_control_center(self.wifi_window)

    def on_wifi_direct_changed(self, *args):
        hide_control_center(self.wifi_window)

    def on_network_clicked(self, *args):
        handle_indicator_click(self.wifi_window)

    def hide_controlcenter(self, *args):
        hide_control_center(self.wifi_window)


class BatteryIndicator(Box):
    def __init__(self, show_window=True, **kwargs):
        super().__init__(name="battery-indicator", orientation="h", **kwargs)
        self.show_window = show_window

        self.battery_service = Battery()

        self.battery_icon = svg_file("battery/battery-100.svg", size=23)

        self.battery_button = Button(
            name="battery-button",
            child=self.battery_icon,
            on_clicked=self.on_battery_clicked,
        )

        self.battery_label = Label(name="battery-label", label="--- %")

        self.add(self.battery_label)
        self.add(self.battery_button)

        # Set pointer cursor on hover
        setup_cursor_hover(self.battery_button, "pointer")

        (
            self.battery_window,
            self.battery_widget,
        ) = setup_control_center(
            self.show_window,
            "battery",
            BatteryControl,
            self,
            pointing_to=self.battery_button,
            show_back_button=False,
        )
        if self.battery_window:
            self.battery_window._pointing_widget = self.battery_button

        modus_service.connect("battery-changed", self.on_battery_changed)
        self.battery_service.connect("changed", self.on_battery_direct_changed)

        self.update_modus_service_battery_state()
        self.update_state()

    def on_battery_changed(self, service, new_battery_state):
        self.update_state()

    def on_battery_direct_changed(self, *args):
        self.update_modus_service_battery_state()
        self.update_state()
        hide_control_center(self.battery_window)

    def _get_percentage(self):
        return int(self.battery_service.percent)

    def _get_state(self):
        if self.battery_service.charging:
            return "CHARGING"
        if self.battery_service.discharging:
            return "DISCHARGING"
        if self.battery_service.charged:
            return "FULLY_CHARGED"
        return "UNKNOWN"

    def _is_present(self):
        return self.battery_service.available

    def _get_time_to_empty(self):
        return self.battery_service.time_remaining

    def _get_time_to_full(self):
        return self.battery_service.time_to_full

    def _format_time(self, seconds: int) -> str:
        return format_duration(seconds)

    def _get_battery_icon_file(self, percentage: int, is_charging: bool) -> str:
        clamped = max(0, min(100, percentage))
        step = (clamped // 10) * 10
        filename = f"battery-{step:03d}{'-charging' if is_charging else ''}.svg"
        return f"battery/{filename}"

    def update_modus_service_battery_state(self):
        if not self._is_present():
            battery_state = "not_present"
        else:
            percentage = self._get_percentage()
            state_str = self._get_state().lower()

            battery_state = f"{state_str}:{percentage}%"

            if state_str == "discharging":
                time_to_empty = self._format_time(self._get_time_to_empty())
                if time_to_empty != "N/A":
                    battery_state += f":{time_to_empty}"
            elif state_str == "charging":
                time_to_full = self._format_time(self._get_time_to_full())
                if time_to_full != "N/A":
                    battery_state += f":{time_to_full}"

        modus_service.battery = battery_state

    def get_battery_tooltip(self, percentage, state):
        tooltip = f"Battery: {percentage}%"

        if state == "CHARGING":
            tooltip += " (Charging)"
            time_to_full = self._format_time(self._get_time_to_full())
            if time_to_full != "N/A":
                tooltip += f" - {time_to_full} until full"
        elif state == "DISCHARGING":
            time_to_empty = self._format_time(self._get_time_to_empty())
            if time_to_empty != "N/A":
                tooltip += f" - {time_to_empty} remaining"
        elif state == "FULLY_CHARGED":
            tooltip += " (Fully charged)"

        return tooltip

    def update_state(self):
        if not self._is_present():
            print("[Battery] No battery detected, hiding indicator")
            self.hide()
            return
        else:
            self.show()

            percentage = self._get_percentage()
            state = self._get_state()
            is_charging = state in ["CHARGING", "FULLY_CHARGED"]

            icon_file = self._get_battery_icon_file(percentage, is_charging)
            tooltip = self.get_battery_tooltip(percentage, state)
            percentage_text = f"{percentage}%"

            self.battery_icon.dynamic_file(icon_file)
            self.battery_button.set_tooltip_text(tooltip)
            self.battery_label.set_label(percentage_text)

    def on_battery_clicked(self, *args):
        handle_indicator_click(self.battery_window)

    def close_battery(self, *args):
        hide_control_center(self.battery_window)

    def hide_controlcenter(self, *args):
        hide_control_center(self.battery_window)

    def destroy(self):
        """Clean up resources when the indicator is destroyed."""
        # Disconnect signals
        try:
            modus_service.disconnect_by_func(self.on_battery_changed)
            if hasattr(self, "battery_service") and self.battery_service:
                self.battery_service.disconnect_by_func(self.on_battery_direct_changed)
        except Exception as e:
            logger.error(f"Error disconnecting battery indicator signals: {e}")

        # Destroy window and widget
        try:
            if hasattr(self, "battery_widget") and self.battery_widget:
                self.battery_widget.destroy()
            if hasattr(self, "battery_window") and self.battery_window:
                self.battery_window.destroy()
        except Exception as e:
            logger.error(f"An error occurred: {e}")

        super().destroy()


# Add destroy methods to other classes in this file as well
def add_destroy_to_indicators():
    # BluetoothIndicator

    def bt_destroy(self):
        try:
            modus_service.disconnect_by_func(self.on_bluetooth_changed)
            if hasattr(self, "bluetooth") and self.bluetooth:
                self.bluetooth.disconnect_by_func(self.on_bluetooth_direct_changed)
                self.bluetooth.disconnect_by_func(self.on_device_added)
                self.bluetooth.disconnect_by_func(self.on_device_removed)
        except Exception as e:
            logger.error(f"Error disconnecting bluetooth indicator signals: {e}")
        try:
            if hasattr(self, "bluetooth_widget") and self.bluetooth_widget:
                self.bluetooth_widget.destroy()
            if hasattr(self, "bluetooth_window") and self.bluetooth_window:
                self.bluetooth_window.destroy()
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        Box.destroy(self)

    BluetoothIndicator.destroy = bt_destroy

    # NetworkIndicator
    def net_destroy(self):
        try:
            modus_service.disconnect_by_func(self.on_wlan_changed)
            if hasattr(self, "network_service") and self.network_service:
                self.network_service.disconnect_by_func(self.on_wifi_device_added)
                self.network_service.disconnect_by_func(self.on_ethernet_device_added)
                self.network_service.disconnect_by_func(self.on_network_changed)

                # Also disconnect from the devices themselves if they exist
                if (
                    hasattr(self.network_service, "wifi_device")
                    and self.network_service.wifi_device
                ):
                    try:
                        self.network_service.wifi_device.disconnect_by_func(
                            self.on_network_direct_changed
                        )
                    except Exception as e:
                        logger.error(f"An error occurred: {e}")
                if (
                    hasattr(self.network_service, "ethernet_device")
                    and self.network_service.ethernet_device
                ):
                    try:
                        self.network_service.ethernet_device.disconnect_by_func(
                            self.on_network_direct_changed
                        )
                    except Exception as e:
                        logger.error(f"An error occurred: {e}")
        except Exception as e:
            logger.error(f"Error disconnecting network indicator signals: {e}")
        try:
            if hasattr(self, "wifi_widget") and self.wifi_widget:
                self.wifi_widget.destroy()
            if hasattr(self, "wifi_window") and self.wifi_window:
                self.wifi_window.destroy()
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        Box.destroy(self)

    NetworkIndicator.destroy = net_destroy


# Apply the destroy methods
add_destroy_to_indicators()
