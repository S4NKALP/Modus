"""
Caffeine plugin for the launcher.
Prevents system from going idle for a specified duration.
"""

import subprocess
import os
from typing import List
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib
from ..plugin_base import PluginBase
from ..result import Result
from fabric.widgets.label import Label
import utils.icons as icons

class CaffeinePlugin(PluginBase):
    """
    Plugin for preventing system idle using the inhibit script.
    """
    
    def __init__(self):
        super().__init__()
        self.display_name = "Caffeine"
        self.description = "Prevent system from going idle"
        self.inhibit_script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "utils", "inhibit.py")
        
        # Predefined durations
        self.durations = {
            "30m": "30 minutes",
            "1h": "1 hour",
            "2h": "2 hours",
            "4h": "4 hours",
            "8h": "8 hours",
            "indefinite": "Indefinitely",
            "off": "Off"
        }

    def initialize(self):
        """Initialize the caffeine plugin."""
        self.set_triggers(["caffeine", "caffeine "])

    def cleanup(self):
        """Cleanup the caffeine plugin."""
        pass

    def _create_inhibit_action(self, duration: str):
        """Create an inhibit action that properly captures the duration."""
        def action():
            try:
                # Run the script in the background without waiting
                subprocess.Popen(
                    ["python3", self.inhibit_script, duration],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True  # Run in a new session to prevent hanging
                )
            except Exception as e:
                print(f"Error starting inhibit script: {e}")
        return action

    def _is_valid_duration(self, query: str) -> bool:
        """Check if the query is a valid duration format."""
        if query in self.durations:
            return True
        if query.isdigit():
            return True
        if query.endswith(('h', 'm', 's')) and query[:-1].replace('.', '').isdigit():
            return True
        return False

    def _get_default_action(self, query: str):
        """Get the default action for a direct duration input."""
        if self._is_valid_duration(query):
            return self._create_inhibit_action(query)
        return None

    def query(self, query_string: str) -> List[Result]:
        """Search caffeine durations based on query."""
        if not query_string.strip():
            return []

        query = query_string.lower().strip()
        results = []

        # Handle direct search entry (e.g., "caffeine 30m" or just "30m")
        if query.startswith("caffeine "):
            query = query[9:].strip()  # Remove "caffeine " prefix
        elif query in self.durations or (query.endswith(('h', 'm', 's')) and query[:-1].replace('.', '').isdigit()):
            # If query is a valid duration without prefix, use it directly
            pass
        else:
            return []


        # Add custom duration option
        if query.isdigit() or (query.endswith(('h', 'm', 's')) and query[:-1].replace('.', '').isdigit()):
            result = Result(
                title=f"Custom: {query}",
                subtitle="Set custom duration",
                icon_markup=icons.coffee,
                action=self._create_inhibit_action(query),
                relevance=1.0,
                plugin_name=self.display_name,
                data={"duration": query}
            )
            results.append(result)

        # Add predefined durations
        for duration, description in self.durations.items():
            if query in duration or query in description.lower():
                result = Result(
                    title=description,
                    subtitle=f"Prevent idle for {description.lower()}",
                    icon_markup=icons.coffee,
                    action=self._create_inhibit_action(duration),
                    relevance=0.9 if query == duration else 0.7,
                    plugin_name=self.display_name,
                    data={"duration": duration}
                )
                results.append(result)

        # Set default action for direct duration input
        if results:
            results[0].default_action = self._get_default_action(query)

        return results 