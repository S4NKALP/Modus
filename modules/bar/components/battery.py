import subprocess
import re
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.overlay import Overlay
from fabric.widgets.revealer import Revealer
from fabric.core.fabricator import Fabricator
from fabric.utils.helpers import exec_shell_command_async
from gi.repository import GLib
import utils.icons as icons


class Battery(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="battery",
            orientation="v",
            spacing=0,
        )

        self.bat_save = Button(
            name="battery-save",
            child=Label(name="battery-save-label", markup=icons.power_saving),
            on_clicked=lambda *_: self.set_power_mode("powersave"),
        )
        self.bat_balanced = Button(
            name="battery-balanced",
            child=Label(name="battery-balanced-label", markup=icons.power_balanced),
            on_clicked=lambda *_: self.set_power_mode("balanced"),
        )
        self.bat_perf = Button(
            name="battery-performance",
            child=Label(
                name="battery-performance-label", markup=icons.power_performance
            ),
            on_clicked=lambda *_: self.set_power_mode("performance"),
        )
        self.bat_level = Label(
            name="battery-level",
            label="100%",
        )

        for btn in [self.bat_save, self.bat_balanced, self.bat_perf]:
            btn.connect("enter-notify-event", self.on_mouse_enter)
            btn.connect("leave-notify-event", self.on_mouse_leave)

        self.mode_switcher = Box(
            name="power-mode-switcher",
            orientation="v",
            spacing=4,
            children=[self.bat_level, self.bat_save, self.bat_balanced, self.bat_perf],
        )

        self.bat_icon = Label(name="battery-icon", markup=icons.battery)

        self.bat_circle = CircularProgressBar(
            name="battery-circle",
            value=0,
            size=28,
            line_width=2,
            start_angle=150,
            end_angle=390,
        )

        self.bat_overlay = Overlay(
            name="battery-overlay",
            visible=False,
            child=self.bat_circle,
            overlays=[self.bat_icon],
        )

        self.bat_revealer = Revealer(
            name="battery-revealer",
            transition_duration=250,
            transition_type="slide-up",
            child=self.mode_switcher,
            child_revealed=False,
        )

        inner_container = Box(orientation="v", spacing=3)
        inner_container.add(self.bat_overlay)
        inner_container.add(self.bat_revealer)
        inner_container.add(self.mode_switcher)

        self.event_box = EventBox(
            events=["enter-notify-event", "leave-notify-event"],
            name="battery-eventbox",
        )
        self.event_box.connect("enter-notify-event", self.on_mouse_enter)
        self.event_box.connect("leave-notify-event", self.on_mouse_leave)
        self.event_box.add(inner_container)

        self.add(self.event_box)

        self.current_mode = None
        self.hide_timer = None
        self.hover_counter = 0

        # Fabricator for battery polling every second
        self.batt_fabricator = Fabricator(
            lambda *args, **kwargs: self.poll_battery(),
            interval=1000,
            stream=False,
            default_value=0,
        )
        self.batt_fabricator.changed.connect(self.update_battery)

        # Fabricator for power profile monitoring every 5 seconds
        self.profile_fabricator = Fabricator(
            lambda *args, **kwargs: self.get_active_power_profile(),
            interval=5000,  # Check every 5 seconds
            stream=False,
            default_value="balanced",
        )
        self.profile_fabricator.changed.connect(self.set_active_profile)

        # Run initial UI updates
        GLib.idle_add(self.update_battery, None, self.poll_battery())
        GLib.idle_add(self.set_active_profile, None, self.get_active_power_profile())

    def on_mouse_enter(self, widget, event):
        """Reveal battery level on hover."""
        self.hover_counter += 1
        if self.hide_timer is not None:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = None
        self.bat_revealer.set_reveal_child(True)
        return False

    def on_mouse_leave(self, widget, event):
        """Schedule hiding the battery level after a 0.5s delay only if not hovering any element."""
        if self.hover_counter > 0:
            self.hover_counter -= 1
        if self.hover_counter == 0:
            if self.hide_timer is not None:
                GLib.source_remove(self.hide_timer)
            self.hide_timer = GLib.timeout_add(500, self.hide_revealer)
        return False

    def hide_revealer(self):
        self.bat_revealer.set_reveal_child(False)
        self.hide_timer = None
        return False

    def poll_battery(self):
        """Polls the battery status using 'acpi -b' command."""
        try:
            output = subprocess.check_output(["acpi", "-b"]).decode("utf-8").strip()
            if "Battery" not in output:
                return (0, None)
            match_percent = re.search(r"(\d+)%", output)
            match_status = re.search(r"Battery \d+: (\w+)", output)
            if match_percent:
                percent = int(match_percent.group(1))
                status = match_status.group(1) if match_status else None
                return (percent / 100.0, status)
        except Exception:
            pass
        return (0, None)

    def update_battery(self, sender, battery_data):
        """Updates the battery widget UI."""
        value, status = battery_data
        if value == 0:
            self.bat_overlay.set_visible(False)
            self.bat_revealer.set_visible(False)
        else:
            self.bat_overlay.set_visible(True)
            self.bat_revealer.set_visible(True)
            self.bat_circle.set_value(value)

        percentage = int(value * 100)
        self.bat_level.set_label(f"{percentage}%")

        if percentage <= 15:
            self.bat_icon.set_markup(icons.alert)
            self.bat_icon.add_style_class("alert")
            self.bat_circle.add_style_class("alert")
        else:
            self.bat_icon.remove_style_class("alert")
            self.bat_circle.remove_style_class("alert")
            if status == "Discharging":
                self.bat_icon.set_markup(icons.discharging)
            elif percentage == 100:
                self.bat_icon.set_markup(icons.battery)
            elif status == "Charging":
                self.bat_icon.set_markup(icons.charging)
            else:
                self.bat_icon.set_markup(icons.battery)

    def get_active_power_profile(self):
        """Returns the currently active power profile using powerprofilesctl."""
        try:
            output = (
                subprocess.check_output(["powerprofilesctl", "get"])
                .decode("utf-8")
                .strip()
            )
            return output
        except Exception as err:
            print(f"Error fetching active power profile: {err}")
            return "balanced"

    def set_active_profile(self, sender, profile):
        """Detects the current power profile and updates the UI accordingly."""
        profile_map = {
            "power-saver": "powersave",
            "balanced": "balanced",
            "performance": "performance",
        }
        if profile in profile_map and self.current_mode != profile_map[profile]:
            self.set_power_mode(profile_map[profile])

    def set_power_mode(self, mode):
        """Switches power mode using power-profile-daemon."""
        commands = {
            "powersave": "powerprofilesctl set power-saver",
            "balanced": "powerprofilesctl set balanced",
            "performance": "powerprofilesctl set performance",
        }
        if mode in commands:
            try:
                exec_shell_command_async(commands[mode])
                self.current_mode = mode
                self.update_button_styles()
            except Exception as err:
                print(f"Error setting power mode: {err}")

    def update_button_styles(self):
        """Updates button styles to reflect the current mode."""
        for btn, mode in zip(
            [self.bat_save, self.bat_balanced, self.bat_perf],
            ["powersave", "balanced", "performance"],
        ):
            if self.current_mode == mode:
                btn.add_style_class("active")
            else:
                btn.remove_style_class("active")
