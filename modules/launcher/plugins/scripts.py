"""
Scripts plugin for the launcher.
Provides access to various system scripts and utilities.
"""

import os
import subprocess
from typing import List

from fabric.utils import exec_shell_command_async
import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class ScriptsPlugin(PluginBase):
    """
    Plugin for executing system scripts and utilities.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Scripts"
        self.description = "System scripts and utilities"

    def initialize(self):
        """Initialize the scripts plugin."""
        self.set_triggers(["script", "scripts", "cmd", "util"])

    def cleanup(self):
        """Cleanup the scripts plugin."""
        pass

    def _check_gamemode_status(self) -> bool:
        """Check if gamemode (animations disabled) is currently active."""
        try:
            # Use the gamemode script's check function
            script_path = self._get_script_path("gamemode.sh")
            result = subprocess.run(
                ["bash", script_path, "check"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                # Script returns "t" for true (gamemode on), "f" for false (gamemode off)
                return result.stdout.strip() == "t"
        except Exception:
            pass
        return False

    def _toggle_gamemode(self):
        """Toggle gamemode using the gamemode script."""
        script_path = self._get_script_path("gamemode.sh")
        exec_shell_command_async(f"bash '{script_path}'")

    def _run_colorpicker(self, format_type: str):
        """Run color picker with specified format."""
        script_path = self._get_script_path("hyprpicker.sh")
        exec_shell_command_async(f"bash '{script_path}' -{format_type}")



    def _reload_css(self):
        """Reload application CSS."""
        exec_shell_command_async("$fabricSend 'app.set_css()'")

    def _restart_modus(self):
        """Restart Modus application."""
        exec_shell_command_async("killall modus; uwsm-app python ~/Modus/main.py")

    def _run_system_command(self, command: str):
        """Run a system command."""
        exec_shell_command_async(command)



    def _toggle_service(self, service_name: str):
        """Toggle a systemd service."""
        exec_shell_command_async(f"systemctl --user is-active {service_name} && systemctl --user stop {service_name} || systemctl --user start {service_name}")

    def _get_script_path(self, script_name: str) -> str:
        """Get the full path to a script from the scripts directory."""
        # Get the current working directory (should be Modus root)
        current_dir = os.getcwd()

        # Try scripts directory relative to current working directory
        script_path = os.path.join(current_dir, "scripts", script_name)
        if os.path.exists(script_path):
            return script_path

        # Try relative to this file's location
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        modus_root = os.path.dirname(os.path.dirname(os.path.dirname(plugin_dir)))
        script_path = os.path.join(modus_root, "scripts", script_name)
        if os.path.exists(script_path):
            return script_path

        # Fallback to relative path
        return f"scripts/{script_name}"

    def query(self, query_string: str) -> List[Result]:
        """Search for script actions based on query."""
        query = query_string.strip().lower()
        results = []

        # Check gamemode status for dynamic display
        gamemode_active = self._check_gamemode_status()
        gamemode_icon = icons.gamemode if gamemode_active else icons.gamemode_off
        gamemode_status = "ON" if gamemode_active else "OFF"

        # Define script actions
        script_actions = {
            # Gamemode
            "gamemode": {
                "title": f"Toggle Gamemode (Currently {gamemode_status})",
                "subtitle": "Toggle Hyprland game mode - disable animations, gaps, and effects",
                "icon": gamemode_icon,
                "action": self._toggle_gamemode,
                "keywords": ["gamemode", "game", "performance", "toggle"],
                "relevance": 1.0
            },

            # Color Picker
            "colorpicker-hex": {
                "title": "Color Picker (HEX)",
                "subtitle": "Pick a color and copy HEX value to clipboard",
                "icon": icons.colorpicker,
                "action": lambda: self._run_colorpicker("hex"),
                "keywords": ["color", "picker", "hex", "colorpicker"],
                "relevance": 0.9
            },
            "colorpicker-rgb": {
                "title": "Color Picker (RGB)",
                "subtitle": "Pick a color and copy RGB value to clipboard",
                "icon": icons.colorpicker,
                "action": lambda: self._run_colorpicker("rgb"),
                "keywords": ["color", "picker", "rgb", "colorpicker"],
                "relevance": 0.9
            },
            "colorpicker-hsv": {
                "title": "Color Picker (HSV)",
                "subtitle": "Pick a color and copy HSV value to clipboard",
                "icon": icons.colorpicker,
                "action": lambda: self._run_colorpicker("hsv"),
                "keywords": ["color", "picker", "hsv", "colorpicker"],
                "relevance": 0.9
            },



            # System Controls
            "reload-css": {
                "title": "Reload CSS",
                "subtitle": "Reload application stylesheets",
                "icon": icons.reload,
                "action": self._reload_css,
                "keywords": ["reload", "css", "style", "stylesheet"],
                "relevance": 0.6
            },
            "restart-modus": {
                "title": "Restart Modus",
                "subtitle": "Restart the Modus application",
                "icon": icons.reload,
                "action": self._restart_modus,
                "keywords": ["restart", "modus", "reload", "reboot"],
                "relevance": 0.6
            },



            # System Utilities
            "kill-all": {
                "title": "Kill All Processes",
                "subtitle": "Kill all user processes (useful for cleanup)",
                "icon": icons.close,
                "action": lambda: self._run_system_command("killall -u $USER"),
                "keywords": ["kill", "killall", "processes", "cleanup"],
                "relevance": 0.5
            },
            "clear-cache": {
                "title": "Clear Cache",
                "subtitle": "Clear system and user cache directories",
                "icon": icons.trash,
                "action": lambda: self._run_system_command("rm -rf ~/.cache/* /tmp/*"),
                "keywords": ["clear", "cache", "clean", "tmp", "cleanup"],
                "relevance": 0.5
            },


            # Night Light / Blue Light Filter
            "night-light": {
                "title": "Toggle Night Light",
                "subtitle": "Toggle blue light filter for eye comfort",
                "icon": icons.night,
                "action": lambda: self._run_system_command("hyprctl keyword decoration:screen_shader ~/.config/hypr/shaders/blue_light_filter.glsl"),
                "keywords": ["night", "light", "blue", "filter", "eye", "comfort"],
                "relevance": 0.6
            },

            # Clipboard
            "clear-clipboard": {
                "title": "Clear Clipboard",
                "subtitle": "Clear clipboard contents",
                "icon": icons.clipboard,
                "action": lambda: self._run_system_command("wl-copy --clear"),
                "keywords": ["clipboard", "clear", "empty"],
                "relevance": 0.5
            },
        }

        # If no query, show all actions
        if not query:
            for action_id, action_data in script_actions.items():
                results.append(Result(
                    title=action_data["title"],
                    subtitle=action_data["subtitle"],
                    icon_markup=action_data["icon"],
                    action=action_data["action"],
                    relevance=action_data["relevance"],
                    plugin_name=self.display_name,
                    data={"action_id": action_id}
                ))
        else:
            # Search through actions
            for action_id, action_data in script_actions.items():
                relevance = self._calculate_relevance(query, action_data["keywords"], action_data["title"])
                if relevance > 0:
                    results.append(Result(
                        title=action_data["title"],
                        subtitle=action_data["subtitle"],
                        icon_markup=action_data["icon"],
                        action=action_data["action"],
                        relevance=relevance,
                        plugin_name=self.display_name,
                        data={"action_id": action_id}
                    ))

        return sorted(results, key=lambda x: x.relevance, reverse=True)

    def _calculate_relevance(self, query: str, keywords: List[str], title: str) -> float:
        """Calculate relevance score for a script action."""
        query_lower = query.lower()
        title_lower = title.lower()

        # Check for exact matches in keywords
        for keyword in keywords:
            if query_lower == keyword.lower():
                return 1.0

        # Check if query starts with any keyword
        for keyword in keywords:
            if keyword.lower().startswith(query_lower):
                return 0.9

        # Check if title contains query
        if query_lower in title_lower:
            return 0.8

        # Check if any keyword contains query
        for keyword in keywords:
            if query_lower in keyword.lower():
                return 0.7

        return 0.0
