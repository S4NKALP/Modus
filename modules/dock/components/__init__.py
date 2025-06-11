import os
import json
import config.data as data
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.datetime import DateTime
from fabric.system_tray.widgets import SystemTray
from .battery import Battery
from .metrics import Metrics
from .controls import Controls
from .workspaces import workspace
from .indicators import Indicators
from .applications import Applications


class DockComponents(Box):
    def __init__(self, orientation_val="h", dock_instance=None, **kwargs):
        super().__init__(
            name="dock-components", orientation=orientation_val, spacing=8, **kwargs
        )

        self.dock_instance = dock_instance

        # Create applications with dock reference
        self.applications = Applications(
            orientation_val=orientation_val, dock_instance=dock_instance
        )

        # Initialize component visibility from data
        self.component_visibility = data.DOCK_COMPONENTS_VISIBILITY

        # Create components
        self.workspaces = workspace  # Use the workspace instance directly
        self.metrics = Metrics()
        self.battery = Battery()
        self.date_time = DateTime(
            name="date-time",
            formatters=["%I:%M"] if not data.VERTICAL else ["%I\n%M"],
            h_align="center" if not data.VERTICAL else "fill",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )
        self.controls = Controls()
        self.indicators = Indicators()
        self.systray = SystemTray(
            icon_size=18,
            spacing=4,
            name="tray",
            orientation="h" if not data.VERTICAL else "v",
        )

        # Create list of components to add
        self.themed_children = [
            self.workspaces,
            self.metrics,
            self.controls,
            self.applications,
            self.indicators,
            self.battery,
            self.date_time,
            self.systray,
        ]

        # Add each child individually
        for child in self.themed_children:
            self.add(child)

        # Apply initial visibility
        self.apply_component_props()

        # Apply invert style for specific themes and positions
        should_invert = (
            data.DOCK_THEME in ["Dense", "Edge"] or
            (data.DOCK_THEME == "Pills" and data.DOCK_POSITION in ["Left", "Right"])
        )

        if should_invert:
            for child in self.themed_children:
                if hasattr(child, "add_style_class"):
                    child.add_style_class("invert")

    def apply_component_props(self):
        components = {
            "workspaces": self.workspaces,
            "metrics": self.metrics,
            "battery": self.battery,
            "date_time": self.date_time,
            "controls": self.controls,
            "indicators": self.indicators,
            "systray": self.systray,
            "applications": self.applications,
        }

        for component_name, widget in components.items():
            if component_name in self.component_visibility:
                widget.set_visible(self.component_visibility[component_name])

    def toggle_component_visibility(self, component_name):
        components = {
            "workspaces": self.workspaces,
            "metrics": self.metrics,
            "battery": self.battery,
            "date_time": self.date_time,
            "controls": self.controls,
            "indicators": self.indicators,
            "systray": self.systray,
            "applications": self.applications,
        }

        if component_name in components and component_name in self.component_visibility:
            self.component_visibility[component_name] = not self.component_visibility[
                component_name
            ]
            components[component_name].set_visible(
                self.component_visibility[component_name]
            )

            config_file = os.path.expanduser(
                f"~/.config/{data.APP_NAME}/config/config.json"
            )
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r") as f:
                        config = json.load(f)

                    config[f"dock_{component_name}_visible"] = (
                        self.component_visibility[component_name]
                    )

                    with open(config_file, "w") as f:
                        json.dump(config, f, indent=4)
                except Exception as e:
                    print(f"Error updating config file: {e}")

            return self.component_visibility[component_name]

        return None
