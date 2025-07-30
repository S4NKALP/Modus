from gi.repository import Gtk

# from fabric.system_tray.widgets import SystemTrayItem
import json
import os

import gi
from fabric.hyprland.service import HyprlandEvent
from fabric.hyprland.widgets import HyprlandLanguage, get_hyprland_connection
from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.datetime import DateTime
from fabric.widgets.label import Label

import config.data as data
import utils.icons as icons

from .applications import Applications
from .battery import Battery
from .controls import Controls
from .indicators import Indicators
from .metrics import Metrics
from .workspaces import workspace
# from .systemtray import SystemTray

gi.require_version("Gtk", "3.0")
# Monkey patch SystemTray to use GTK theme icons


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

        self.connection = get_hyprland_connection()
        self.lang_label = Label(name="lang-label")
        self.language = Button(
            name="language", h_align="center", v_align="center", child=self.lang_label
        )
        self.on_language_switch()
        self.connection.connect("event::activelayout", self.on_language_switch)

        # Initialize component visibility from data
        self.component_visibility = data.DOCK_COMPONENTS_VISIBILITY

        # Create components
        self.workspaces = workspace
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
        # self.systray = SystemTray()

        # Create list of components to add
        self.themed_children = [
            self.workspaces,
            self.metrics,
            self.controls,
            self.applications,
            self.indicators,
            self.battery,
            self.date_time,
            self.language,
            # self.systray,
        ]

        # Add each child individually
        for child in self.themed_children:
            self.add(child)

        # Apply initial visibility
        self.apply_component_props()

        # Apply invert style for specific themes and positions
        should_invert = data.DOCK_THEME in ["Dense", "Edge"] or (
            data.DOCK_THEME == "Pills"
            and data.DOCK_POSITION in ["Left", "Right", "Top"]
        )

        if should_invert:
            for child in self.themed_children:
                if hasattr(child, "add_style_class"):
                    child.add_style_class("invert")

    def apply_component_props(self):
        components = {
            "workspace": self.workspaces,
            "metrics": self.metrics,
            "battery": self.battery,
            "date_time": self.date_time,
            "controls": self.controls,
            "indicators": self.indicators,
            # "systray": self.systray,
            "applications": self.applications,
            "language": self.language,
        }

        for component_name, widget in components.items():
            if component_name in self.component_visibility:
                visibility = self.component_visibility[component_name]
                # Special handling for applications component - let it manage its own visibility
                if component_name == "applications":
                    # Only apply config visibility if the component has content
                    if hasattr(widget, "_update_visibility_based_on_content"):
                        widget._update_visibility_based_on_content()
                    else:
                        widget.set_visible(visibility)
                # Special handling for battery - let it manage its own visibility based on config and battery state
                elif component_name == "battery":
                    # Battery component manages its own visibility based on config and battery presence
                    # Don't override its visibility here, let it handle it internally
                    pass
                else:
                    widget.set_visible(visibility)

    def toggle_component_visibility(self, component_name):
        components = {
            "workspace": self.workspaces,
            "metrics": self.metrics,
            "battery": self.battery,
            "date_time": self.date_time,
            "controls": self.controls,
            "indicators": self.indicators,
            # "systray": self.systray,
            "applications": self.applications,
            "language": self.language,
        }

        if component_name in components and component_name in self.component_visibility:
            self.component_visibility[component_name] = not self.component_visibility[
                component_name
            ]

            components[component_name].set_visible(
                self.component_visibility[component_name]
            )

            config_file = get_relative_path("../../../config/assets/config.json")
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

    def on_language_switch(self, _=None, event: HyprlandEvent = None):
        lang_data = (
            event.data[1]
            if event and event.data and len(event.data) > 1
            else HyprlandLanguage().get_label()
        )
        self.language.set_tooltip_text(lang_data)
        if not data.VERTICAL:
            self.lang_label.set_label(lang_data[:2].lower())
        else:
            self.lang_label.add_style_class("icon")
            self.lang_label.set_markup(icons.keyboard)
