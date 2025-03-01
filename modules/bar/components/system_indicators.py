import subprocess
from fabric import Fabricator
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.bluetooth import BluetoothClient
from services import NetworkClient, audio
import utils.icons as icons


class SystemIndicators(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="h", spacing=2, **kwargs)

        self.bluetooth_icon = Label(name="system-indicator-icon")
        self.wifi_icon = Label(name="system-indicator-icon")
        self.volume_icon_button = Label(name="system-indicator-icon")
        self.microphone_icon = Label(name="system-indicator-icon")
        self.idle_label = Label(name="system-indicator-icon")
        self.night_label = Label(name="system-indicator-icon")

        for widget in [
            self.bluetooth_icon,
            self.wifi_icon,
            self.volume_icon_button,
            self.microphone_icon,
            self.idle_label,
            self.night_label,
        ]:
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

        Fabricator(interval=1000, poll_from=self.update_all_statuses)

        self.update_bluetooth_status()

    def update_all_statuses(self, *_args):
        self.update_idle_night_status()
        self.update_network_status()

    def update_idle_night_status(self, *_):
        """Updates the idle and night mode status icons."""
        self.idle_label.set_markup(
            icons.coffee
            if subprocess.run(
                ["pgrep", "-x", "wlinhibit"], capture_output=True
            ).returncode
            == 0
            else ""
        )

        self.night_label.set_markup(
            icons.night
            if subprocess.run(
                ["pgrep", "-x", "hyprsunset"], capture_output=True
            ).returncode
            == 0
            else ""
        )

    def update_volume_status(self, *_):
        """Updates the volume icon based on speaker status."""
        stream = self.audio_service.speaker
        if stream:
            volume_level = stream.volume
            self.volume_icon_button.set_markup(
                icons.vol_off
                if stream.muted
                else (
                    icons.vol_mute
                    if volume_level < 1
                    else (icons.vol_medium if volume_level >= 1 else icons.vol_high)
                )
            )

    def update_mic_status(self, *_):
        """Updates the microphone icon based on mute status."""
        mic = self.audio_service.microphone
        self.microphone_icon.set_markup(icons.mic_off if mic and mic.muted else "")
        self.microphone_icon.set_visible(bool(mic))

    def update_bluetooth_status(self, *_):
        """Updates the Bluetooth icon based on enabled status."""
        self.bluetooth_icon.set_markup(
            icons.bluetooth if self.bluetooth_client.enabled else icons.bluetooth_off
        )

    def update_network_status(self, *_):
        primary_device = self.network_client.primary_device

        if primary_device == "wifi" and self.network_client.wifi_device:
            wifi_device = self.network_client.wifi_device
            self.set_tooltip_text(self.network_client.wifi_device.ssid)

            if wifi_device.enabled:
                wifi_strength = wifi_device.strength

                if wifi_strength == -1:  # No active connection
                    icon_label = icons.wifi_off
                else:
                    icon_label = {
                        80: icons.wifi,
                        60: icons.good_signal,
                        40: icons.moderate_signal,
                        20: icons.weak_signal,
                        0: icons.no_signal,
                    }.get(min(80, 20 * round(wifi_strength / 20)), icons.wifi_off)
            else:
                icon_label = icons.wifi_off

        elif primary_device == "wired":
            icon_label = icons.lan
        else:
            icon_label = icons.wifi_off

        self.wifi_icon.set_markup(icon_label)
