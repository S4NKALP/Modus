import subprocess
from threading import Timer
from typing import List

import gi

import config.data as data
from fabric.utils import get_relative_path
from fabric.utils.helpers import exec_shell_command_async
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result

gi.require_version("Gtk", "3.0")


class CaffeinePlugin(PluginBase):
    """
    Plugin for preventing system idle using the inhibit script.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Caffeine"
        self.description = "Prevent system from going idle"
        self.inhibit_script = get_relative_path("../../../utils/inhibit.py")

        # Predefined durations
        self.durations = {
            "30m": "30 minutes",
            "1h": "1 hour",
            "2h": "2 hours",
            "4h": "4 hours",
            "8h": "8 hours",
            "on": "On",
            "off": "Off",
        }

    def initialize(self):
        """Initialize the caffeine plugin."""
        self.set_triggers(["caffeine"])

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
                    start_new_session=True,  # Run in a new session to prevent hanging
                )

                # Send notification based on duration
                if duration.lower() == "off":
                    # Deactivation notification
                    exec_shell_command_async(
                        f"notify-send '☕ Caffeine' 'Deactivated' -a '{
                            data.APP_NAME_CAP
                        }' -e"
                    )
                else:
                    # Activation notification with duration
                    duration_text = self.durations.get(duration, duration)
                    exec_shell_command_async(
                        f"notify-send '☕ Caffeine' 'Activated for {
                            duration_text
                        }' -a '{data.APP_NAME_CAP}' -e"
                    )

                    # Schedule expiration notification for timed durations
                    if duration.lower() not in ["on", "off"]:
                        self._schedule_expiration_notification(duration, duration_text)

            except Exception as e:
                print(f"Error starting inhibit script: {e}")

        return action

    def _parse_duration_to_seconds(self, duration_str: str) -> int:
        """Parse duration string into seconds. Same logic as inhibit.py"""
        try:
            if duration_str.lower() in ["on", "off"]:
                return 0
            elif duration_str.endswith("h"):
                return int(float(duration_str[:-1]) * 3600)
            elif duration_str.endswith("m"):
                return int(float(duration_str[:-1]) * 60)
            elif duration_str.endswith("s"):
                return int(float(duration_str[:-1]))
            else:
                return int(duration_str)
        except ValueError:
            return 0

    def _schedule_expiration_notification(self, duration: str, duration_text: str):
        """Schedule a notification for when the caffeine effect expires."""
        seconds = self._parse_duration_to_seconds(duration)
        if seconds > 0:

            def send_expiration_notification():
                exec_shell_command_async(
                    f"notify-send '☕ Caffeine' 'Expired after {duration_text}' -a '{
                        data.APP_NAME_CAP
                    }' -e"
                )

            # Schedule the notification
            timer = Timer(seconds, send_expiration_notification)
            timer.daemon = True  # Don't prevent program exit
            timer.start()

    def _is_valid_duration(self, query: str) -> bool:
        """Check if the query is a valid duration format."""
        if query in self.durations:
            return True
        if query.isdigit():
            return True
        if query.endswith(("h", "m", "s")) and query[:-1].replace(".", "").isdigit():
            return True
        return False

    def _get_default_action(self, query: str):
        """Get the default action for a direct duration input."""
        if self._is_valid_duration(query):
            return self._create_inhibit_action(query)
        return None

    def query(self, query_string: str) -> List[Result]:
        """Search caffeine durations based on query."""
        # For empty queries, show all available durations
        if not query_string.strip():
            query_string = ""  # Will match all durations in the loop below

        query = query_string.lower().strip()
        results = []

        # Handle direct search entry (e.g., "caffeine 30m" or just "30m")
        if query.startswith("caffeine "):
            query = query[9:].strip()  # Remove "caffeine " prefix
            # If query becomes empty after removing prefix, show all durations
            if not query:
                query = ""  # Will match all durations in the loop below
        elif query == "caffeine":
            # Handle just "caffeine" without space - show all durations
            query = ""
        elif not query:
            # Handle empty query - show all durations
            pass
        elif (
            query in self.durations
            or query.isdigit()
            or (
                query.endswith(("h", "m", "s"))
                and query[:-1].replace(".", "").isdigit()
            )
        ):
            # If query is a valid duration without prefix, use it directly
            pass
        else:
            return []

        # Add custom duration option
        if query.isdigit() or (
            query.endswith(("h", "m", "s")) and query[:-1].replace(".", "").isdigit()
        ):
            result = Result(
                title=f"Custom: {query}",
                subtitle="Set custom duration",
                icon_name="caffeine",
                action=self._create_inhibit_action(query),
                relevance=1.0,
                plugin_name=self.display_name,
                data={"duration": query},
            )
            results.append(result)

        # Add predefined durations
        for duration, description in self.durations.items():
            # If query is empty, show all durations; otherwise filter by query
            if not query or query in duration or query in description.lower():
                # Special handling for "off" - it should stop inhibition
                if duration.lower() == "off":
                    subtitle = "Stop idle inhibition"
                else:
                    subtitle = f"Prevent idle for {description.lower()}"

                result = Result(
                    title=description,
                    subtitle=subtitle,
                    icon_name="caffeine",
                    action=self._create_inhibit_action(duration),
                    relevance=0.9 if query == duration else 0.7,
                    plugin_name=self.display_name,
                    data={"duration": duration},
                )
                results.append(result)

        # Set default action for direct duration input
        if results:
            results[0].default_action = self._get_default_action(query)

        return results
