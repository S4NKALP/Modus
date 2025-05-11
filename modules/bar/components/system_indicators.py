import subprocess
from fabric import Fabricator
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.bluetooth import BluetoothClient
from services import network_client, audio
import utils.icons as icons
from fabric.hyprland.widgets import Language, HyprlandEvent, get_hyprland_connection


class SystemIndicators(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="h", spacing=2, name="system-indicator", **kwargs
        )

        self.bluetooth_icon = Label(name="system-indicator-icon")
        self.wifi_icon = Label(name="system-indicator-icon")
        self.volume_icon_button = Label(name="system-indicator-icon")
        self.language_icon = Label(name="lang-label")
        self.idle_label = Label(name="system-indicator-icon")
        self.night_label = Label(name="system-indicator-icon")
        self.power_label = Label(name="system-indicator-icon")


        for widget in [
            self.language_icon,
            self.bluetooth_icon,
            self.wifi_icon,
            self.volume_icon_button,
            self.idle_label,
            self.night_label,
            self.power_label,
        ]:
            self.add(widget)

        self.audio_service = audio
        self.bluetooth_client = BluetoothClient()
        self.network_client = network_client
        self.hyprland = get_hyprland_connection()

        # Connect signals
        self.bluetooth_client.connect("changed", self.update_bluetooth_status)
        self.audio_service.connect("changed", self.update_volume_status)
        self.network_client.connect("device_ready", self.update_network_status)
        self.hyprland.connect("event::activelayout", self.update_language)


        if self.network_client.wifi_device:
            self.network_client.wifi_device.connect(
                "changed", self.update_network_status
            )

        if self.network_client.ethernet_device:
            self.network_client.ethernet_device.connect(
                "changed", self.update_network_status
            )

        Fabricator(interval=1000, poll_from=self.update_all_statuses)

        # Initial updates
        self.update_bluetooth_status()
        self.update_language()
        self.update_idle_night_status()

    def update_all_statuses(self, *_args):
        self.update_idle_night_status()
        self.update_power_profile()
        self.update_network_status()

    def update_language(self, _=None, event: HyprlandEvent = None):
        """Update the language indicator based on Hyprland events."""
        lang = event.data[1] if event else Language().get_label()
        self.language_icon.set_tooltip_text(lang)
        self.language_icon.set_label(lang[:2].lower())

    def update_idle_night_status(self, *_):
        # Update idle status
        has_idle = (
            subprocess.run(["pgrep", "-x", "wlinhibit"], capture_output=True).returncode
            == 0
        )
        self.idle_label.set_visible(has_idle)
        self.idle_label.set_markup(icons.coffee if has_idle else "")

        # Update night mode status
        has_night = (
            subprocess.run(
                ["pgrep", "-x", "hyprsunset"], capture_output=True
            ).returncode
            == 0
        )
        self.night_label.set_visible(has_night)
        self.night_label.set_markup(icons.night if has_night else "")

    def update_volume_status(self, *_):
        stream = self.audio_service.speaker
        if not stream:
            self.volume_icon_button.set_visible(False)
            return

        self.volume_icon_button.set_visible(True)
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


    def update_bluetooth_status(self, *_):
        if self.bluetooth_client.enabled:
            self.bluetooth_icon.set_visible(True)
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
            self.bluetooth_icon.set_visible(True)  # Keep it visible
            self.bluetooth_icon.set_markup(icons.bluetooth_off)
            self.bluetooth_icon.set_tooltip_text("Bluetooth is disabled")

    def update_network_status(self, *_):
        primary_device = self.network_client.primary_device
        self.wifi_icon.set_visible(True)

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

    def update_power_profile(self, *_):
        try:
            result = subprocess.run(
                ["powerprofilesctl", "get"], capture_output=True, text=True
            )
            current_profile = result.stdout.strip()

            profile_icons = {
                "performance": icons.power_performance,
                "balanced": "",
                "power-saver": icons.power_saving,
            }

            icon = profile_icons.get(current_profile)
            tooltip = (
                f"Power Profile: {current_profile.capitalize()}"
                if current_profile
                else "Unknown Profile"
            )

            self.power_label.set_visible(bool(icon))  # Only show if there's an icon
            self.power_label.set_markup(icon)
            self.power_label.set_tooltip_text(tooltip)

        except Exception as e:
            self.power_label.set_visible(False)
            self.power_label.set_tooltip_text(f"Error fetching power profile: {e}")

