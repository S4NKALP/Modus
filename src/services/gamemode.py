"""
Hyprland Game Mode Toggle Script

This script toggles game mode in Hyprland by disabling/enabling animations
and other visual effects for better performance during gaming.

Uses a marker file in /tmp to track state.
"""

import subprocess
import sys
from datetime import datetime
from typing import Literal

from utils.functions import read_json_file, write_json_file

STATE_FILE = "/tmp/hyprland_gamemode"


def run_hyprctl(command: str) -> str:
    """Run a hyprctl command and return the output (raises on error)."""
    result = subprocess.run(
        ["hyprctl"] + command.split(), capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def check_gamemode() -> Literal["t", "f"]:
    """Check if game mode is active."""
    state = read_json_file(STATE_FILE)
    return "t" if state and state.get("enabled") else "f"


def enable_gamemode():
    """Enable game mode by disabling visual effects."""
    batch_commands = [
        "keyword animations:enabled 0",
        "keyword decoration:shadow:enabled 0",
        "keyword decoration:blur:enabled 0",
        "keyword general:gaps_in 0",
        "keyword general:gaps_out 0",
        "keyword general:border_size 1",
        "keyword decoration:rounding 0",
    ]
    run_hyprctl(f'--batch "{"; ".join(batch_commands)}"')

    state = {
        "enabled": True,
        "last_toggled": datetime.now().isoformat(timespec="seconds"),
    }
    write_json_file(state, STATE_FILE)
    print("Game mode enabled - visual effects disabled for better performance")


def disable_gamemode():
    """Disable game mode by reloading Hyprland configuration."""
    run_hyprctl("reload")

    state = {
        "enabled": False,
        "last_toggled": datetime.now().isoformat(timespec="seconds"),
    }
    write_json_file(state, STATE_FILE)
    print("Game mode disabled - visual effects restored")


def toggle_gamemode():
    """Toggle game mode state using JSON file."""
    state = read_json_file(STATE_FILE) or {}
    if state.get("enabled"):
        disable_gamemode()
    else:
        enable_gamemode()


def print_usage():
    print("Usage:")
    print("  gamemode check    - Check if game mode is active (t/f)")
    print("  gamemode toggle   - Toggle game mode")


def main():
    if len(sys.argv) < 2:
        toggle_gamemode()
        return

    command = sys.argv[1].lower()

    if command == "check":
        print(check_gamemode())
    elif command == "toggle":
        toggle_gamemode()
    elif command in ["help", "-h", "--help"]:
        print_usage()
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
