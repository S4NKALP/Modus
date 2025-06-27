import subprocess

from fabric.bluetooth import BluetoothClient
from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from gi.repository import GLib

import config.data as data
import utils.icons as icons
from .notifications import Notifications
from services.network import NetworkClient


class WifiIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-network", **kwargs)

        self.network = NetworkClient()
        self.progress_bar = CircularProgressBar(
            name="button-network",
            size=28,
            line_width=2,
            start_angle=150,
            end_angle=390,
        )
        self.wifi_label = Label(name="network-label", markup=icons.loader)

        self.add(Overlay(child=self.progress_bar, overlays=self.wifi_label))

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
            self.wifi_label.set_markup(icons.world)
            self.progress_bar.value = 1.0  # Full circle for ethernet
            tooltip = f"Connected to Ethernet ({self.network.ethernet_device.speed})"
            self.set_tooltip_text(tooltip)
            return

        if not self.network.wifi_device:
            self.wifi_label.set_markup(icons.cloud_off)
            self.progress_bar.value = 0
            tooltip = "No WiFi device found"
        elif not self.network.wifi_device.wireless_enabled:
            self.wifi_label.set_markup(icons.cloud_off)
            self.progress_bar.value = 0
            tooltip = "WiFi disabled"
        else:
            active_ap = self.network.wifi_device.active_access_point
            if active_ap:
                strength = active_ap.strength
                self.progress_bar.value = strength / 100
                if strength >= 75:
                    self.wifi_label.set_markup(icons.wifi_3)
                elif strength >= 50:
                    self.wifi_label.set_markup(icons.wifi_2)
                elif strength >= 25:
                    self.wifi_label.set_markup(icons.wifi_1)
                else:
                    self.wifi_label.set_markup(icons.wifi_0)
                tooltip = f"Connected to {active_ap.ssid} ({strength}%)"
            else:
                self.wifi_label.set_markup(icons.world_off)
                self.progress_bar.value = 0
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
        super().__init__(name="button-bar-bluetooth", **kwargs)

        self.bluetooth = BluetoothClient()

        self.bt_label = Label(name="bluetooth-label", markup=icons.loader)
        self.add(self.bt_label)

        self.bluetooth.connect("changed", self.on_bluetooth_changed)
        self.bluetooth.connect("device-added", self.on_device_added)
        self.bluetooth.connect("device-removed", self.on_device_removed)

        self.update_state()

    def update_state(self):
        if not self.bluetooth.enabled:
            self.bt_label.set_markup(icons.bluetooth_off)
            tooltip = "Bluetooth disabled"
        else:
            connected_devices = self.bluetooth.connected_devices
            if connected_devices:
                self.bt_label.set_markup(icons.bluetooth_connected)
                if len(connected_devices) == 1:
                    device = connected_devices[0]
                    tooltip = f"Connected to {device.alias}"
                    if device.battery_percentage > 0:
                        tooltip += f" ({device.battery_percentage:.0f}%)"
                else:
                    tooltip = f"Connected to {len(connected_devices)} devices"
            else:
                if self.bluetooth.scanning:
                    self.bt_label.set_markup(icons.loader)
                    tooltip = "Scanning for devices..."
                else:
                    self.bt_label.set_markup(icons.bluetooth)
                    tooltip = "No devices connected"

        self.set_tooltip_text(tooltip)

    def on_bluetooth_changed(self, *args):
        self.update_state()

    def on_device_added(self, _, address):
        self.update_state()

    def on_device_removed(self, _, address):
        self.update_state()


class RecordingIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-recording", **kwargs)

        # Path to the screen-capture script
        self.script_path = get_relative_path("../../../scripts/screen-capture.sh")

        self.recording_label = Label(name="recording-label", markup=icons.screenrecord)
        self.add(self.recording_label)

        # Connect click to stop recording
        self.connect("clicked", self.on_stop_recording)

        # Start with indicator hidden
        self.hide()

        # Set up periodic checking for recording status
        self.check_recording_status()
        self.timeout_id = GLib.timeout_add(
            1000, self.check_recording_status
        )  # Check every second

    def check_recording_status(self):
        """Check if recording is currently active and update visibility."""
        try:
            result = subprocess.run(
                [self.script_path, "status"], capture_output=True, text=True, timeout=2
            )
            is_recording = result.stdout.strip() == "true"

            if is_recording:
                if not self.get_visible():
                    self.show()
                self.set_tooltip_text("Recording in progress - Click to stop")
            else:
                if self.get_visible():
                    self.hide()

        except Exception:
            # If we can't check status, hide the indicator
            if self.get_visible():
                self.hide()

        return True  # Continue the timeout

    def on_stop_recording(self, *args):
        """Stop the current recording."""
        try:
            subprocess.Popen([self.script_path, "record", "stop"])
            # The indicator will hide automatically on next status check
        except Exception as e:
            print(f"Error stopping recording: {e}")

    def cleanup(self):
        """Clean up the timeout when the indicator is destroyed."""
        if hasattr(self, "timeout_id"):
            GLib.source_remove(self.timeout_id)


class Indicators(Box):
    def __init__(self, **kwargs):
        self.recording_indicator = RecordingIndicator()
        self.notifications = Notifications()

        super().__init__(
            name="indicator",
            orientation="h" if not data.VERTICAL else "v",
            spacing=4,
            children=[WifiIndicator(), BluetoothIndicator(), self.recording_indicator, self.notifications],
            **kwargs,
        )
        self.show_all()

    def cleanup(self):
        """Clean up all indicators when the dock is destroyed."""
        if hasattr(self, "recording_indicator"):
            self.recording_indicator.cleanup()
