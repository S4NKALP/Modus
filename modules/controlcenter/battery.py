from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.svg import Svg
from fabric.widgets.image import Image
from services.battery import Battery
import subprocess
import os


class PowerProfileButton(Button):
    def __init__(self, profile_name: str, display_name: str, battery_service: Battery, parent, **kwargs):
        self.profile_name = profile_name
        self.battery_service = battery_service
        self.parent = parent

        # Get symbolic icon for profile
        profile_icons = {
            "power-saver": "power-profile-power-saver-symbolic",
            "powersave": "power-profile-power-saver-symbolic",
            "power_saver": "power-profile-power-saver-symbolic",
            "balanced": "power-profile-balanced-symbolic",
            "balance": "power-profile-balanced-symbolic",
            "performance": "power-profile-performance-symbolic",
            "performance-mode": "power-profile-performance-symbolic"
        }

        icon_name = profile_icons.get(profile_name, "preferences-system-symbolic")

        # Create symbolic icon
        from fabric.widgets.image import Image
        self.profile_icon = Image(
            icon_name=icon_name,
            size=20,
            style_classes="battery-profile-icon"
        )

        self.profile_label = Label(
            label=display_name,
            style_classes="battery-profile-label"
        )

        # Create vertical layout for icon and label
        content = Box(
            orientation="vertical",
            spacing=2,
            children=[self.profile_icon, self.profile_label],
            h_align="center"
        )
        
        super().__init__(
            child=content,
            on_clicked=self.on_clicked,
            style_classes="battery-profile-button",
            **kwargs
        )
        
        # Update initial state
        self.update_state()
    
    def on_clicked(self, *args):
        """Handle profile selection"""
        success = self.battery_service.change_power_profile(self.profile_name)
        if success:
            # Update all profile buttons in parent
            self.parent.update_profile_buttons()
    
    def update_state(self):
        """Update the visual state based on current active profile"""
        is_active = self.battery_service.power_profile == self.profile_name
        
        if is_active:
            self.add_style_class("active")
        else:
            self.remove_style_class("active")


