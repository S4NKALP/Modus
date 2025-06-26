import json
import os

from fabric.hyprland.service import HyprlandEvent
from fabric.hyprland.widgets import Language, get_hyprland_connection
from fabric.system_tray.widgets import SystemTray
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
from .music_player import MusicPlayer
from .workspaces import workspace

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

# Monkey patch SystemTray to use GTK theme icons
from fabric.system_tray.widgets import SystemTrayItem

def _patched_do_update_properties(self, *_):
    """Enhanced update method that prioritizes GTK theme icons"""
    icon_name = self._item.icon_name

    if icon_name:
        # Use the default GTK icon theme to load the icon
        icon_theme = Gtk.IconTheme.get_default()

        try:
            # Try to load the icon from the GTK theme first
            if icon_theme.has_icon(icon_name):
                self._image.set_from_icon_name(icon_name, self._icon_size)
            else:
                # Fallback to original behavior (pixbuf)
                pixbuf = self._item.get_preferred_icon_pixbuf(self._icon_size)
                if pixbuf is not None:
                    self._image.set_from_pixbuf(pixbuf)
                else:
                    self._image.set_from_icon_name("image-missing", self._icon_size)
        except Exception:
            # Fallback to original behavior on any error
            pixbuf = self._item.get_preferred_icon_pixbuf(self._icon_size)
            if pixbuf is not None:
                self._image.set_from_pixbuf(pixbuf)
            else:
                self._image.set_from_icon_name("image-missing", self._icon_size)
    else:
        # No icon name, use original behavior
        pixbuf = self._item.get_preferred_icon_pixbuf(self._icon_size)
        if pixbuf is not None:
            self._image.set_from_pixbuf(pixbuf)
        else:
            self._image.set_from_icon_name("image-missing", self._icon_size)

    # Set tooltip (same as original)
    tooltip = self._item.tooltip
    self.set_tooltip_markup(
        tooltip.description or tooltip.title or self._item.title.title() if self._item.title else "Unknown"
    )
    return

# Apply the patch
SystemTrayItem.do_update_properties = _patched_do_update_properties


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
        self.music_player = MusicPlayer()
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
            self.music_player,
            self.date_time,
            self.language,
            self.systray,
        ]

        # Add each child individually
        for child in self.themed_children:
            self.add(child)

        # Apply initial visibility
        self.apply_component_props()

        # Apply invert style for specific themes and positions
        should_invert = data.DOCK_THEME in ["Dense", "Edge"] or (
            data.DOCK_THEME == "Pills" and data.DOCK_POSITION in ["Left", "Right", "Top"]
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
            "music_player": self.music_player,
            "systray": self.systray,
            "applications": self.applications,
            "language": self.language,
        }

        for component_name, widget in components.items():
            if component_name in self.component_visibility:
                # Special handling for applications component - let it manage its own visibility
                if component_name == "applications":
                    # Only apply config visibility if the component has content
                    if hasattr(widget, "_update_visibility_based_on_content"):
                        widget._update_visibility_based_on_content()
                    else:
                        widget.set_visible(self.component_visibility[component_name])
                else:
                    widget.set_visible(self.component_visibility[component_name])

    def toggle_component_visibility(self, component_name):
        components = {
            "workspaces": self.workspaces,
            "metrics": self.metrics,
            "battery": self.battery,
            "date_time": self.date_time,
            "controls": self.controls,
            "indicators": self.indicators,
            "music_player": self.music_player,
            "systray": self.systray,
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
            else Language().get_label()
        )
        self.language.set_tooltip_text(lang_data)
        if not data.VERTICAL:
            self.lang_label.set_label(lang_data[:2].lower())
        else:
            self.lang_label.add_style_class("icon")
            self.lang_label.set_markup(icons.keyboard)
