import subprocess
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.utils.helpers import exec_shell_command_async
import gi
from gi.repository import Gtk, Gdk, GLib
from services import network_client
from services.powerprofile import PowerProfiles
from fabric import Fabricator

gi.require_version("Gtk", "3.0")
import utils.icons as icons


def add_hover_cursor(widget):
    # Add enter/leave events to change the cursor
    widget.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
    widget.connect(
        "enter-notify-event",
        lambda w, e: w.get_window().set_cursor(
            Gdk.Cursor.new_from_name(w.get_display(), "pointer")
        )
        if w.get_window()
        else None,
    )
    widget.connect(
        "leave-notify-event",
        lambda w, e: w.get_window().set_cursor(None) if w.get_window() else None,
    )


class NetworkButton(Box):
    def __init__(self):
        self.network_client = network_client
        self._animation_timeout_id = None
        self._animation_step = 0
        self._animation_direction = 1

        self.network_icon = Label(
            name="network-icon",
            markup=None,
        )
        self.network_label = Label(
            name="network-label",
            label="Wi-Fi",
            justification="left",
        )
        self.network_label_box = Box(children=[self.network_label, Box(h_expand=True)])
        self.network_ssid = Label(
            name="network-ssid",
            justification="left",
        )
        self.network_ssid_box = Box(children=[self.network_ssid, Box(h_expand=True)])
        self.network_text = Box(
            name="network-text",
            orientation="v",
            h_align="start",
            v_align="center",
            children=[self.network_label_box, self.network_ssid_box],
        )
        self.network_status_box = Box(
            h_align="start",
            v_align="center",
            spacing=10,
            children=[self.network_icon, self.network_text],
        )
        self.network_status_button = Button(
            name="network-status-button",
            h_expand=True,
            child=self.network_status_box,
            on_clicked=lambda *_: self.network_client.wifi_device.toggle_wifi()
            if self.network_client.wifi_device
            else None,
        )
        add_hover_cursor(self.network_status_button)  # <-- Added hover

        self.network_menu_label = Label(
            name="network-menu-label",
            markup=icons.chevron_right,
        )
        self.network_menu_button = Button(
            name="network-menu-button",
            child=self.network_menu_label,
        )
        add_hover_cursor(self.network_menu_button)  # <-- Added hover

        super().__init__(
            name="network-button",
            orientation="h",
            h_align="fill",
            v_align="fill",
            h_expand=True,
            v_expand=True,
            spacing=0,
            children=[self.network_status_button, self.network_menu_button],
        )

        self.widgets = [
            self,
            self.network_icon,
            self.network_label,
            self.network_ssid,
            self.network_status_button,
            self.network_menu_button,
            self.network_menu_label,
        ]

        # Connect to wifi device signals when ready
        self.network_client.connect("device-ready", self._on_wifi_ready)

        # Check initial state using idle_add to defer until GTK loop is running
        GLib.idle_add(self._initial_update)

    def _initial_update(self):
        self.update_state()
        return False  # Run only once

    def _on_wifi_ready(self, *args):
        if self.network_client.wifi_device:
            self.network_client.wifi_device.connect(
                "notify::enabled", self.update_state
            )
            self.network_client.wifi_device.connect("notify::ssid", self.update_state)
            self.update_state()

    def _animate_searching(self):
        """Animate wifi icon when searching for networks"""
        wifi_icons = [
            icons.wifi_0,
            icons.wifi_1,
            icons.wifi_2,
            icons.wifi_3,
            icons.wifi_2,
            icons.wifi_1,
        ]

        # Si el widget no existe o el WiFi está desactivado, detener la animación
        wifi = self.network_client.wifi_device
        if not self.network_icon or not wifi or not wifi.enabled:
            self._stop_animation()
            return False

        # Si estamos conectados, detener la animación
        if wifi.state == "activated" and wifi.ssid != "Disconnected":
            self._stop_animation()
            return False

        GLib.idle_add(self.network_icon.set_markup, wifi_icons[self._animation_step])

        # Reiniciar al principio cuando llegamos al final
        self._animation_step = (self._animation_step + 1) % len(wifi_icons)

        return True  # Mantener la animación activa

    def _start_animation(self):
        if self._animation_timeout_id is None:
            self._animation_step = 0
            self._animation_direction = 1
            # Ejecuta la animación cada 500ms sin usar idle_add
            self._animation_timeout_id = GLib.timeout_add(500, self._animate_searching)

    def _stop_animation(self):
        if self._animation_timeout_id is not None:
            GLib.source_remove(self._animation_timeout_id)
            self._animation_timeout_id = None

    def update_state(self, *args):
        """Update the button state based on network status"""
        wifi = self.network_client.wifi_device
        ethernet = self.network_client.ethernet_device

        # Update enabled/disabled state
        if wifi and not wifi.enabled:
            self._stop_animation()
            self.network_icon.set_markup(icons.wifi_off)
            for widget in self.widgets:
                widget.add_style_class("disabled")
            self.network_ssid.set_label("Disabled")
            return

        # Remove disabled class if we got here
        for widget in self.widgets:
            widget.remove_style_class("disabled")

        # Update text and animation based on state
        if wifi and wifi.enabled:
            if wifi.state == "activated" and wifi.ssid != "Disconnected":
                self._stop_animation()
                self.network_ssid.set_label(wifi.ssid)
                # Update icon based on signal strength
                if wifi.strength > 0:
                    strength = wifi.strength
                    if strength < 25:
                        self.network_icon.set_markup(icons.wifi_0)
                    elif strength < 50:
                        self.network_icon.set_markup(icons.wifi_1)
                    elif strength < 75:
                        self.network_icon.set_markup(icons.wifi_2)
                    else:
                        self.network_icon.set_markup(icons.wifi_3)
            else:
                self.network_ssid.set_label("Enabled")
                self._start_animation()

        # Handle primary device check safely
        try:
            primary_device = self.network_client.primary_device
        except AttributeError:
            primary_device = "wireless"  # Default to wireless if error occurs

        # Handle wired connection case
        if primary_device == "wired":
            self._stop_animation()
            if ethernet and ethernet.internet == "activated":
                self.network_icon.set_markup(icons.world)
            else:
                self.network_icon.set_markup(icons.world_off)
        else:
            if not wifi:
                self._stop_animation()
                self.network_icon.set_markup(icons.wifi_off)
            elif (
                wifi.state == "activated"
                and wifi.ssid != "Disconnected"
                and wifi.strength > 0
            ):
                self._stop_animation()
                strength = wifi.strength
                if strength < 25:
                    self.network_icon.set_markup(icons.wifi_0)
                elif strength < 50:
                    self.network_icon.set_markup(icons.wifi_1)
                elif strength < 75:
                    self.network_icon.set_markup(icons.wifi_2)
                else:
                    self.network_icon.set_markup(icons.wifi_3)
            else:
                self._start_animation()