class GameModeButton(Button):
    def __init__(self, **kwargs):
        self.script_path = get_relative_path("../../scripts/gamemode.sh")
        self.gamemode_active = self.check_gamemode_status()

        # Create icon for gamemode
        self.gamemode_icon = Image(
            icon_name="applications-games-symbolic" if self.gamemode_active else "applications-games-symbolic",
            size=20,
            style_classes="battery-gamemode-icon"
        )

        self.gamemode_label = Label(
            label="Game Mode",
            style_classes="battery-gamemode-label"
        )

        # Create vertical layout for icon and label
        content = Box(
            orientation="vertical",
            spacing=2,
            children=[self.gamemode_icon, self.gamemode_label],
            h_align="center"
        )

        super().__init__(
            child=content,
            on_clicked=self.toggle_gamemode,
            style_classes="battery-gamemode-button",
            **kwargs
        )

        # Update initial state
        self.update_state()

    def check_gamemode_status(self):
        """Check if gamemode is currently active"""
        try:
            result = subprocess.run(
                [self.script_path, "check"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() == "t"
        except Exception:
            return False

    def toggle_gamemode(self, *args):
        """Toggle gamemode state"""
        try:
            # Make script executable if it isn't
            os.chmod(self.script_path, 0o755)

            # Run the toggle script
            subprocess.run([self.script_path], timeout=10)

            # Update state after toggle
            self.gamemode_active = self.check_gamemode_status()
            self.update_state()
        except Exception as e:
            print(f"Failed to toggle gamemode: {e}")

    def update_state(self):
        """Update the visual state based on gamemode status"""
        if self.gamemode_active:
            self.add_style_class("active")
            self.gamemode_icon.set_property("style-classes", "battery-gamemode-icon active")
        else:
            self.remove_style_class("active")
            self.gamemode_icon.set_property("style-classes", "battery-gamemode-icon")


class BatteryControl(Box):
    def __init__(self, parent, **kwargs):
        super().__init__(
            spacing=0,
            orientation="vertical",
            name="control-center-widgets",
            **kwargs,
        )
        self.set_size_request(300, -1)

        self.parent = parent
        self.battery_service = Battery()
        self.profile_buttons = []

        # Battery information widget in control center style
        self.battery_info_widget = Box(
            name="battery-info-widget",
            orientation="vertical",
            style_classes="menu",
            h_expand=True,
            children=[
                Label(label="Battery", style_classes="title", h_align="start"),
            ]
        )

        # Battery status labels
        self.battery_percentage = Label(
            label="100%",
            style_classes="battery-info-item",
            h_align="start"
        )

        self.battery_state = Label(
            label="Fully Charged",
            style_classes="battery-info-item",
            h_align="start"
        )

        self.battery_capacity = Label(
            label="",
            style_classes="battery-info-item",
            h_align="start"
        )

        self.battery_time_to_full = Label(
            label="",
            style_classes="battery-info-item",
            h_align="start",
            visible=False
        )

        self.battery_time_to_empty = Label(
            label="",
            style_classes="battery-info-item",
            h_align="start",
            visible=False
        )

        self.battery_temperature = Label(
            label="",
            style_classes="battery-info-item",
            h_align="start"
        )

        # Add battery info to widget
        self.battery_info_widget.add(self.battery_percentage)
        self.battery_info_widget.add(self.battery_state)
        self.battery_info_widget.add(self.battery_capacity)
        self.battery_info_widget.add(self.battery_time_to_full)
        self.battery_info_widget.add(self.battery_time_to_empty)
        self.battery_info_widget.add(self.battery_temperature)

        # Power profiles widget in control center style
        self.profiles_widget = Box(
            name="power-profiles-widget",
            orientation="vertical",
            style_classes="menu",
            h_expand=True,
            children=[
                Label(label="Power Profiles", style_classes="title", h_align="start"),
            ]
        )
        
        # Power profiles container
        self.profiles_container = Box(
            orientation="horizontal",
            spacing=8,
            style_classes="battery-profiles-container",
            h_align="center"
        )

        self.profiles_widget.add(self.profiles_container)

        # Game mode widget in control center style
        self.gamemode_widget = Box(
            name="gamemode-widget",
            orientation="vertical",
            style_classes="menu",
            h_expand=True,
            children=[
                Label(label="Game Mode", style_classes="title", h_align="start"),
            ]
        )

        # Add gamemode button
        self.gamemode_button = GameModeButton()
        gamemode_container = Box(
            orientation="horizontal",
            spacing=8,
            style_classes="battery-gamemode-container",
            h_align="center",
            children=[self.gamemode_button]
        )
        self.gamemode_widget.add(gamemode_container)

        # Add all widgets to main container
        self.add(self.battery_info_widget)
        self.add(self.profiles_widget)
        self.add(self.gamemode_widget)

        # Connect to battery service signals
        self.battery_service.connect("changed", self.on_battery_changed)
        self.battery_service.connect("profile_changed", self.on_profile_changed)

        # Initialize display
        self.update_battery_info()
        self.create_profile_buttons()
    

    
    def create_profile_buttons(self):
        """Create buttons for available power profiles"""
        # Clear existing buttons
        for button in self.profile_buttons:
            button.destroy()
        self.profile_buttons.clear()
        
        # Get available profiles
        available_profiles = self.battery_service.available_profiles
        
        if not available_profiles:
            no_profiles_label = Label(
                label="No power profiles available",
                style_classes="battery-no-profiles",
                h_align="center"
            )
            self.profiles_container.add(no_profiles_label)
            return
        
        # Create button for each profile
        for profile in available_profiles:
            display_name = Battery.get_profile_display_name(profile)
            button = PowerProfileButton(
                profile_name=profile,
                display_name=display_name,
                battery_service=self.battery_service,
                parent=self
            )
            self.profile_buttons.append(button)
            self.profiles_container.add(button)
    
    def update_profile_buttons(self):
        """Update the state of all profile buttons"""
        for button in self.profile_buttons:
            button.update_state()

    def update_battery_info(self):
        """Update battery information display"""
        if not self.battery_service.is_present:
            self.battery_percentage.set_label("No Battery")
            self.battery_state.set_label("Not Present")
            self.battery_capacity.set_label("")
            self.battery_time_to_full.set_visible(False)
            self.battery_time_to_empty.set_visible(False)
            self.battery_temperature.set_label("")
            return

        # Update percentage
        percentage = self.battery_service.percentage
        self.battery_percentage.set_label(f"Charge: {percentage}%")

        # Update state
        state = self.battery_service.state
        state_text = state.replace("_", " ").title()
        self.battery_state.set_label(f"Status: {state_text}")

        # Update capacity
        capacity = getattr(self.battery_service, 'capacity', None)
        if capacity is not None:
            try:
                # Try to convert to float if it's a string
                capacity_value = float(capacity)
                self.battery_capacity.set_label(f"Capacity: {capacity_value:.1f} Wh")
            except (ValueError, TypeError):
                # If conversion fails, display as string
                self.battery_capacity.set_label(f"Capacity: {capacity}")
        else:
            self.battery_capacity.set_label("Capacity: N/A")

        # Update time to full
        time_to_full = self.battery_service.time_to_full
        if time_to_full != "N/A" and state == "CHARGING":
            self.battery_time_to_full.set_label(f"Time to full: {time_to_full}")
            self.battery_time_to_full.set_visible(True)
        else:
            self.battery_time_to_full.set_visible(False)

        # Update time to empty
        time_to_empty = self.battery_service.time_to_empty
        if time_to_empty != "N/A" and state == "DISCHARGING":
            self.battery_time_to_empty.set_label(f"Time remaining: {time_to_empty}")
            self.battery_time_to_empty.set_visible(True)
        else:
            self.battery_time_to_empty.set_visible(False)

        # Update temperature
        temperature = getattr(self.battery_service, 'temperature', None)
        if temperature is not None:
            try:
                # Try to convert to float and convert from tenths of degrees Celsius to Celsius
                temp_value = float(temperature) / 10.0
                self.battery_temperature.set_label(f"Temperature: {temp_value:.1f}°C")
            except (ValueError, TypeError):
                # If conversion fails, display as string
                self.battery_temperature.set_label(f"Temperature: {temperature}")
        else:
            self.battery_temperature.set_label("Temperature: N/A")

    def on_battery_changed(self, *args):
        """Handle battery service changes"""
        self.update_battery_info()

    def on_profile_changed(self, service, new_profile):
        """Handle power profile changes"""
        self.update_profile_buttons()
