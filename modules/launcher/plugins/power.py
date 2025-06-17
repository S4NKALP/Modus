"""
Power management plugin for the launcher.
Handles system power operations like shutdown, restart, sleep, etc.
"""

from typing import List

import utils.icons as icons
from fabric.utils import exec_shell_command_async
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class PowerPlugin(PluginBase):
    """
    Plugin for system power management operations.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Power"
        self.description = "System power management and control"
        self.commands = {
            "shutdown": {
                "description": "Shutdown the system",
                "icon": icons.shutdown,
                "action": self.shutdown,
            },
            "restart": {
                "description": "Restart the system",
                "icon": icons.reboot,
                "action": self.restart,
            },
            "lock": {
                "description": "Lock the screen",
                "icon": icons.lock,
                "action": self.lock,
            },
            "suspend": {
                "description": "Suspend the system",
                "icon": icons.suspend,
                "action": self.suspend,
            },
            "logout": {
                "description": "Logout from current session",
                "icon": icons.logout,
                "action": self.logout,
            },
        }

    def initialize(self):
        """Initialize the power plugin."""
        self.set_triggers(["power", "power "])

    def cleanup(self):
        """Cleanup the power plugin."""
        pass

    def query(self, query_string: str) -> List[Result]:
        """Search power commands based on query."""
        if not query_string.strip():
            return []

        query = query_string.lower().strip()
        results = []

        for cmd, info in self.commands.items():
            if query in cmd.lower() or query in info["description"].lower():
                result = Result(
                    title=cmd.capitalize(),
                    subtitle=info["description"],
                    icon_markup=info["icon"],
                    action=info["action"],
                    relevance=1.0 if query == cmd else 0.7,
                    plugin_name=self.display_name,
                    data={"command": cmd},
                )
                results.append(result)

        return results

    def shutdown(self, *args) -> None:
        exec_shell_command_async("systemctl poweroff")

    def restart(self, *args) -> None:
        exec_shell_command_async("systemctl reboot")

    def lock(self, *args) -> None:
        exec_shell_command_async("loginctl lock-session")

    def suspend(self, *args) -> None:
        exec_shell_command_async("systemctl suspend")

    def logout(self, *args) -> None:
        exec_shell_command_async("hyprctl dispatch exit")
