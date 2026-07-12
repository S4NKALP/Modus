"""
Hyprland Game Mode Toggle Script

This script toggles game mode in Hyprland by disabling/enabling animations
and other visual effects for better performance during gaming.

Uses a marker file in /tmp to track state.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

import tomlkit

from utils.functions import run_command

STATE_FILE = Path("/tmp/hyprland_gamemode.toml")


def run_hyprctl(command: str) -> str:
    """Run a hyprctl command and return the output (raises on error)."""
    result = run_command(["hyprctl", *command.split()], timeout=5)
    if result.returncode != 0:
        raise RuntimeError(f"hyprctl failed: {result.stderr}")
    return result.stdout.strip()


def _read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE) as f:
            data = tomlkit.load(f)
        return dict(data) if data else {}
    except Exception:
        return {}


def _write_state(data: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.document()
    for k, v in data.items():
        doc[k] = v
    with open(STATE_FILE, "w") as f:
        tomlkit.dump(doc, f)


def check_gamemode() -> Literal["t", "f"]:
    """Check if game mode is active."""
    state = _read_state()
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

    _write_state(
        {
            "enabled": True,
            "last_toggled": datetime.now().isoformat(timespec="seconds"),
        }
    )
    print("Game mode enabled - visual effects disabled for better performance")


def disable_gamemode():
    """Disable game mode by reloading Hyprland configuration."""
    run_hyprctl("reload")

    _write_state(
        {
            "enabled": False,
            "last_toggled": datetime.now().isoformat(timespec="seconds"),
        }
    )
    print("Game mode disabled - visual effects restored")


def toggle_gamemode():
    """Toggle game mode state."""
    state = _read_state()
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
