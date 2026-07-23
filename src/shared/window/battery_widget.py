from fabric.utils import GLib, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.separator import Separator

from services.battery import Battery
from services.gamemode import GameModeService
from shared.capture import CaptureNotifier
from shared.widgets.flat_scale import FlatScale
from utils.functions import clear_children, format_duration
from utils.gtk_utils import svg_file

_charge_notifier = CaptureNotifier(app_name="Modus")


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

        self.mode_icon_svg = svg_file(f"power_modes/battery-{icon_name}.svg", size=24)

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
        success = False
        if hasattr(self.battery_service, "set_power_profile"):
            success = self.battery_service.set_power_profile(self.profile_name)
        if success:
            # Update all profile buttons in parent
            self.parent.update_energy_mode_buttons()

        # Reset icon state after short delay
        GLib.timeout_add(300, lambda: self._reset_icon_state())

    def _reset_icon_state(self):
        return False  # Remove timeout

    def update_state(self):
        current_profile = None
        if hasattr(self.battery_service, "get_power_profile"):
            current_profile = self.battery_service.get_power_profile()
        is_active = current_profile == self.profile_name
        if is_active:
            self.mode_icon.add_style_class("connected")
        else:
            self.mode_icon.remove_style_class("connected")


class ChargeLimitButton(Box):
    def __init__(self, battery_service: Battery, parent, **kwargs):
        super().__init__(name="energy-mode-button", h_expand=True, **kwargs)
        self.battery_service = battery_service
        self.parent = parent
        self._has_threshold = (
            battery_service.charge_limit is not None
            and battery_service.charge_limit.sysfs_path is not None
        )

        self.charge_icon_svg = svg_file("zap.svg", size=16)

        self.charge_icon = Box(
            children=[self.charge_icon_svg],
            name="charge-limit-icon",
        )

        self.charge_label = Label(
            label="Charge Limit",
            style_classes="charge-limit-button",
            h_align="start",
            h_expand=True,
        )

        start_box = Box(
            orientation="horizontal",
            spacing=3,
            children=[self.charge_icon, self.charge_label],
        )

        self.button = Button(
            child=start_box,
            name="charge-limit-button-clickable",
            on_clicked=self.on_clicked,
            h_expand=True,
        )

        children = [self.button]

        if self._has_threshold:
            self.threshold_label = Label(
                label="80%",
                style_classes="charge-threshold-value",
                h_align="end",
            )

            self.slider = FlatScale(
                value=80.0,
                min_value=20.0,
                max_value=100.0,
                step=5.0,
                draw_value=True,
                orientation="horizontal",
                on_value_changed=self._on_slider_changed,
                name="charge-threshold-slider",
                style_classes="charge-threshold-flat-scale",
                h_expand=True,
            )

            self.slider_box = Box(
                orientation="horizontal",
                spacing=8,
                children=[self.slider, self.threshold_label],
            )

            children.append(self.slider_box)

        self.children = children
        self.update_state()

    def on_clicked(self, *args):
        self.battery_service.toggle_charge_limit()
        self.update_state()
        cl = self.battery_service.charge_limit
        if cl is not None:
            state = "enabled" if cl.enabled else "disabled"
            _charge_notifier.notify(
                "Charge Limit",
                f"Battery charge limit {state}",
                icon="battery-full-charged-symbolic",
            )

    def _on_slider_changed(self, _scale, value):
        threshold = round(value)
        self.threshold_label.set_label(f"{threshold}%")
        self.battery_service.set_charge_threshold(threshold)

    def update_state(self, *_):
        cl = self.battery_service.charge_limit
        if cl is not None and cl.enabled:
            self.charge_icon.add_style_class("connected")
        else:
            self.charge_icon.remove_style_class("connected")

        if self._has_threshold:
            threshold = self.battery_service.get_charge_threshold()
            if threshold is not None:
                self.slider.handler_block_by_func(self._on_slider_changed)
                self.slider.set_value(float(threshold))
                self.slider.handler_unblock_by_func(self._on_slider_changed)
                self.threshold_label.set_label(f"{threshold}%")
            is_enabled = cl is not None and cl.enabled
            self.slider.set_sensitive(is_enabled)
            self.slider_box.set_visible(is_enabled)


class GameModeButton(Box):
    def __init__(self, parent, **kwargs):
        super().__init__(name="energy-mode-button", h_expand=True, **kwargs)
        self.parent = parent
        self.gamemode_service = GameModeService.get_initial()
        self.gamemode_service.connect("changed", self.update_state)

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
        self.gamemode_service.toggle()

    def update_state(self, *_):
        if self.gamemode_service.enabled:
            self.game_icon.add_style_class("connected")
        else:
            self.game_icon.remove_style_class("connected")


