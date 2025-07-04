import json
import re
from typing import List

from fabric.utils import DesktopApp
from fabric.utils.helpers import get_desktop_applications, get_relative_path

from modules.dock.main import Dock
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class ApplicationsPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.display_name = "Applications"
        self.description = "Search and launch desktop applications"

    def initialize(self):
        # Set up triggers for applications - both with and without spaces
        self.set_triggers(["app"])

    def cleanup(self):
        pass

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

        config_path = get_relative_path("../../../config/assets/dock.json")
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

        # Get fresh applications list each time (like examples/app-launcher)
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
                # Truncate description to prevent overflow beyond 550px window
                description = app.description or app.generic_name or ""
                if len(description) > 80:  # Limit to ~80 characters to fit in 550px
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
        app.launch()