class BluetoothButton(Box):
    def __init__(self, launcher):
        super().__init__(
            name="bluetooth-button",
            orientation="h",
            h_align="fill",
            v_align="fill",
            h_expand=True,
            v_expand=True,
        )
        self.launcher = launcher

        self.bluetooth_icon = Label(
            name="bluetooth-icon",
            markup=icons.bluetooth,
        )
        self.bluetooth_label = Label(
            name="bluetooth-label",
            label="Bluetooth",
            justification="left",
        )
        self.bluetooth_label_box = Box(
            children=[self.bluetooth_label, Box(h_expand=True)]
        )
        self.bluetooth_status_text = Label(
            name="bluetooth-status",
            label="Disabled",
            justification="left",
        )
        self.bluetooth_status_box = Box(
            children=[self.bluetooth_status_text, Box(h_expand=True)]
        )
        self.bluetooth_text = Box(
            orientation="v",
            h_align="start",
            v_align="center",
            children=[self.bluetooth_label_box, self.bluetooth_status_box],
        )
        self.bluetooth_status_container = Box(
            h_align="start",
            v_align="center",
            spacing=10,
            children=[self.bluetooth_icon, self.bluetooth_text],
        )
        self.bluetooth_status_button = Button(
            name="bluetooth-status-button",
            h_expand=True,
            child=self.bluetooth_status_container,
            on_clicked=lambda *_: self.launcher.bluetooth.client.toggle_power(),
        )
        add_hover_cursor(self.bluetooth_status_button)  # <-- Added hover
        self.bluetooth_menu_label = Label(
            name="bluetooth-menu-label",
            markup=icons.chevron_right,
        )
        self.bluetooth_menu_button = Button(
            name="bluetooth-menu-button",
            on_clicked=lambda *_: self.launcher.open("bluetooth"),
            child=self.bluetooth_menu_label,
        )
        add_hover_cursor(self.bluetooth_menu_button)  # <-- Added hover

        self.add(self.bluetooth_status_button)
        self.add(self.bluetooth_menu_button)


