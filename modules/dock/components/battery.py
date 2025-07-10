from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from gi.repository import Gdk, GLib

import config.data as data
import utils.icons as icons
from services.battery import Battery as BatteryService
from utils.wayland import WaylandWindow as Window


class BatteryPopup(Window):
    """Popup window that shows battery information and power profile switcher"""

    def __init__(self, dock_component=None, **kwargs):
        # Get dock position for proper anchoring
        dock_position = data.DOCK_POSITION
        popup_anchor = self._get_popup_anchor(dock_position)
        margin = self._get_popup_margin(dock_position)

        super().__init__(
            name="battery-popup",
            layer="top",
            anchor=popup_anchor,
            margin=margin,
            exclusive=False,
            keyboard_mode="on-demand",
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.dock_component = dock_component

        # Get transition type based on dock position
        transition_type = self._get_revealer_transition(dock_position)

        # Create main content box
        self.content_box = Box(
            name="battery-popup-content",
            orientation="v",
            spacing=12,
            style_classes=["battery-popup"],
        )

        # Create battery info section
        self.info_box = Box(
            name="battery-info",
            orientation="v",
            spacing=6,
        )

        # Create power profile switcher section
        self.profile_box = Box(
            name="power-profile-switcher",
            orientation="h",
            spacing=8,
            style_classes=["power-profiles"],
        )

        # Create power profile buttons
        # We'll determine the actual profile names dynamically
        self.power_saver_btn = Button(
            name="power-saver-btn",
            child=Label(markup=icons.power_saving,name="bat-icon"),
            on_clicked=lambda *_: self._set_power_profile_by_type("power-saver"),
            style_classes=["power-profile-btn"],
        )

        self.balanced_btn = Button(
            name="balanced-btn",
            child=Label(markup=icons.power_balanced,name="bat-icon"),
            on_clicked=lambda *_: self._set_power_profile_by_type("balanced"),
            style_classes=["power-profile-btn"],
        )

        self.performance_btn = Button(
            name="performance-btn",
            child=Label(markup=icons.power_performance,name="bat-icon"),
            on_clicked=lambda *_: self._set_power_profile_by_type("performance"),
            style_classes=["power-profile-btn"],
        )

        # Add profile buttons to profile box
        self.profile_box.add(self.power_saver_btn)
        self.profile_box.add(self.balanced_btn)
        self.profile_box.add(self.performance_btn)

        # Add sections to content box
        self.content_box.add(self.info_box)
        self.content_box.add(self.profile_box)

        # Create revealer for slide transition
        self.revealer = Revealer(
            transition_type=transition_type,
            transition_duration=300,
            child=self.content_box,
            reveal_child=False,
        )

        self.add(self.revealer)

        # Connect to escape key to close
        self.connect("key-press-event", self.on_key_press)
        self.connect("button-press-event", self.on_button_press)
        self.connect("enter-notify-event", self.on_enter_notify)
        self.connect("leave-notify-event", self.on_leave_notify)
        self.set_can_focus(True)

    def _set_power_profile_by_type(self, profile_type):
        """Set power profile by type (maps to actual profile names)"""
        if self.dock_component and hasattr(self.dock_component, '_battery'):
            try:
                battery_service = self.dock_component._battery

                # Check if profile proxy is available
                if not hasattr(battery_service, '_profile_proxy') or not battery_service._profile_proxy:
                    print("Power profile proxy not available")
                    return

                # Get available profiles
                profiles = battery_service._profile_proxy.Profiles
                available_profiles = []
                for p in profiles:
                    if isinstance(p, dict) and "Profile" in p:
                        available_profiles.append(p["Profile"])
                    elif hasattr(p, "Profile"):
                        available_profiles.append(p.Profile)
                    elif isinstance(p, str):
                        available_profiles.append(p)

                # Map profile types to actual profile names
                profile_mapping = {
                    "power-saver": ["power-saver", "powersave", "power_saver"],
                    "balanced": ["balanced", "balance"],
                    "performance": ["performance", "performance-mode"]
                }

                # Find the actual profile name
                actual_profile = None
                if profile_type in profile_mapping:
                    for candidate in profile_mapping[profile_type]:
                        if candidate in available_profiles:
                            actual_profile = candidate
                            break

                if actual_profile:
                    battery_service._profile_proxy.ActiveProfile = actual_profile
                    self.update_profile_buttons()
                    self.dock_component.update_battery()
                    print(f"Successfully set power profile to {actual_profile}")
                else:
                    print(f"No matching profile found for type '{profile_type}' in available profiles: {available_profiles}")

            except Exception as e:
                print(f"Error setting power profile: {e}")

    def _set_power_profile(self, profile):
        """Set the power profile"""
        if self.dock_component and hasattr(self.dock_component, '_battery'):
            try:
                battery_service = self.dock_component._battery

                # Check if profile proxy is available
                if not hasattr(battery_service, '_profile_proxy') or not battery_service._profile_proxy:
                    print("Power profile proxy not available")
                    return

                # Get available profiles for debugging
                try:
                    profiles = battery_service._profile_proxy.Profiles
                    available_profiles = []
                    for p in profiles:
                        if isinstance(p, dict) and "Profile" in p:
                            available_profiles.append(p["Profile"])
                        elif hasattr(p, "Profile"):
                            available_profiles.append(p.Profile)
                        elif isinstance(p, str):
                            available_profiles.append(p)

                    print(f"Available profiles: {available_profiles}")
                    print(f"Trying to set profile: {profile}")

                    # Try to set the profile
                    if profile in available_profiles:
                        battery_service._profile_proxy.ActiveProfile = profile
                        self.update_profile_buttons()
                        # Update the dock component as well
                        self.dock_component.update_battery()
                        print(f"Successfully set power profile to {profile}")
                    else:
                        print(f"Profile '{profile}' not found in available profiles: {available_profiles}")

                except Exception as e:
                    print(f"Error accessing profiles: {e}")

            except Exception as e:
                print(f"Error setting power profile: {e}")

    def update_content(self):
        """Update the popup content with current battery information"""
        if not self.dock_component:
            return

        # Clear existing info
        for child in self.info_box.get_children():
            self.info_box.remove(child)

        battery = self.dock_component._battery

        # Battery percentage and state
        percentage_label = Label(
            name="battery-percentage",
            label=f"{battery.percentage}%",
            style_classes=["battery-percentage"],
        )

        state_label = Label(
            name="battery-state",
            label=battery.state,
            style_classes=["battery-state"],
        )

        # Create percentage and state row
        percentage_state_box = Box(
            name="percentage-state-box",
            orientation="h",
            spacing=8,
            children=[percentage_label, state_label],
        )

        # Battery capacity (health)
        capacity_box = Box(
            name="capacity-box",
            orientation="h",
            spacing=8,
            children=[
                Label(label="Battery Health:", style_classes=["battery-label"]),
                Label(label=battery.capacity, style_classes=["battery-value"]),
            ],
        )

        # Time information based on charging state
        time_box = None
        if battery.state == "CHARGING":
            time_to_full = battery.time_to_full
            if time_to_full and time_to_full != "0m":
                time_box = Box(
                    name="time-box",
                    orientation="h",
                    spacing=8,
                    children=[
                        Label(label="Time to full:", style_classes=["battery-label"]),
                        Label(label=time_to_full, style_classes=["battery-value"]),
                    ],
                )
        else:  # DISCHARGING or other states
            time_to_empty = battery.time_to_empty
            if time_to_empty and time_to_empty != "0m":
                time_box = Box(
                    name="time-box",
                    orientation="h",
                    spacing=8,
                    children=[
                        Label(label="Time remaining:", style_classes=["battery-label"]),
                        Label(label=time_to_empty, style_classes=["battery-value"]),
                    ],
                )

        # Power profile information
        profile_label_box = Box(
            name="profile-label-box",
            orientation="h",
            spacing=8,
            children=[
                Label(label="Power Profile:", style_classes=["battery-label"]),
                Label(label=battery.power_profile.title(), style_classes=["battery-value"]),
            ],
        )

        # Add all info to the info box
        self.info_box.add(percentage_state_box)
        self.info_box.add(capacity_box)
        if time_box:
            self.info_box.add(time_box)
        self.info_box.add(profile_label_box)

        # Update profile button states
        self.update_profile_buttons()

    def update_profile_buttons(self):
        """Update the active state of profile buttons"""
        if not self.dock_component or not hasattr(self.dock_component, '_battery'):
            return

        current_profile = self.dock_component._battery.power_profile

        # Remove active class from all buttons
        self.power_saver_btn.remove_style_class("active")
        self.balanced_btn.remove_style_class("active")
        self.performance_btn.remove_style_class("active")

        # Add active class to current profile button
        if current_profile == "power-saver":
            self.power_saver_btn.add_style_class("active")
        elif current_profile == "performance":
            self.performance_btn.add_style_class("active")
        else:  # balanced or default
            self.balanced_btn.add_style_class("active")

    def on_key_press(self, widget, event):
        """Handle key press events"""
        if event.keyval == Gdk.KEY_Escape:
            self.hide_popup()
            return True
        return False

    def show_popup(self):
        """Show the battery popup"""
        self.update_content()
        self.set_visible(True)
        self.show_all()
        # Use GLib.idle_add to ensure the window is shown before revealing
        GLib.idle_add(self._reveal_popup)

    def _reveal_popup(self):
        """Reveal the popup after window is shown"""
        self.revealer.set_reveal_child(True)
        self.grab_focus()
        return False  # Don't repeat

    def _get_popup_anchor(self, dock_position):
        """Get popup anchor based on dock position"""
        anchor_map = {
            "Top": "top",
            "Bottom": "bottom right",
            "Left": "left",
            "Right": "right",
        }
        return anchor_map.get(dock_position, "bottom")

    def _get_popup_margin(self, dock_position):
        """Get popup margin based on dock position"""
        margin_map = {
            "Top": "60px 10px 10px 10px",
            "Bottom": "10px 650px 60px 10px",
            "Left": "10px 10px 10px 60px",
            "Right": "10px 60px 10px 10px",
        }
        return margin_map.get(dock_position, "10px 10px 60px 10px")

    def _get_revealer_transition(self, dock_position):
        """Get revealer transition type based on dock position"""
        transition_map = {
            "Top": "slide-down",
            "Bottom": "slide-up",
            "Left": "slide-right",
            "Right": "slide-left",
        }
        return transition_map.get(dock_position, "slide-up")

    def on_button_press(self, widget, event):
        """Handle button press events"""
        return False

    def on_enter_notify(self, widget, event):
        """Handle mouse entering popup"""
        # Cancel any pending hide from dock component
        if self.dock_component and hasattr(self.dock_component, '_hover_timeout'):
            if self.dock_component._hover_timeout:
                GLib.source_remove(self.dock_component._hover_timeout)
                self.dock_component._hover_timeout = None
        return False

    def on_leave_notify(self, widget, event):
        """Handle mouse leaving popup"""
        # Hide popup when mouse leaves
        self.hide_popup()
        return False

    def hide_popup(self):
        """Hide the battery popup"""
        self.revealer.set_reveal_child(False)
        # Hide window after transition completes
        GLib.timeout_add(350, lambda: self.set_visible(False))


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

        # Create event box for hover detection
        self.event_box = EventBox(
            events=["enter-notify", "leave-notify"],
            child=self.circle_button,
        )

        # Connect hover events
        self.event_box.connect("enter-notify-event", self.on_enter_notify)
        self.event_box.connect("leave-notify-event", self.on_leave_notify)
        self.event_box.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)

        self.level = Label(
            name="battery-level",
            style_classes="battery",
            label="0%",
        )

        self.battery_box = Box(
            name="battery-box",
            orientation=orientation,
            spacing=0,
            children=[self.event_box],
        )

        if not data.VERTICAL:
            self.battery_box.add(self.level)

        self.add(self.battery_box)

        self.popup = None

        # Hover timeout for debouncing
        self._hover_timeout = None

        # Connect to destroy signal for cleanup
        self.connect("destroy", self.on_destroy)

        GLib.idle_add(self.update_battery)

    def on_destroy(self, widget):
        """Clean up popup when component is destroyed"""
        try:
            # Remove hover timeout
            if hasattr(self, "_hover_timeout") and self._hover_timeout:
                GLib.source_remove(self._hover_timeout)
                self._hover_timeout = None

            # Clean up popup
            if hasattr(self, 'popup') and self.popup:
                try:
                    self.popup.destroy()
                    self.popup = None
                except Exception:
                    pass

        except Exception:
            pass

    def on_enter_notify(self, widget, event):
        """Handle mouse entering the battery component"""
        # Cancel any pending hover timeout
        if self._hover_timeout:
            GLib.source_remove(self._hover_timeout)
            self._hover_timeout = None

        # Show popup immediately on hover
        if not self.popup or not self.popup.get_visible():
            # Create popup on-demand if it doesn't exist
            if not self.popup:
                self.popup = BatteryPopup(dock_component=self)
            self.popup.show_popup()
        return False

    def on_leave_notify(self, widget, event):
        """Handle mouse leaving the battery component"""
        # Hide popup with a small delay to prevent flickering
        self._hover_timeout = GLib.timeout_add(100, self._hide_popup_delayed)
        return False

    def _hide_popup_delayed(self):
        """Hide popup after delay"""
        if self.popup and self.popup.get_visible():
            self.popup.hide_popup()
        self._hover_timeout = None
        return False  # Don't repeat timeout
    
    def update_battery(self, *args):
        if not self._battery.is_present:
            self.set_visible(False)
            return True

        percentage = self._battery.percentage
        state = self._battery.state
        charging = state in ["CHARGING", "FULLY_CHARGED"]

        self.circle.set_value(percentage / 100.0)

        if percentage < 100:
            self.level.set_label(f"{int(percentage)}%")
            self.level.set_visible(True)
        else:
            self.level.set_visible(False)

   
        self.icon.remove_style_class("discharging")
        self.icon.remove_style_class("discharging-low")
        self.icon.remove_style_class("discharging-critical")

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

        # Only show if enabled in configuration
        if data.DOCK_COMPONENTS_VISIBILITY.get("battery", True):
            self.set_visible(True)
        else:
            self.set_visible(False)
        return True
