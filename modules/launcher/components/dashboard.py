import subprocess
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.utils.helpers import exec_shell_command_async, exec_shell_command
import gi
from gi.repository import Gtk, Gdk, GLib  # Added Gdk import
from fabric.utils import get_relative_path

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
        self.network_icon = Label(
            name="network-icon",
            markup=icons.wifi,
        )
        self.network_label = Label(
            name="network-label",
            label="Wi-Fi",
            justification="left",
        )
        self.network_label_box = Box(children=[self.network_label, Box(h_expand=True)])
        self.network_ssid = Label(
            name="network-ssid",
            label="Hello_World!!",
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
        self.check_hyprsunset()

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

    def check_hyprsunset(self, *args):
        """
        Update the button state based on whether hyprsunset is running.
        """
        try:
            subprocess.check_output(["pgrep", "hyprsunset"])
            self.night_mode_status.set_label("Enabled")
            for widget in self.widgets:
                widget.remove_style_class("disabled")
        except subprocess.CalledProcessError:
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
        self.check_wlinhibit()

    def toggle_wlinhibit(self, *args):
        """
        Toggle the 'wlinhibit' process:
          - If running, kill it and mark as 'Disabled' (add 'disabled' class).
          - If not running, start it and mark as 'Enabled' (remove 'disabled' class).
        """
        try:
            subprocess.check_output(["pgrep", "wlinhibit"])
            exec_shell_command_async("pkill wlinhibit")
            self.caffeine_status.set_label("Disabled")
            for i in self.widgets:
                i.add_style_class("disabled")
        except subprocess.CalledProcessError:
            exec_shell_command_async("wlinhibit")
            self.caffeine_status.set_label("Enabled")
            for i in self.widgets:
                i.remove_style_class("disabled")

    def check_wlinhibit(self, *args):
        try:
            subprocess.check_output(["pgrep", "wlinhibit"])
            self.caffeine_status.set_label("Enabled")
            for i in self.widgets:
                i.remove_style_class("disabled")
        except subprocess.CalledProcessError:
            self.caffeine_status.set_label("Disabled")
            for i in self.widgets:
                i.add_style_class("disabled")


class DarkModeButton(Button):
    def __init__(self):
        self.dark_mode_icon = Label(
            name="dark-mode-icon",
            markup=icons.darkmode,
        )
        self.dark_mode_label = Label(
            name="dark-mode-label", label="Dark Mode", justification="left"
        )

        self.dark_mode_label_box = Box(
            children=[self.dark_mode_label, Box(h_expand=True)]
        )
        self.dark_mode_status = Label(
            name="dark-mode-status", label="Enabled", justification="left"
        )
        self.dark_mode_status_box = Box(
            children=[self.dark_mode_status, Box(h_expand=True)]
        )
        self.dark_mode_text = Box(
            name="dark-mode-text",
            orientation="v",
            h_align="start",
            v_align="center",
            children=[self.dark_mode_label_box, self.dark_mode_status_box],
        )
        self.dark_mode_box = Box(
            h_align="start",
            v_align="center",
            spacing=10,
            children=[self.dark_mode_icon, self.dark_mode_text],
        )

        super().__init__(
            name="dark-mode-button",
            h_expand=True,
            child=self.dark_mode_box,
            on_clicked=self.toggle_darkmode,
        )
        add_hover_cursor(self)

        self.widgets = [
            self,
            self.dark_mode_label,
            self.dark_mode_status,
            self.dark_mode_icon,
        ]
        self.check_darkmode()

    def toggle_darkmode(self, *_):
        current_state = self.check_darkmode()
        new_mode = "dark" if not current_state else "light"
        command = f"bash {get_relative_path('../../../config/scripts/dark-theme.sh')} --set {new_mode}"
        GLib.spawn_command_line_async(command)

        self.dark_mode_status.set_label("Enabled" if new_mode == "dark" else "Disabled")

        # Apply or remove 'disabled' class
        if new_mode == "light":
            for widget in self.widgets:
                widget.add_style_class("disabled")
        else:
            for widget in self.widgets:
                widget.remove_style_class("disabled")

    def check_darkmode(self):
        result = exec_shell_command(
            "gsettings get org.gnome.desktop.interface color-scheme"
        )
        is_dark_mode = result.strip().replace("'", "") == "prefer-dark"

        if not is_dark_mode:
            for widget in self.widgets:
                widget.add_style_class("disabled")
        else:
            for widget in self.widgets:
                widget.remove_style_class("disabled")

        return is_dark_mode


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
        self.dark_mode_button = DarkModeButton()

        # Attach buttons into the grid (one row, four columns)
        self.attach(self.network_button, 0, 0, 1, 1)
        self.attach(self.bluetooth_button, 1, 0, 1, 1)
        self.attach(self.dark_mode_button, 2, 0, 1, 1)
        self.attach(self.night_mode_button, 0, 1, 1, 1)
        self.attach(self.caffeine_button, 1, 1, 1, 1)

        self.show_all()
