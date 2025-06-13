from typing import List, Dict, Any
from fabric.utils import get_desktop_applications, DesktopApp, exec_shell_command_async
from . import LauncherPlugin


class ApplicationsPlugin(LauncherPlugin):
    """Plugin for searching desktop applications"""

    @property
    def name(self) -> str:
        return "Applications"

    @property
    def category(self) -> str:
        return "Applications"

    @property
    def icon_name(self) -> str:
        return "application-x-executable-symbolic"

    def search(self, query: str) -> List[Dict[str, Any]]:
        all_apps = get_desktop_applications()

        # Filter apps based on query
        filtered_apps = [
            app
            for app in all_apps
            if query.casefold()
            in (
                (app.display_name or "")
                + (" " + app.name + " ")
                + (app.generic_name or "")
            ).casefold()
        ]

        # Sort by relevance - exact matches first
        if query:
            exact_matches = []
            partial_matches = []

            for app in filtered_apps:
                name = (app.display_name or app.name or "").casefold()
                if name == query.casefold() or name.startswith(query.casefold()):
                    exact_matches.append(app)
                else:
                    partial_matches.append(app)

            filtered_apps = exact_matches + partial_matches

        # Convert to result format
        results = []
        for app in filtered_apps:
            results.append(
                {
                    "title": app.display_name or app.name or "Unknown",
                    "description": app.description or "Application",
                    "icon": app,  # Pass the whole app object for icon rendering
                    "action": lambda app=app: self.launch_app(app),
                    "app": app,  # Store the original app object
                }
            )

        return results

    def launch_app(self, app: DesktopApp):
        command = (
            " ".join([arg for arg in app.command_line.split() if "%" not in arg])
            if app.command_line
            else None
        )
        (
            exec_shell_command_async(
                f"hyprctl dispatch exec -- {command}",
                lambda *_: print(f"Launched {app.name}"),
            )
            if command
            else None
        )
