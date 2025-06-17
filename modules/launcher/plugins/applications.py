"""
Applications plugin for the launcher.
Searches and launches desktop applications.
"""

import re
import json
from typing import List
from fabric.utils.helpers import get_desktop_applications, get_relative_path
from ..plugin_base import PluginBase
from ..result import Result
from modules.dock.main import Dock


class ApplicationsPlugin(PluginBase):
    """
    Plugin for searching and launching desktop applications.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Applications"
        self.description = "Search and launch desktop applications"
        self.applications = []

    def initialize(self):
        """Initialize the applications plugin."""
        # Set up triggers for applications - both with and without spaces
        self.set_triggers(["app", "app "])
        print("Initializing Applications plugin...")
        self._load_applications()

    def cleanup(self):
        """Cleanup the applications plugin."""
        self.applications = []

    def _load_applications(self):
        """Load all desktop applications."""
        try:
            self.applications = get_desktop_applications(include_hidden=False)
            print(f"Loaded {len(self.applications)} applications")
        except Exception as e:
            print(f"Failed to load applications: {e}")
            self.applications = []

    def _pin_application(self, app):
        """Pin an application to the dock."""
        app_data = {
            k: v
            for k, v in {
                "name": app.name,
                "display_name": app.display_name,
                "window_class": app.window_class,
                "executable": app.executable,
                "command_line": app.command_line,
                "icon_name": app.icon_name,
            }.items()
            if v is not None
        }

        config_path = get_relative_path("../../../config/dock.json")
        try:
            with open(config_path, "r") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"pinned_apps": []}

        already_pinned = False
        for pinned_app in data.get("pinned_apps", []):
            if (
                isinstance(pinned_app, dict)
                and pinned_app.get("name") == app_data["name"]
            ):
                already_pinned = True
                pinned_app.update(app_data)
                break
            elif isinstance(pinned_app, str) and pinned_app == app_data["name"]:
                already_pinned = True
                data["pinned_apps"].remove(pinned_app)
                data["pinned_apps"].append(app_data)
                break

        if not already_pinned:
            data.setdefault("pinned_apps", []).append(app_data)

        with open(config_path, "w") as file:
            json.dump(data, file, indent=4)

        Dock.notify_config_change()

    def query(self, query_string: str) -> List[Result]:
        """Search applications based on query."""
        if not query_string.strip():
            return []

        query = query_string.lower().strip()
        results = []

        for app in self.applications:
            relevance = self._calculate_relevance(app, query)
            if relevance > 0:
                result = Result(
                    title=app.display_name or app.name,
                    subtitle=app.description or app.generic_name or "",
                    icon=app.get_icon_pixbuf(size=48),
                    action=lambda a=app: self._launch_application(a),
                    relevance=relevance,
                    plugin_name=self.display_name,
                    data={
                        "app": app,
                        "pin_action": lambda a=app: self._pin_application(a)
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

    def _launch_application(self, app):
        """Launch a desktop application."""
        try:
            success = app.launch()
            if not success:
                # Fallback to command line execution
                if app.command_line:
                    import subprocess

                    subprocess.Popen(
                        app.command_line,
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                elif app.executable:
                    import subprocess

                    subprocess.Popen(
                        [app.executable],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            print(f"Launched application: {app.name}")
        except Exception as e:
            print(f"Failed to launch application {app.name}: {e}")
