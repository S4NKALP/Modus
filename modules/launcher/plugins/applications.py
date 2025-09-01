import json
import re
from typing import List
import subprocess

from fabric.utils import DesktopApp
from fabric.utils.helpers import get_desktop_applications, get_relative_path
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
from utils.roam import modus_service


class ApplicationsPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.display_name = "Applications"
        self.description = "Search and launch desktop applications"

    def initialize(self):
        pass

    def cleanup(self):
        pass

    def _pin_application(self, app):
        """Pin an application to the dock."""
        config_path = get_relative_path("../../../config/assets/dock.json")
        try:
            with open(config_path, "r") as file:
                pinned_apps = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            pinned_apps = []

        # Handle legacy format (dict with "pinned_apps" key) and convert to new format (simple list)
        if isinstance(pinned_apps, dict):
            pinned_apps = pinned_apps.get("pinned_apps", [])

        # Check if app is already pinned (by name/app_id)
        app_id = app.name  # Use app.name as the identifier
        if app_id not in pinned_apps:
            pinned_apps.append(app_id)

            # Save the updated list
            with open(config_path, "w") as file:
                json.dump(pinned_apps, file, indent=4)

            # Notify dock about the change via modus_service
            if modus_service:
                try:
                    dock_apps_json = json.dumps(pinned_apps)
                    modus_service.dock_apps = dock_apps_json
                except Exception as e:
                    print(f"Failed to notify dock about pinned app change: {e}")

    def query(self, query_string: str) -> List[Result]:
        """Search applications based on query."""
        if not query_string.strip():
            return self._get_all_applications()

        try:
            applications = get_desktop_applications(include_hidden=False)
        except Exception as e:
            print(f"Failed to load applications: {e}")
            applications = []

        query = query_string.lower().strip()
        results = []

        for app in applications:
            relevance = self._calculate_relevance(app, query)
            if relevance > 0:
                description = app.description or app.generic_name or ""
                if len(description) > 80:
                    description = description[:70] + "..."

                result = Result(
                    title=app.display_name or app.name,
                    subtitle=description,
                    icon=app.get_icon_pixbuf(size=48),
                    action=lambda a=app: self._launch_application(a),
                    relevance=relevance,
                    plugin_name=self.display_name,
                    data={
                        "app": app,
                        "pin_action": lambda a=app: self._pin_application(a),
                    },
                )
                results.append(result)

        return results

    def _calculate_relevance(self, app, query: str) -> float:
        """Calculate relevance score for an application."""
        if not query:
            return 0.0

        # Get searchable text
        name = (app.name or "").lower()
        display_name = (app.display_name or "").lower()
        description = (app.description or "").lower()
        generic_name = (app.generic_name or "").lower()
        executable = (app.executable or "").lower()

        # Exact matches get highest score
        if query == name or query == display_name:
            return 1.0

        # Starts with matches get high score
        if (
            name.startswith(query)
            or display_name.startswith(query)
            or generic_name.startswith(query)
        ):
            return 0.9

        # Contains matches get medium score
        if (
            query in name
            or query in display_name
            or query in description
            or query in generic_name
        ):
            return 0.7

        # Fuzzy matching for partial matches
        if self._fuzzy_match(query, name) or self._fuzzy_match(query, display_name):
            return 0.5

        # Executable name matching
        if executable and query in executable:
            return 0.4

        return 0.0

    def _fuzzy_match(self, query: str, text: str) -> bool:
        """Simple fuzzy matching algorithm."""
        if not query or not text:
            return False

        # Create regex pattern for fuzzy matching
        pattern = ".*".join(re.escape(char) for char in query)
        return bool(re.search(pattern, text, re.IGNORECASE))

    def _launch_application(self, app: DesktopApp):

        # Remove ALL % codes (e.g., %u, %U, %f, %F, %i, %c, etc.)
        cleaned_command = re.sub(r"%\w+", "", app.command_line).strip()

        # Final command with hyprctl dispatch
        final_command = f"hyprctl dispatch exec 'uwsm app -- {cleaned_command}'"
        subprocess.Popen(final_command, shell=True)

        # app.launch()

    def _get_all_applications(self) -> List[Result]:
        """Get a list of all available applications."""
        try:
            applications = get_desktop_applications(include_hidden=False)
        except Exception as e:
            print(f"Failed to load applications: {e}")
            return []

        results = []

        for app in applications:
            # Truncate description
            description = app.description or app.generic_name or ""
            if len(description) > 80:
                description = description[:70] + "..."

            result = Result(
                title=app.display_name or app.name,
                subtitle=description,
                icon=app.get_icon_pixbuf(size=48),
                action=lambda a=app: self._launch_application(a),
                relevance=0.5,  # Default relevance for all apps
                plugin_name=self.display_name,
                data={
                    "app": app,
                    "pin_action": lambda a=app: self._pin_application(a),
                },
            )
            results.append(result)

        return results
