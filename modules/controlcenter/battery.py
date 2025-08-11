import subprocess

from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.separator import Separator
from fabric.widgets.svg import Svg
from gi.repository import GLib

from services.battery import Battery


class EnergyModeButton(Box):
    def __init__(
        self,
        profile_name: str,
        display_name: str,
        icon_name: str,
        battery_service: Battery,
        parent,
        **kwargs,
    ):
        super().__init__(name="energy-mode-button", **kwargs)
        self.profile_name = profile_name
        self.battery_service = battery_service
        self.parent = parent

        self.mode_icon_svg = Svg(
            # icon_name=f"battery-{icon_name}-symbolic",
            svg_file=get_relative_path(
                f"../../config/assets/icons/power_modes/battery-{icon_name}.svg"
            ),
            size=24,
        )
        self.mode_icon = Box(
            children=[self.mode_icon_svg],
            name="energy-mode-icon",
            style_classes="battery-profile-icon",
        )

        self.mode_label = Label(
            label=display_name,
            style_classes="battery-power-mode",
            h_align="start",
            h_expand=True,
        )

        start_box = Box(
            orientation="horizontal",
            spacing=4,
            children=[self.mode_icon, self.mode_label],
        )

        self.button = Button(
            child=start_box,
            h_expand=True,
            name="energy-mode-button-clickable",
            on_clicked=self.on_clicked,
            style_classes="battery-profile-button",
        )

        self.children = [self.button]
        self.update_state()

    def on_clicked(self, *args):
        success = self.battery_service.change_power_profile(self.profile_name)
        if success:
            # Update all profile buttons in parent
            self.parent.update_energy_mode_buttons()

        # Reset icon state after short delay
        GLib.timeout_add(300, lambda: self._reset_icon_state())

    def _reset_icon_state(self):
        return False  # Remove timeout

    def update_state(self):
        is_active = self.battery_service.power_profile == self.profile_name
        if is_active:
            self.mode_icon.add_style_class("connected")
        else:
            self.mode_icon.remove_style_class("connected")


class GameModeButton(Box):
    def __init__(self, parent, **kwargs):
        super().__init__(name="energy-mode-button", h_expand=True, **kwargs)
        self.parent = parent

        self.game_icon = Image(
            icon_name="applications-games-symbolic",
            size=16,
            name="game-mode-icon",
            style_classes="battery-gamemode-icon",
        )

        self.game_label = Label(
            label="Game Mode",
            style_classes="gamemode-button",
            h_align="start",
            h_expand=True,
        )

        start_box = Box(
            orientation="horizontal",
            spacing=3,
            children=[self.game_icon, self.game_label],
        )

        self.button = Button(
            child=start_box,
            name="game-mode-button-clickable",
            on_clicked=self.on_clicked,
            h_expand=True,
            style_classes="battery-gamemode-button",
        )

        self.children = [self.button]
        self.update_state()

    def on_clicked(self, *args):
        try:
            script_path = get_relative_path("../../scripts/gamemode.sh")
            subprocess.run([script_path], check=False)

            GLib.timeout_add(500, lambda: self.update_state())
        except Exception as e:
            print(f"Failed to toggle game mode: {e}")

        GLib.timeout_add(300, lambda: self._reset_icon_state())

    def _reset_icon_state(self):
        return False  # Remove timeout

    def update_state(self):
        try:
            script_path = get_relative_path("../../scripts/gamemode.sh")
            result = subprocess.run(
                [script_path, "check"], capture_output=True, text=True, check=False
            )
            is_active = result.stdout.strip() == "t"

            if is_active:
                self.game_icon.add_style_class("connected")
            else:
                self.game_icon.remove_style_class("connected")
        except Exception as e:
            print(f"Failed to check game mode status: {e}")
            # Default to inactive state on error
            self.game_icon.remove_style_class("connected")

        return False  # Remove timeout if called from GLib.timeout_add