class BatteryControl(Box):
    def __init__(self, parent, **kwargs):
        super().__init__(
            spacing=12,
            orientation="vertical",
            name="control-center-widgets",
            **kwargs,
        )
        self.set_size_request(354, -1)

        self.parent = parent
        self.battery_service = Battery.get_initial()
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

        self.charge_limit_section = Box(
            orientation="vertical", spacing=8, name="charge-limit-section"
        )

        self.charge_limit_title = Label(
            label="Charge Limit", style_classes="battery-section-title", h_align="start"
        )

        self.charge_limit_container = Box(
            orientation="vertical", spacing=4, name="charge-limit-container"
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

        self.charge_limit_section.add(self.charge_limit_title)
        self.charge_limit_section.add(self.charge_limit_container)
        self.battery_widget.add(self.charge_limit_section)

        separator3 = Separator(orientation="h", name="separator")
        self.battery_widget.add(separator3)

        self.game_mode_section.add(self.game_mode_title)
        self.game_mode_section.add(self.game_mode_container)
        self.battery_widget.add(self.game_mode_section)

        separator4 = Separator(orientation="h", name="separator")
        self.battery_widget.add(separator4)

        self.battery_widget.add(self.battery_settings_button)

        self.add(self.battery_widget)

        self.battery_service.connect("changed", self.on_battery_changed)
        try:
            self.battery_service.connect(
                "power_profile_changed", self.on_profile_changed
            )
        except TypeError as e:
            logger.warning(
                f"[battery_widget] connect power_profile_changed failed: {e}"
            )

        # Initialize display
        self.update_battery_info()
        self.create_energy_mode_buttons()
        self.create_charge_limit_button()
        self.create_game_mode_button()

    def open_battery_settings(self, *args):
        # TODO: Implement to open Battery Settings
        pass

    def create_energy_mode_buttons(self):
        for button in self.energy_mode_buttons:
            button.destroy()
        self.energy_mode_buttons.clear()

        available_profiles = []
        if hasattr(self.battery_service, "get_available_power_profiles"):
            available_profiles = (
                self.battery_service.get_available_power_profiles() or []
            )

        if not available_profiles:
            no_profiles_label = Label(
                label="No energy modes available",
                style_classes="battery-no-profiles",
                h_align="start",
            )
            self.energy_modes_container.add(no_profiles_label)
            return

        energy_mode_config = {
            "balanced": {"display": "Automatic", "icon": "balanced"},
            "power-saver": {"display": "Low Power", "icon": "power"},
            "powersave": {"display": "Low Power", "icon": "power"},
            "performance": {"display": "High Power", "icon": "performance"},
        }

        desired_order = ["balanced", "power-saver", "powersave", "performance"]

        ordered_profiles = []
        for profile_name in desired_order:
            if profile_name in available_profiles:
                ordered_profiles.append(profile_name)

        for profile in available_profiles:
            if profile not in ordered_profiles:
                ordered_profiles.append(profile)

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

    def create_charge_limit_button(self):
        if self.battery_service.charge_limit is None:
            self.charge_limit_section.hide()
            return
        self.charge_limit_section.show()
        if not hasattr(self, "charge_limit_button"):
            self.charge_limit_button = ChargeLimitButton(
                battery_service=self.battery_service,
                parent=self,
            )
            self.charge_limit_container.add(self.charge_limit_button)
        self.charge_limit_button.update_state()

    def create_game_mode_button(self):
        clear_children(self.game_mode_container)
        self.game_mode_button = GameModeButton(parent=self)
        self.game_mode_container.add(self.game_mode_button)

    def update_battery_info(self):
        is_present = self.battery_service.available
        if not is_present:
            self.battery_percentage_label.set_label("No Battery")
            self.power_source_label.set_label("Power Source: Not Present")
            self.charging_time_label.set_label("")
            return

        percentage = int(self.battery_service.percent)
        self.battery_percentage_label.set_label(f"{percentage}%")

        if self.battery_service.charging:
            state = "CHARGING"
        elif self.battery_service.discharging:
            state = "DISCHARGING"
        elif self.battery_service.charged:
            state = "FULLY_CHARGED"
        else:
            state = "UNKNOWN"

        if state in ["CHARGING", "PENDING_CHARGE"]:
            self.power_source_label.set_label("Power Source: Power Adapter")
            seconds_to_full = self.battery_service.time_to_full
            time_to_full = format_duration(seconds_to_full)
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
            seconds_to_empty = self.battery_service.time_remaining
            time_to_empty = format_duration(seconds_to_empty)
            if time_to_empty != "N/A" and not time_to_empty.startswith("4553h"):
                self.charging_time_label.set_label(f"{time_to_empty} remaining")
            else:
                self.charging_time_label.set_label("On Battery Power")
        elif state == "EMPTY":
            self.power_source_label.set_label("Power Source: Battery")
            self.charging_time_label.set_label("Battery Empty")
        else:
            self.power_source_label.set_label("Power Source: Unknown")
            self.charging_time_label.set_label("")

        if hasattr(self, "charge_limit_button"):
            self.charge_limit_button.update_state()

    def on_battery_changed(self, *args):
        self.update_battery_info()

    def on_profile_changed(self, service, *args):
        self.update_energy_mode_buttons()

    def destroy(self):
        try:
            self.battery_service.disconnect_by_func(self.on_battery_changed)
        except Exception as e:
            logger.warning(
                f"[battery_widget] disconnect on_battery_changed failed: {e}"
            )
        try:
            self.battery_service.disconnect_by_func(self.on_profile_changed)
        except Exception as e:
            logger.warning(
                f"[battery_widget] disconnect on_profile_changed failed: {e}"
            )
        super().destroy()
