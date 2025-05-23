import subprocess
from gi.repository import Gtk, Gdk
from fabric import Fabricator
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
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

        # Create event box to wrap indicators
        self.event_box = Gtk.EventBox()
        self.indicators_box = Box(name="indicators-container", orientation="h", spacing=2)
        self.event_box.add(self.indicators_box)

        # Create revealers for additional indicators
        self.volume_revealer = Revealer(
            name="volume-revealer",
            transition_duration=250,
            transition_type="slide-left",
            child=self.volume_icon_button,
            child_revealed=False,
        )
        self.idle_revealer = Revealer(
            name="idle-revealer",
            transition_duration=250,
            transition_type="slide-left",
            child=self.idle_label,
            child_revealed=False,
        )
        self.night_revealer = Revealer(
            name="night-revealer",
            transition_duration=250,
            transition_type="slide-left",
            child=self.night_label,
            child_revealed=False,
        )
        self.power_revealer = Revealer(
            name="power-revealer",
            transition_duration=250,
            transition_type="slide-left",
            child=self.power_label,
            child_revealed=False,
        )

        # Add all indicators with revealers
        self.indicators_box.add(self.language_icon)
        self.indicators_box.add(self.wifi_icon)
        self.indicators_box.add(self.bluetooth_icon)
        self.indicators_box.add(self.volume_revealer)
        self.indicators_box.add(self.idle_revealer)
        self.indicators_box.add(self.night_revealer)
        self.indicators_box.add(self.power_revealer)

        # Add event box to main container
        self.add(self.event_box)

        # Connect click events
        self.event_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.event_box.connect("button-press-event", self.on_button_press)

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
        self.showing_all_indicators = False

    def on_button_press(self, widget, event):
        if event.button == 3:  # Right click
            self.toggle_labels()
            return True  # Stop event propagation
        elif event.button == 1:  # Left click
            self.toggle_all_indicators()
            return True  # Stop event propagation
        return False

    def toggle_all_indicators(self):
        self.showing_all_indicators = not self.showing_all_indicators
        
        # Toggle revealers
        self.volume_revealer.set_reveal_child(self.showing_all_indicators)
        self.idle_revealer.set_reveal_child(self.showing_all_indicators)
        self.night_revealer.set_reveal_child(self.showing_all_indicators)
        self.power_revealer.set_reveal_child(self.showing_all_indicators)

    def toggle_labels(self):
        # Toggle tooltips for all visible indicators
        for child in self.indicators_box.get_children():
            if isinstance(child, Label):
                current_tooltip = child.get_tooltip_text()
                if current_tooltip:
                    child.set_tooltip_text("")
                else:
                    # Restore original tooltip based on the indicator type
                    if child == self.wifi_icon:
                        self.update_network_status()
                    elif child == self.bluetooth_icon:
                        self.update_bluetooth_status()
                    elif child == self.volume_icon_button:
                        self.update_volume_status()
                    elif child == self.language_icon:
                        self.update_language()

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

