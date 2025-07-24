from gi.repository import GLib

from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.button import Button
from services.battery import Battery as BatteryService
import utils.icons as icons
import config.data as data


class Battery(Box):
    def __init__(self, **kwargs):
        orientation = "v" if data.VERTICAL else "h"
        super().__init__(
            name="battery", spacing=0, orientation=orientation, visible=True, **kwargs
        )

        # Initialize battery service
        self._battery = BatteryService()
        self._battery.changed.connect(self.update_battery)

        # Create the battery icon and circular progress
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

        # Create button to hold the circle
        self.circle_button = Button(
            name="battery-button",
            child=self.circle,
        )

        # Create percentage label
        self.level = Label(
            name="battery-level",
            style_classes="battery",
            label="0%",
        )

        # Create the container box
        self.battery_box = Box(
            name="battery-box",
            orientation=orientation,
            spacing=0,
            children=[self.circle_button],
        )

        # Only add level label in horizontal mode
        if not data.VERTICAL:
            self.battery_box.add(self.level)

        # Enable tooltips
        self.circle_button.set_has_tooltip(True)
        self.battery_box.set_has_tooltip(True)
        self.level.set_has_tooltip(True)

        # Connect tooltip signals
        self.circle_button.connect("query-tooltip", self.on_query_tooltip)
        self.battery_box.connect("query-tooltip", self.on_query_tooltip)
        self.level.connect("query-tooltip", self.on_query_tooltip)

        # Add the battery box to self
        self.add(self.battery_box)

        # Initial update
        GLib.idle_add(self.update_battery)

    def on_query_tooltip(self, _widget, _x, _y, _keyboard_mode, tooltip):
        """Handle tooltip query"""
        tooltip.set_markup(self.get_tooltip_text())
        return True

    def get_tooltip_text(self):
        """Get formatted tooltip text in bullet points"""
        if not self._battery.is_present:
            return "No battery detected"

        percentage = self._battery.percentage
        state = self._battery.state
        # Get capacity as integer by converting from float
        capacity = int(float(self._battery.capacity.rstrip("%")))
        tooltip_points = []

        # Status and percentage
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

        # Battery level and capacity
        tooltip_points.append(f"• Level: {int(percentage)}%")
        tooltip_points.append(f"• Battery Health: {capacity}%")

        # Add power profile if available
        power_profile = self._battery.power_profile
        if power_profile:
            # Add icon based on profile
            if power_profile == "power-saver":
                profile_icon = icons.power_saving
            elif power_profile == "performance":
                profile_icon = icons.power_performance
            else:  # balanced
                profile_icon = icons.power_balanced
            tooltip_points.append(f"• Profile: {profile_icon} {power_profile}")

        # Add temperature if available
        temp = self._battery.temperature
        if temp != "N/A":
            tooltip_points.append(f"• Temperature: {temp}")

        # Add time estimates
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
        """Update battery status and UI"""
        if not self._battery.is_present:
            self.set_visible(False)
            return True

        percentage = self._battery.percentage
        state = self._battery.state
        charging = state in ["CHARGING", "FULLY_CHARGED"]
        power_profile = self._battery.power_profile

        # Update circle progress
        self.circle.set_value(percentage / 100.0)

        # Only show percentage label if not at 100%
        if percentage < 100:
            self.level.set_label(f"{int(percentage)}%")
            self.level.set_visible(True)
        else:
            self.level.set_visible(False)

        # Apply alert styling if battery is low AND not charging
        if percentage <= 15 and not charging:
            self.icon.add_style_class("alert")
            self.circle.add_style_class("alert")
        else:
            self.icon.remove_style_class("alert")
            self.circle.remove_style_class("alert")

        # Update icon based on battery state if not in power profile mode
        if not power_profile:
            if state == "FULLY_CHARGED":
                self.icon.set_markup(icons.battery)
            elif state == "CHARGING":
                self.icon.set_markup(icons.charging)
            elif percentage <= 15 and state == "DISCHARGING":
                self.icon.set_markup(icons.alert)
            elif state == "DISCHARGING":
                self.icon.set_markup(icons.discharging)
            else:
                self.icon.set_markup(icons.battery)

        self.set_visible(True)
        return True
