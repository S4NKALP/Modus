import config.data as data
import utils.icons as icons
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.label import Label
from gi.repository import Gdk, GLib
from services.battery import Battery as BatteryService


class Battery(Box):
    def __init__(self, **kwargs):
        orientation = "v" if data.VERTICAL else "h"
        super().__init__(
            name="battery", spacing=0, orientation=orientation, visible=True, **kwargs
        )

        self._battery = BatteryService()
        self._battery.changed.connect(self.update_battery)

        self.icon = Label(name="battery-icon", markup=icons.battery)
        self.circle = CircularProgressBar(
            name="battery-circle",
            value=0,
            size=26,
            line_width=2,
            start_angle=150,
            end_angle=390,
            style_classes="battery",
            child=self.icon,
        )

        self.circle_button = Button(
            name="battery-button",
            child=self.circle,
        )

        self.circle_button.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
        )
        self.circle_button.connect("enter-notify-event", self.on_button_enter)
        self.circle_button.connect("leave-notify-event", self.on_button_leave)
        self.circle_button.connect("button-press-event", self.on_button_press)

        self.level = Label(
            name="battery-level",
            style_classes="battery",
            label="0%",
        )

        self.battery_box = Box(
            name="battery-box",
            orientation=orientation,
            spacing=0,
            children=[self.circle_button],
        )

        if not data.VERTICAL:
            self.battery_box.add(self.level)

        self.circle_button.set_has_tooltip(True)
        self.battery_box.set_has_tooltip(True)
        self.level.set_has_tooltip(True)

        self.circle_button.connect("query-tooltip", self.on_query_tooltip)
        self.battery_box.connect("query-tooltip", self.on_query_tooltip)
        self.level.connect("query-tooltip", self.on_query_tooltip)

        self.add(self.battery_box)

        GLib.idle_add(self.update_battery)

    def on_button_enter(self, widget, event):
        window = widget.get_window()
        if window:
            window.set_cursor(Gdk.Cursor(Gdk.CursorType.HAND2))

    def on_button_leave(self, widget, event):
        window = widget.get_window()
        if window:
            window.set_cursor(None)

    def on_button_press(self, widget, event):
        if event.button == 1:  # Left click
            try:
                if (
                    not hasattr(self._battery, "_profile_proxy")
                    or not self._battery._profile_proxy
                ):
                    return False

                current_profile = self._battery._profile_proxy.ActiveProfile
                profiles = self._battery._profile_proxy.Profiles
                profile_names = []

                for profile in profiles:
                    if isinstance(profile, dict) and "Profile" in profile:
                        profile_names.append(profile["Profile"])
                    elif hasattr(profile, "Profile"):
                        profile_names.append(profile.Profile)
                    elif isinstance(profile, str):
                        profile_names.append(profile)

                if profile_names and current_profile in profile_names:
                    next_index = (profile_names.index(current_profile) + 1) % len(
                        profile_names
                    )
                    next_profile = profile_names[next_index]
                    self._battery._profile_proxy.ActiveProfile = next_profile
                else:
                    return False
            except Exception:
                return False
            return True
        return False

    def on_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
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
            status = f"{icons.bat_full} Fully Charged"
        elif state == "CHARGING":
            status = f"{icons.bat_charging} Charging"
        elif percentage <= 15 and state == "DISCHARGING":
            status = f"{icons.bat_low} Low Battery"
        elif state == "DISCHARGING":
            status = f"{icons.bat_discharging} Discharging"
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
            else:  # balanced
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

    def update_battery(self, *args):
        if not self._battery.is_present:
            self.set_visible(False)
            return True

        percentage = self._battery.percentage
        state = self._battery.state
        charging = state in ["CHARGING", "FULLY_CHARGED"]
        power_profile = self._battery.power_profile

        self.circle.set_value(percentage / 100.0)

        if percentage < 100:
            self.level.set_label(f"{int(percentage)}%")
            self.level.set_visible(True)
        else:
            self.level.set_visible(False)

        self.circle.remove_style_class("power-saver")
        self.circle.remove_style_class("performance")
        self.circle.remove_style_class("balanced")
        self.circle.remove_style_class("discharging")
        self.circle.remove_style_class("discharging-low")
        self.circle.remove_style_class("discharging-critical")
        self.icon.remove_style_class("discharging")
        self.icon.remove_style_class("discharging-low")
        self.icon.remove_style_class("discharging-critical")

        if power_profile:
            self.circle.add_style_class(power_profile)
            if power_profile == "power-saver":
                self.icon.set_markup(icons.power_saving)
            elif power_profile == "performance":
                self.icon.set_markup(icons.power_performance)
            else:  # balanced
                # In balanced mode, show discharging icons when discharging
                if state == "DISCHARGING":
                    if percentage <= 15:
                        self.icon.set_markup(icons.bat_low)
                        self.circle.add_style_class("discharging-critical")
                        self.icon.add_style_class("discharging-critical")
                    elif percentage <= 30:
                        self.icon.set_markup(icons.alert)
                        self.circle.add_style_class("discharging-low")
                        self.icon.add_style_class("discharging-low")
                    else:
                        self.icon.set_markup(icons.bat_discharging)
                        self.circle.add_style_class("discharging")
                        self.icon.add_style_class("discharging")
                elif state == "CHARGING":
                    self.icon.set_markup(icons.charging)
                else:
                    self.icon.set_markup(icons.battery)
        else:
            if state == "FULLY_CHARGED":
                self.icon.set_markup(icons.battery)
            elif state == "CHARGING":
                self.icon.set_markup(icons.charging)
            elif state == "DISCHARGING":
                self.icon.set_markup(icons.discharging)
            else:
                self.icon.set_markup(icons.battery)

        if percentage <= 15 and not charging:
            self.icon.add_style_class("alert")
            self.circle.add_style_class("alert")
        else:
            self.icon.remove_style_class("alert")
            self.circle.remove_style_class("alert")

        self.set_visible(True)
        return True