class NightModeButton(Button):
    def __init__(self):
        self.night_mode_icon = Label(
            name="night-mode-icon",
            markup=icons.night,
        )
        self.night_mode_label = Label(
            name="night-mode-label",
            label="Night Mode",
            justification="left",
        )
        self.night_mode_label_box = Box(
            children=[self.night_mode_label, Box(h_expand=True)]
        )
        self.night_mode_status = Label(
            name="night-mode-status",
            label="Enabled",
            justification="left",
        )
        self.night_mode_status_box = Box(
            children=[self.night_mode_status, Box(h_expand=True)]
        )
        self.night_mode_text = Box(
            name="night-mode-text",
            orientation="v",
            h_align="start",
            v_align="center",
            children=[self.night_mode_label_box, self.night_mode_status_box],
        )
        self.night_mode_box = Box(
            h_align="start",
            v_align="center",
            spacing=10,
            children=[self.night_mode_icon, self.night_mode_text],
        )

        super().__init__(
            name="night-mode-button",
            h_expand=True,
            child=self.night_mode_box,
            on_clicked=self.toggle_hyprsunset,
        )
        add_hover_cursor(self)  # <-- Added hover

        self.widgets = [
            self,
            self.night_mode_label,
            self.night_mode_status,
            self.night_mode_icon,
        ]
        # self.check_hyprsunset()
        # **Monitor external changes every 3 seconds**
        self.hyprsunset_watcher = Fabricator(
            self.is_hyprsunset_running,
            interval=3000,
            stream=False,
            default_value=False,
        )
        self.hyprsunset_watcher.changed.connect(self.update_night_mode_status)
        self.update_night_mode_status(None, self.is_hyprsunset_running())

    def toggle_hyprsunset(self, *args):
        """
        Toggle the 'hyprsunset' process:
          - If running, kill it and mark as 'Disabled'.
          - If not running, start it and mark as 'Enabled'.
        """
        try:
            subprocess.check_output(["pgrep", "hyprsunset"])
            exec_shell_command_async("pkill hyprsunset")
            self.night_mode_status.set_label("Disabled")
            for widget in self.widgets:
                widget.add_style_class("disabled")
        except subprocess.CalledProcessError:
            exec_shell_command_async("hyprsunset -t 3500")
            self.night_mode_status.set_label("Enabled")
            for widget in self.widgets:
                widget.remove_style_class("disabled")

    def is_hyprsunset_running(self, *args):
        """Returns True if hyprsunset is running."""
        try:
            subprocess.check_output(["pgrep", "hyprsunset"])
            return True
        except subprocess.CalledProcessError:
            return False

    def update_night_mode_status(self, _, is_running):
        """Update UI based on hyprsunset status."""
        if is_running:
            self.night_mode_status.set_label("Enabled")
            for widget in self.widgets:
                widget.remove_style_class("disabled")
        else:
            self.night_mode_status.set_label("Disabled")
            for widget in self.widgets:
                widget.add_style_class("disabled")


class CaffeineButton(Button):
    def __init__(self):
        self.caffeine_icon = Label(
            name="caffeine-icon",
            markup=icons.coffee,
        )
        self.caffeine_label = Label(
            name="caffeine-label",
            label="Caffeine",
            justification="left",
        )
        self.caffeine_label_box = Box(
            children=[self.caffeine_label, Box(h_expand=True)]
        )
        self.caffeine_status = Label(
            name="caffeine-status",
            label="Enabled",
            justification="left",
        )
        self.caffeine_status_box = Box(
            children=[self.caffeine_status, Box(h_expand=True)]
        )
        self.caffeine_text = Box(
            name="caffeine-text",
            orientation="v",
            h_align="start",
            v_align="center",
            children=[self.caffeine_label_box, self.caffeine_status_box],
        )
        self.caffeine_box = Box(
            h_align="start",
            v_align="center",
            spacing=10,
            children=[self.caffeine_icon, self.caffeine_text],
        )
        super().__init__(
            name="caffeine-button",
            h_expand=True,
            child=self.caffeine_box,
            on_clicked=self.toggle_wlinhibit,
        )
        add_hover_cursor(self)  # <-- Added hover

        self.widgets = [
            self,
            self.caffeine_label,
            self.caffeine_status,
            self.caffeine_icon,
        ]
        # **Monitor external changes every 3 seconds**
        self.wlinhibit_watcher = Fabricator(
            self.is_wlinhibit_running,
            interval=3000,
            stream=False,
            default_value=False,
        )
        self.wlinhibit_watcher.changed.connect(self.update_wlinhibit_status)
        self.update_wlinhibit_status(None, self.is_wlinhibit_running())

    def toggle_wlinhibit(self, *args):
        """Toggle the 'wlinhibit' process."""
        if self.is_wlinhibit_running():
            exec_shell_command_async("pkill wlinhibit")
        else:
            exec_shell_command_async("wlinhibit")

    def is_wlinhibit_running(self, *args):
        """Returns True if wlinhibit is running. Accepts extra arguments to avoid Fabricator errors."""
        try:
            subprocess.check_output(["pgrep", "wlinhibit"])
            return True
        except subprocess.CalledProcessError:
            return False

    def update_wlinhibit_status(self, _, is_running):
        """Update UI based on wlinhibit status."""
        if is_running:
            self.caffeine_status.set_label("Enabled")
            for widget in self.widgets:
                widget.remove_style_class("disabled")
        else:
            self.caffeine_status.set_label("Disabled")
            for widget in self.widgets:
                widget.add_style_class("disabled")


