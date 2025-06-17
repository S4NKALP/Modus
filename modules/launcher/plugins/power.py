"""
Power management plugin for the launcher.
Handles system power operations like shutdown, restart, sleep, etc.
"""

import subprocess
from typing import List, Dict, Any
import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib
from ..plugin_base import PluginBase
from ..result import Result
import utils.icons as icons

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
                "action": self.shutdown
            },
            "restart": {
                "description": "Restart the system",
                "icon": icons.reboot,
                "action": self.restart
            },
            "sleep": {
                "description": "Put system to sleep",
                "icon": icons.suspend,
                "action": self.sleep
            },
            "lock": {
                "description": "Lock the screen",
                "icon": icons.lock,
                "action": self.lock
            },
            "suspend": {
                "description": "Suspend the system",
                "icon": icons.suspend,
                "action": self.suspend
            },
            "logout": {
                "description": "Logout from current session",
                "icon": icons.logout,
                "action": self.logout
            }
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
                    data={"command": cmd}
                )
                results.append(result)

        return results

    def shutdown(self) -> None:
        """Shutdown the system"""
        subprocess.run(["shutdown", "now"])

    def restart(self) -> None:
        """Restart the system"""
        subprocess.run(["shutdown", "-r", "now"])

    def sleep(self) -> None:
        """Put system to sleep"""
        subprocess.run(["systemctl", "suspend"])

    def lock(self) -> None:
        """Lock the screen using hyprlock"""
        subprocess.run(["hyprlock"])

    def suspend(self) -> None:
        """Suspend the system"""
        subprocess.run(["systemctl", "suspend"])

    def logout(self) -> None:
        """Logout from current session"""
        subprocess.run(["loginctl", "terminate-session", os.environ.get("XDG_SESSION_ID")]) 