class BatteryControl(Box):
    def __init__(self, parent, **kwargs):
        super().__init__(
            spacing=12,
            orientation="vertical",
            name="control-center-widgets",
            **kwargs,
        )
        self.set_size_request(374, -1)

        self.parent = parent
        self.battery_service = Battery()
        self.energy_mode_buttons = []

        self.battery_widget = Box(
            name="battery-widget",
            orientation="vertical",
            style_classes="battery-status-section",
            h_expand=True,
            spacing=8,
        )

        self.battery_title = Label(
            label="Battery", style_classes="battery-main-title", h_align="start"
        )

        self.battery_percentage_label = Label(
            label="80%", style_classes="battery-percentage", h_align="end"
        )

        self.battery_header = CenterBox(
            start_children=self.battery_title,
            end_children=self.battery_percentage_label,
            name="battery-header",
        )

        self.power_source_label = Label(
            label="Power Source: Power Adapter",
            style_classes="battery-power-source",
            h_align="start",
        )

        self.charging_time_label = Label(
            label="1h 4m until fully charged",
            style_classes="battery-power-source",
            h_align="start",
        )

        self.energy_mode_section = Box(
            orientation="vertical", spacing=8, name="energy-mode-section"
        )

        self.energy_mode_title = Label(
            label="Energy Mode", style_classes="battery-section-title", h_align="start"
        )

        self.energy_modes_container = Box(
            orientation="vertical", spacing=4, name="energy-modes-container"
        )

        self.game_mode_section = Box(
            orientation="vertical", spacing=8, name="game-mode-section"
        )

        self.game_mode_title = Label(
            label="Game Mode", style_classes="battery-section-title", h_align="start"
        )

        self.game_mode_container = Box(
            orientation="vertical", spacing=4, name="game-mode-container"
        )

        self.battery_settings_button = Button(
            v_align="center",
            child=Label(
                label="Battery Settings",
                h_align="start",
            ),
            style_classes="battery-settings-button",
            on_clicked=self.open_battery_settings,
        )

        self.battery_widget.add(self.battery_header)
        self.battery_widget.add(self.power_source_label)
        self.battery_widget.add(self.charging_time_label)

        separator1 = Separator(orientation="h", name="separator")
        self.battery_widget.add(separator1)

        self.energy_mode_section.add(self.energy_mode_title)
        self.energy_mode_section.add(self.energy_modes_container)
        self.battery_widget.add(self.energy_mode_section)

        separator2 = Separator(orientation="h", name="separator")
        self.battery_widget.add(separator2)

        self.game_mode_section.add(self.game_mode_title)
        self.game_mode_section.add(self.game_mode_container)
        self.battery_widget.add(self.game_mode_section)

        separator3 = Separator(orientation="h", name="separator")
        self.battery_widget.add(separator3)

        self.battery_widget.add(self.battery_settings_button)

        self.add(self.battery_widget)

        self.battery_service.connect("changed", self.on_battery_changed)
        self.battery_service.connect("profile_changed", self.on_profile_changed)

        # Initialize display
        self.update_battery_info()
        self.create_energy_mode_buttons()
        self.create_game_mode_button()

    def open_battery_settings(self, *args):
        # TODO: Implement to open Battery Settings
        pass

    def create_energy_mode_buttons(self):
        # Clear existing buttons
        for button in self.energy_mode_buttons:
            button.destroy()
        self.energy_mode_buttons.clear()

        # Get available profiles
        available_profiles = self.battery_service.available_profiles

        if not available_profiles:
            no_profiles_label = Label(
                label="No energy modes available",
                style_classes="battery-no-profiles",
                h_align="start",
            )
            self.energy_modes_container.add(no_profiles_label)
            return

        # Define energy mode mappings with proper icon names
        energy_mode_config = {
            "balanced": {"display": "Automatic", "icon": "balanced"},
            "power-saver": {"display": "Low Power", "icon": "power"},
            "powersave": {"display": "Low Power", "icon": "power"},
            "performance": {"display": "High Power", "icon": "performance"},
        }

        # Define the desired order for energy modes
        desired_order = ["balanced", "power-saver", "powersave", "performance"]

        # Create ordered list of available profiles
        ordered_profiles = []
        for profile_name in desired_order:
            if profile_name in available_profiles:
                ordered_profiles.append(profile_name)

        # Add any remaining profiles not in the desired order
        for profile in available_profiles:
            if profile not in ordered_profiles:
                ordered_profiles.append(profile)

        # Create button for each available profile in the specified order
        for profile in ordered_profiles:
            config = energy_mode_config.get(
                profile, {"display": profile.title(), "icon": "good"}
            )

            button = EnergyModeButton(
                profile_name=profile,
                display_name=config["display"],
                icon_name=config["icon"],
                battery_service=self.battery_service,
                parent=self,
            )
            self.energy_mode_buttons.append(button)
            self.energy_modes_container.add(button)

    def update_energy_mode_buttons(self):
        for button in self.energy_mode_buttons:
            button.update_state()

    def create_game_mode_button(self):
        # Clear existing game mode button if any
        for child in list(self.game_mode_container.get_children()):
            child.destroy()

        # Create game mode button
        self.game_mode_button = GameModeButton(parent=self)
        self.game_mode_container.add(self.game_mode_button)

    def update_battery_info(self):
        if not self.battery_service.is_present:
            self.battery_percentage_label.set_label("No Battery")
            self.power_source_label.set_label("Power Source: Not Present")
            self.charging_time_label.set_label("")
            return

        # Update percentage in header
        percentage = self.battery_service.percentage
        self.battery_percentage_label.set_label(f"{percentage}%")

        # Update power source and charging info
        state = self.battery_service.state

        if state in ["CHARGING", "PENDING_CHARGE"]:
            self.power_source_label.set_label("Power Source: Power Adapter")
            time_to_full = self.battery_service.time_to_full
            if time_to_full != "N/A" and time_to_full != "0m":
                self.charging_time_label.set_label(
                    f"{time_to_full} until fully charged"
                )
            else:
                self.charging_time_label.set_label("Charging...")
        elif state == "FULLY_CHARGED":
            self.power_source_label.set_label("Power Source: Power Adapter")
            self.charging_time_label.set_label("Fully Charged")
        elif state in ["DISCHARGING", "PENDING_DISCHARGE"]:
            self.power_source_label.set_label("Power Source: Battery")
            time_to_empty = self.battery_service.time_to_empty
            if time_to_empty != "N/A" and not time_to_empty.startswith(
                "4553h"
            ):  # Filter out unrealistic times
                self.charging_time_label.set_label(f"{time_to_empty} remaining")
            else:
                self.charging_time_label.set_label("On Battery Power")
        elif state == "EMPTY":
            self.power_source_label.set_label("Power Source: Battery")
            self.charging_time_label.set_label("Battery Empty")
        else:
            self.power_source_label.set_label("Power Source: Unknown")
            self.charging_time_label.set_label("")

    def on_battery_changed(self, *args):
        self.update_battery_info()

    def on_profile_changed(self, service, new_profile):
        self.update_energy_mode_buttons()