class PowerProfileButton(Button):
    def __init__(self):
        self.power_profile_service = PowerProfiles.get_default()
        
        self.power_profile_icon = Label(
            name="power-profile-icon",
            markup=icons.power_balanced,  # Default icon
        )
        self.power_profile_label = Label(
            name="power-profile-label",
            label="Power Profile",
            justification="left",
        )
        self.power_profile_label_box = Box(
            children=[self.power_profile_label, Box(h_expand=True)]
        )
        self.power_profile_status = Label(
            name="power-profile-status",
            label="Balanced",
            justification="left",
        )
        self.power_profile_status_box = Box(
            children=[self.power_profile_status, Box(h_expand=True)]
        )
        self.power_profile_text = Box(
            name="power-profile-text",
            orientation="v",
            h_align="start",
            v_align="center",
            children=[self.power_profile_label_box, self.power_profile_status_box],
        )
        self.power_profile_box = Box(
            h_align="start",
            v_align="center",
            spacing=10,
            children=[self.power_profile_icon, self.power_profile_text],
        )

        super().__init__(
            name="power-profile-button",
            h_expand=True,
            child=self.power_profile_box,
            on_clicked=self.toggle_power_profile,
        )
        add_hover_cursor(self)

        self.widgets = [
            self,
            self.power_profile_label,
            self.power_profile_status,
            self.power_profile_icon,
        ]

        # Connect to power profile service signals
        self.power_profile_service.connect("profile", self.update_power_profile_status)
        
        # Initial update
        self.update_power_profile_status(None, self.power_profile_service.get_current_profile())

    def toggle_power_profile(self, *args):
        current_profile = self.power_profile_service.get_current_profile()
        profiles = ["power-saver", "balanced", "performance"]
        current_index = profiles.index(current_profile)
        next_profile = profiles[(current_index + 1) % len(profiles)]
        self.power_profile_service.set_power_profile(next_profile)

    def update_power_profile_status(self, _, profile):
        # Map profiles to their display names and icons
        profile_map = {
            "power-saver": {"name": "Power Saver", "icon": icons.power_saving},
            "balanced": {"name": "Balanced", "icon": icons.power_balanced},
            "performance": {"name": "Performance", "icon": icons.power_performance},
        }
        
        profile_info = profile_map.get(profile, profile_map["balanced"])
        self.power_profile_status.set_label(profile_info["name"])
        self.power_profile_icon.set_markup(profile_info["icon"])
        
        if profile == "balanced":
            for widget in self.widgets:
                widget.add_style_class("disabled")
        else:
            for widget in self.widgets:
                widget.remove_style_class("disabled")



class Dashboard(Gtk.Grid):
    def __init__(self, **kwargs):
        super().__init__(name="buttons-grid")
        self.set_row_homogeneous(True)
        self.set_column_homogeneous(True)
        self.set_row_spacing(8)
        self.set_column_spacing(8)
        self.set_vexpand(True)  # Prevent vertical expansion

        self.launcher = kwargs["launcher"]

        # Instantiate each button
        self.network_button = NetworkButton()
        self.bluetooth_button = BluetoothButton(self.launcher)
        self.night_mode_button = NightModeButton()
        self.caffeine_button = CaffeineButton()
        self.power_profile_button = PowerProfileButton()

        # Attach buttons into the grid (two rows, three columns)
        self.attach(self.network_button, 0, 0, 1, 1)
        self.attach(self.bluetooth_button, 1, 0, 1, 1)
        self.attach(self.power_profile_button, 2, 0, 1, 1)
        self.attach(self.night_mode_button, 0, 1, 1, 1)
        self.attach(self.caffeine_button, 1, 1, 1, 1)

        self.show_all()
