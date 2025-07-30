"""
Menu action handlers for the macOS-style menu bar.
This file contains all the implementations for menu item actions.
"""

from fabric.hyprland.service import Hyprland
from fabric.utils import exec_shell_command


class MenuActionHandler:

    def __init__(self):
        pass

    def execute_action(self, action):
        try:
            # Window menu actions
            if action == "Move Window to Left":
                Hyprland.send_command("dispatch movewindow l")
            elif action == "Move Window to Right":
                Hyprland.send_command("dispatch movewindow r")
            elif action == "Cycle Through Windows":
                Hyprland.send_command("dispatch cyclenext")
            elif action == "Float":
                Hyprland.send_command("dispatch togglefloating")
            elif action == "Pseudo":
                Hyprland.send_command("dispatch pseudo")
            elif action == "Center":
                Hyprland.send_command("dispatch centerwindow")
            elif action == "Group":
                Hyprland.send_command("dispatch togglegroup")
            elif action == "Pin":
                Hyprland.send_command("dispatch pin")
            elif action == "Quit":
                Hyprland.send_command("dispatch killactive")

            # Go menu actions
            elif action == "Back":
                Hyprland.send_command("dispatch workspace e-1")
            elif action == "Forward":
                Hyprland.send_command("dispatch workspace e+1")

            # Edit menu actions

            # View menu actions
            elif action == "Full Screen":
                Hyprland.send_command("dispatch fullscreen")
            elif action == "Zoom In":
                exec_shell_command("wtype -k ctrl+plus")
            elif action == "Zoom Out":
                exec_shell_command("wtype -k ctrl+minus")
            elif action == "Actual Size":
                exec_shell_command("wtype -k ctrl+0")

            # Help menu actions
            elif action == "Hyprland Help":
                exec_shell_command("xdg-open https://wiki.hyprland.org/")
            elif action == "Arch Wiki":
                exec_shell_command("xdg-open https://wiki.archlinux.org/")
            elif action == "Report a Bug...":
                exec_shell_command("xdg-open https://github.com/S4NKALP/Modus/issues")

            # System menu actions
            elif action == "About This PC":
                exec_shell_command("gnome-system-monitor")
            elif action == "Force Quit":
                exec_shell_command("gnome-system-monitor")
            elif action == "Shutdown":
                exec_shell_command("systemctl poweroff")
            elif action == "Restart":
                exec_shell_command("systemctl reboot")
            elif action == "Sleep":
                exec_shell_command("systemctl suspend")
            elif action == "Lock":
                exec_shell_command("hyprlock")

            # App menu actions (for hiding apps)
            elif action.startswith("Hide ") and not action == "Hide Others":
                action.replace("Hide ", "")
                Hyprland.send_command("dispatch movetoworkspacesilent special:hidden")
            elif action == "Hide Others":
                Hyprland.send_command(
                    "dispatch movetoworkspacesilent special:hidden,^(activewindow)"
                )
            elif action == "Show All":
                Hyprland.send_command("dispatch movetoworkspace e+0,special:hidden")
            elif action.startswith("Quit "):
                action.replace("Quit ", "")
                Hyprland.send_command("dispatch killactive")
            else:
                print(f"No implementation for action: {action}")
        except Exception as e:
            print(f"Error executing command for '{action}': {e}")
