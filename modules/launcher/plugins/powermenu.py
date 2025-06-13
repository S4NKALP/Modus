import subprocess
from typing import List, Dict, Any

import utils.icons as icons
from . import LauncherPlugin


class PowerMenuPlugin(LauncherPlugin):
    """Plugin for system power management functionality"""

    @property
    def name(self) -> str:
        return "Power Menu"

    @property
    def category(self) -> str:
        return "System"

    @property
    def icon_name(self) -> str:
        return "system-shutdown-symbolic"

    def search(self, query: str) -> List[Dict[str, Any]]:
        if not query:
            return []

        query_lower = query.lower()

        # Show power menu when user types "sys", "system", "power", etc.
        power_triggers = ["sys", "system", "power", "shutdown", "restart", "reboot", "logout", "suspend", "sleep", "lock"]
        
        if any(query_lower.startswith(trigger) for trigger in power_triggers):
            return self._get_power_options(query_lower)

        return []

    def _get_power_options(self, query: str = "") -> List[Dict[str, Any]]:
        """Get available power management options"""
        power_options = [
            {
                "title": "Shutdown",
                "description": "Turn off the computer completely",
                "icon_markup": icons.shutdown,
                "action": self.shutdown_system,
                "keywords": ["shutdown", "power off", "turn off", "sys", "halt"],
            },
            {
                "title": "Restart",
                "description": "Restart the computer",
                "icon_markup": icons.reboot,
                "action": self.restart_system,
                "keywords": ["restart", "reboot", "sys"],
            },
            {
                "title": "Logout",
                "description": "End current user session",
                "icon_markup": icons.logout,
                "action": self.logout_session,
                "keywords": ["logout", "sign out", "end session", "sys"],
            },
            {
                "title": "Suspend",
                "description": "Suspend to RAM (sleep mode)",
                "icon_markup": icons.suspend,
                "action": self.suspend_system,
                "keywords": ["suspend", "sleep", "sys"],
            },
            {
                "title": "Lock Screen",
                "description": "Lock the current session",
                "icon_markup": icons.lock,
                "action": self.lock_screen,
                "keywords": ["lock", "lock screen", "sys"],
            },
        ]

        # Filter options based on query if it's more specific
        if len(query) > 3:  # More than just "sys"
            filtered_options = []
            for option in power_options:
                # Check if query matches any keywords
                if any(query in keyword for keyword in option["keywords"]):
                    filtered_options.append(option)
            
            if filtered_options:
                power_options = filtered_options

        # Convert to launcher result format
        results = []
        for option in power_options:
            results.append({
                "title": option["title"],
                "description": option["description"],
                "icon_markup": option["icon_markup"],  # Use markup for custom icons
                "action": option["action"],
                "power_option": True,  # Mark as power option for special handling
            })

        return results

    def shutdown_system(self):
        """Shutdown the system"""
        print("Initiating system shutdown...")
        try:
            # Try systemctl first (systemd)
            subprocess.run(["systemctl", "poweroff"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                # Fallback to shutdown command
                subprocess.run(["shutdown", "-h", "now"], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("Could not shutdown system - no suitable command found")

    def restart_system(self):
        """Restart the system"""
        print("Initiating system restart...")
        try:
            # Try systemctl first (systemd)
            subprocess.run(["systemctl", "reboot"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                # Fallback to shutdown command
                subprocess.run(["shutdown", "-r", "now"], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("Could not restart system - no suitable command found")

    def logout_session(self):
        """Logout from current session"""
        try:
            # Try different logout methods based on desktop environment
            # Hyprland
            subprocess.run(["hyprctl", "dispatch", "exit"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                # GNOME
                subprocess.run(["gnome-session-quit", "--logout", "--no-prompt"], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                try:
                    # KDE
                    subprocess.run(["qdbus", "org.kde.ksmserver", "/KSMServer", "logout", "0", "0", "0"], check=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    try:
                        # Generic X11
                        subprocess.run(["pkill", "-KILL", "-u", subprocess.getoutput("whoami")], check=True)
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        print("Could not logout - no suitable method found")

    def suspend_system(self):
        """Suspend the system"""
        try:
            # Try systemctl first (systemd)
            subprocess.run(["systemctl", "suspend"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                # Fallback to pm-suspend
                subprocess.run(["pm-suspend"], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("Could not suspend system - no suitable command found")

    def lock_screen(self):
        """Lock the screen"""
        try:
            # Try different lock methods
            # Hyprland
            subprocess.run(["hyprlock"], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                # swaylock (Sway/Wayland)
                subprocess.run(["swaylock"], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                try:
                    # i3lock (X11)
                    subprocess.run(["i3lock"], check=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    try:
                        # GNOME
                        subprocess.run(["gnome-screensaver-command", "--lock"], check=True)
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        try:
                            # KDE
                            subprocess.run(["qdbus", "org.freedesktop.ScreenSaver", "/ScreenSaver", "Lock"], check=True)
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            print("Could not lock screen - no suitable command found")

    def get_action_items(self, query: str) -> List[Dict[str, Any]]:
        """Get quick action items for power management"""
        if not query or len(query) < 2:
            return []

        query_lower = query.lower()
        
        # Show quick actions for system-related queries
        if any(trigger in query_lower for trigger in ["sys", "power", "shutdown", "restart"]):
            return [
                {
                    "title": f'System power options for "{query}"',
                    "icon_name": "system-shutdown-symbolic",
                    "action": lambda: None,  # No specific action needed
                }
            ]

        return []
