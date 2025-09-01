from typing import List

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
                "icon": "system-shutdown-symbolic",
                "action": self.shutdown,
            },
            "restart": {
                "description": "Restart the system",
                "icon": "system-reboot-symbolic",
                "action": self.restart,
            },
            "lock": {
                "description": "Lock the screen",
                "icon": "system-lock-screen-symbolic",
                "action": self.lock,
            },
            "suspend": {
                "description": "Suspend the system",
                "icon": "system-suspend-symbolic",
                "action": self.suspend,
            },
            "logout": {
                "description": "Logout from current session",
                "icon": "system-log-out-symbolic",
                "action": self.logout,
            },
        }

    def initialize(self):
        """Initialize the power plugin."""
        self.set_triggers(["power"])

    def cleanup(self):
        """Cleanup the power plugin."""
        pass

    def query(self, query_string: str) -> List[Result]:
        """Search power commands based on query."""
        query = query_string.lower().strip()
        results = []

        # If no query, show all power commands
        if not query:
            for cmd, info in self.commands.items():
                result = Result(
                    title=cmd.capitalize(),
                    subtitle=info["description"],
                    icon_name=info["icon"],
                    action=info["action"],
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"command": cmd},
                )
                results.append(result)
        else:
            # Filter commands based on query
            for cmd, info in self.commands.items():
                if query in cmd.lower() or query in info["description"].lower():
                    result = Result(
                        title=cmd.capitalize(),
                        subtitle=info["description"],
                        icon_name=info["icon"],
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
