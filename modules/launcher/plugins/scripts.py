"""
Scripts plugin for the launcher.
Provides access to various system scripts and utilities.
"""

import os
import subprocess
from typing import List

from fabric.utils import exec_shell_command_async
import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class ScriptsPlugin(PluginBase):
    """
    Plugin for executing system scripts and utilities.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Scripts"
        self.description = "System scripts and utilities"

    def initialize(self):
        """Initialize the scripts plugin."""
        # Use individual trigger keywords for each specific action
        self.set_triggers([
            # Color picker variants
            "color hex",
            "color rgb",
            "color hsv",

            # Night light
            "night"

        ])

    def cleanup(self):
        """Cleanup the scripts plugin."""
        pass


    def _run_colorpicker(self, format_type: str):
        """Run color picker with specified format."""
        script_path = self._get_script_path("hyprpicker.sh")
        exec_shell_command_async(f"bash '{script_path}' -{format_type}")



    def _get_script_path(self, script_name: str) -> str:
        """Get the full path to a script from the scripts directory."""
        # Get the current working directory (should be Modus root)
        current_dir = os.getcwd()

        # Try scripts directory relative to current working directory
        script_path = os.path.join(current_dir, "scripts", script_name)
        if os.path.exists(script_path):
            return script_path

        # Try relative to this file's location
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        modus_root = os.path.dirname(os.path.dirname(os.path.dirname(plugin_dir)))
        script_path = os.path.join(modus_root, "scripts", script_name)
        if os.path.exists(script_path):
            return script_path

        # Fallback to relative path
        return f"scripts/{script_name}"

    def _get_trigger_actions(self) -> dict:
        """Get the map of trigger patterns to actions."""

        return {
            # Color picker triggers
            "color hex": {
                "title": "Color Picker (HEX)",
                "subtitle": "Pick a color and copy HEX value to clipboard",
                "icon": icons.colorpicker,
                "action": lambda: self._run_colorpicker("hex"),
            },
            "color rgb": {
                "title": "Color Picker (RGB)",
                "subtitle": "Pick a color and copy RGB value to clipboard",
                "icon": icons.colorpicker,
                "action": lambda: self._run_colorpicker("rgb"),
            },
            "color hsv": {
                "title": "Color Picker (HSV)",
                "subtitle": "Pick a color and copy HSV value to clipboard",
                "icon": icons.colorpicker,
                "action": lambda: self._run_colorpicker("hsv"),
            },

            # Night light triggers
            "night": {
                "title": "Toggle Night Light",
                "subtitle": "Toggle blue light filter for eye comfort",
                "icon": icons.night,
                "action": lambda: self._run_system_command("hyprctl keyword decoration:screen_shader ~/.config/hypr/shaders/blue_light_filter.glsl"),
            }
        }

    def query(self, query_string: str) -> List[Result]:
        """Search for script actions based on query."""
        query = query_string.strip().lower()
        results = []

        # Get trigger actions
        trigger_actions = self._get_trigger_actions()

        # If no query, return empty results (don't show all actions)
        if not query:
            return []

        # Check if query exactly matches one of our triggers
        # If so, show only that specific result
        for trigger_key in trigger_actions:
            if query == trigger_key.lower():
                action_data = trigger_actions[trigger_key]
                return [Result(
                    title=action_data["title"],
                    subtitle=action_data["subtitle"],
                    icon_markup=action_data["icon"],
                    action=action_data["action"],
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"trigger": trigger_key}
                )]

        # Search through trigger actions for partial matches
        for trigger, action_data in trigger_actions.items():
            # Check if query matches trigger or is contained in title
            if (query in trigger.lower() or
                query in action_data["title"].lower() or
                any(word in trigger.lower() for word in query.split())):

                # Calculate relevance based on match quality
                if query == trigger.lower():
                    relevance = 1.0
                elif trigger.lower().startswith(query):
                    relevance = 0.9
                elif query in trigger.lower():
                    relevance = 0.8
                else:
                    relevance = 0.7

                results.append(Result(
                    title=action_data["title"],
                    subtitle=action_data["subtitle"],
                    icon_markup=action_data["icon"],
                    action=action_data["action"],
                    relevance=relevance,
                    plugin_name=self.display_name,
                    data={"trigger": trigger}
                ))

        return sorted(results, key=lambda x: x.relevance, reverse=True)

    def query_triggered(self, _query_string: str, trigger: str) -> List[Result]:
        """
        Process a triggered query (when plugin is activated by a specific trigger).
        Show only the specific result for the triggered keyword.
        """
        # Get trigger actions
        trigger_actions = self._get_trigger_actions()

        # Find the exact trigger match and return only that result
        trigger_lower = trigger.lower().strip()

        if trigger_lower in trigger_actions:
            action_data = trigger_actions[trigger_lower]
            return [Result(
                title=action_data["title"],
                subtitle=action_data["subtitle"],
                icon_markup=action_data["icon"],
                action=action_data["action"],
                relevance=1.0,
                plugin_name=self.display_name,
                data={"trigger": trigger_lower}
            )]

        # If no exact match found, return empty list
        return []


