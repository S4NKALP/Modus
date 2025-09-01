# Standard library imports
import subprocess

# Fabric imports
from fabric.utils.helpers import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.svg import Svg

# Local imports
from loguru import logger


class NightLightControl:
    """Control night light using hyprsunset"""

    def __init__(self):
        self.is_active = False
        self._check_initial_state()

    def _check_initial_state(self):
        """Check if hyprsunset is currently running"""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "hyprsunset"], capture_output=True, text=True
            )
            self.is_active = bool(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Failed to check hyprsunset status: {e}")
            self.is_active = False

    def toggle(self):
        """Toggle night light on/off"""
        try:
            if self.is_active:
                # Turn off night light by killing hyprsunset
                subprocess.run(["pkill", "hyprsunset"], check=False)
                self.is_active = False
                logger.debug("Night light turned off")
            else:
                # Turn on night light with default temperature (3000K)
                subprocess.Popen(["hyprsunset", "-t", "4500"], start_new_session=True)
                self.is_active = True
                logger.debug("Night light turned on")
            return True
        except Exception as e:
            logger.warning(f"Failed to toggle night light: {e}")
            return False

    def set_temperature(self, temperature: int):
        """Set night light temperature (1000-6500K)"""
        try:
            # Kill existing process
            subprocess.run(["pkill", "hyprsunset"], check=False)

            # Start with new temperature
            subprocess.Popen(
                ["hyprsunset", "-t", str(temperature)], start_new_session=True
            )
            self.is_active = True
            logger.debug(f"Night light temperature set to {temperature}K")
            return True
        except Exception as e:
            logger.warning(f"Failed to set night light temperature: {e}")
            return False


def create_night_light_widget(control_center):
    """Create night light widget for control center"""

    # Initialize night light control
    night_light = NightLightControl()

    # Create icon
    night_light_icon = Svg(
        name="nightlight-icon",
        svg_file=get_relative_path(
            "../../config/assets/icons/applets/redshift-status-on.svg"
            if night_light.is_active
            else "../../config/assets/icons/applets/redshift-status-off.svg"
        ),
        size=42,
    )

    # Create status label
    night_light_status_label = Label(
        label="On" if night_light.is_active else "Off",
        name="nightlight-widget-label",
        style_classes="status-label",
        max_chars_width=15,
        ellipsization="end",
        h_align="start",
    )

    def toggle_night_light(*_):
        """Toggle night light and update UI"""
        if night_light.toggle():
            # Update icon
            night_light_icon.set_from_file(
                get_relative_path(
                    "../../config/assets/icons/applets/redshift-status-on.svg"
                    if night_light.is_active
                    else "../../config/assets/icons/applets/redshift-status-off.svg"
                )
            )
            # Update status label
            night_light_status_label.set_label("On" if night_light.is_active else "Off")

    # Create widget box (similar to bluetooth_widget structure)
    night_light_widget = Box(
        name="nightlight-widget",
        orientation="h",
        h_expand=True,
        children=[
            Button(
                name="nightlight-icon-button",
                child=night_light_icon,
                on_clicked=toggle_night_light,
            ),
            Button(
                name="nightlight-info-button",
                child=Box(
                    name="nightlight-widget-info",
                    h_expand=True,
                    v_expand=True,
                    v_align="center",
                    h_align="start",
                    orientation="vertical",
                    children=[
                        Label(
                            name="nightlight-widget-name",
                            label="Night Light",
                            style_classes="ct",
                            h_align="start",
                        ),
                        night_light_status_label,
                    ],
                ),
                on_clicked=toggle_night_light,
            ),
        ],
    )

    return night_light_widget

