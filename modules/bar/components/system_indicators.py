import subprocess
from fabric import Fabricator
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.bluetooth import BluetoothClient
from services import NetworkClient, audio
import utils.icons as icons


class SystemIndicators(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", spacing=2, **kwargs)

        self.bluetooth_icon = Label(name="system-indicator-icon")
        self.wifi_icon = Label(name="system-indicator-icon")
        self.volume_icon_button = Label(name="system-indicator-icon")
        self.microphone_icon = Label(name="system-indicator-icon")

        for widget in [
            self.bluetooth_icon,
            self.wifi_icon,
            self.volume_icon_button,
            self.microphone_icon,
        ]:
            widget.set_hexpand(False)
            widget.set_vexpand(False)
            self.add(widget)

        self.audio_service = audio
        self.bluetooth_client = BluetoothClient()
        self.network_client = NetworkClient()

        # Connect signals
        self.bluetooth_client.connect("changed", self.update_bluetooth_status)
        self.audio_service.connect("microphone_changed", self.update_mic_status)
        self.audio_service.connect("changed", self.update_volume_status)
        self.network_client.connect("device_ready", self.update_network_status)

        if self.network_client.wifi_device:
            self.network_client.wifi_device.connect(
                "changed", self.update_network_status
            )

        if self.network_client.ethernet_device:
            self.network_client.ethernet_device.connect(
                "changed", self.update_network_status
            )

        Fabricator(interval=1000, poll_from=self.update_network_status)

        self.update_bluetooth_status()

    def update_volume_status(self, *_):
        stream = self.audio_service.speaker
        if not stream:
            return

        # Normalize volume to integer percentage (0-100)
        volume_level = stream.volume
        if volume_level > 1:
            volume_level = min(int(volume_level), 100)
        else:
            volume_level = int(volume_level * 100)

        is_muted = stream.muted

        if is_muted:
            icon = icons.vol_off
        elif volume_level > 74:
            icon = icons.vol_high
        elif volume_level > 0:
            icon = icons.vol_medium
        else:
            icon = icons.vol_mute

        self.volume_icon_button.set_markup(icon)

        tooltip_text = "Muted" if is_muted else f"Volume: {volume_level}%"
        self.volume_icon_button.set_tooltip_text(tooltip_text)

    def update_mic_status(self, *_):
        mic = self.audio_service.microphone
        if not mic:
            return

        # Normalize volume to integer percentage (0-100)
        volume_level = mic.volume
        if volume_level > 1:
            volume_level = min(int(volume_level), 100)
        else:
            volume_level = int(volume_level * 100)

        is_muted = mic.muted
        icon = icons.mic_off if is_muted else icons.mic

        self.microphone_icon.set_markup(icon)
        tooltip_text = "Muted" if is_muted else f"Microphone: {volume_level}%"
        self.microphone_icon.set_tooltip_text(tooltip_text)

    def update_bluetooth_status(self, *_):
        if self.bluetooth_client.enabled:
            # Get a list of connected devices
            connected_devices = [
                device.name
                for device in self.bluetooth_client.devices
                if device.connected
            ]

            if connected_devices:
                self.bluetooth_icon.set_markup(icons.bluetooth_connected)
                self.bluetooth_icon.set_tooltip_text(f"{', '.join(connected_devices)}")
            else:
                self.bluetooth_icon.set_markup(icons.bluetooth)
                self.bluetooth_icon.set_tooltip_text(
                    "Bluetooth is enabled, no devices connected"
                )
        else:
            self.bluetooth_icon.set_markup(icons.bluetooth_off)
            self.bluetooth_icon.set_tooltip_text("Bluetooth is disabled")

    def update_network_status(self, *_):
        primary_device = self.network_client.primary_device

        if primary_device == "wifi" and self.network_client.wifi_device:
            wifi_device = self.network_client.wifi_device

            self.wifi_icon.set_tooltip_text(
                wifi_device.ssid if wifi_device.ssid else "No WiFi Connection"
            )

            if wifi_device.enabled:
                strength = wifi_device.strength

                if strength > 0:
                    if strength < 25:
                        icon_label = icons.wifi_0
                    elif strength < 50:
                        icon_label = icons.wifi_1
                    elif strength < 75:
                        icon_label = icons.wifi_2
                    else:
                        icon_label = icons.wifi_3
                else:
                    icon_label = icons.wifi_off
            else:
                icon_label = icons.wifi_off

        elif primary_device == "wired":
            icon_label = icons.lan
            self.wifi_icon.set_tooltip_text("Wired Connection")

        else:
            icon_label = icons.wifi_off  # No network

        self.wifi_icon.set_markup(icon_label)
