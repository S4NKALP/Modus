import json
import os

import gi
from fabric.utils.helpers import get_relative_path
from gi.repository import Gdk, GLib

gi.require_version("Gtk", "3.0")

APP_NAME = "modus"
APP_NAME_CAP = "Modus"


def parse_timeout_string(timeout_str):
    """
    Parse timeout string in format like '5s', '10m', '30s' etc.
    Returns timeout in milliseconds.
    """
    if not timeout_str or not isinstance(timeout_str, str):
        return 5000

    timeout_str = timeout_str.strip().lower()

    if timeout_str.endswith("s"):
        try:
            seconds = int(timeout_str[:-1])
            return seconds * 1000
        except ValueError:
            return 5000
    elif timeout_str.endswith("m"):
        try:
            minutes = int(timeout_str[:-1])
            return minutes * 60 * 1000
        except ValueError:
            return 5000
    else:
        try:
            seconds = int(timeout_str)
            return seconds * 1000
        except ValueError:
            return 5000


CACHE_DIR = str(GLib.get_user_cache_dir()) + f"/{APP_NAME}"

USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename
HOME_DIR = os.path.expanduser("~")

CONFIG_DIR = os.path.expanduser(f"~/.config/{APP_NAME}")

screen = Gdk.Screen.get_default()
CURRENT_WIDTH = screen.get_width()
CURRENT_HEIGHT = screen.get_height()


WALLPAPERS_DIR_DEFAULT = get_relative_path("../assets/wallpapers_example/")
CONFIG_FILE = get_relative_path("../config/assets/config.json")
MATUGEN_STATE_FILE = os.path.join(CONFIG_DIR, "matugen")


def load_config():
    """Load the configuration from config.json"""
    config = {}

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")

    return config


if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    wallpapers_dir_from_config = config.get("wallpapers_dir", WALLPAPERS_DIR_DEFAULT)
    WALLPAPERS_DIR = os.path.expanduser(wallpapers_dir_from_config)
    DOCK_POSITION = config.get("dock_position", "Bottom")
    TERMINAL_COMMAND = config.get("terminal_command", "kitty -e")
    DOCK_ENABLED = config.get("dock_enabled", True)
    DOCK_AUTO_HIDE = config.get("dock_auto_hide", True)
    DOCK_ALWAYS_OCCLUDED = config.get("dock_always_occluded", False)
    DOCK_ICON_SIZE = config.get("dock_icon_size", 60)
    WINDOW_SWITCHER_ITEMS_PER_ROW = config.get("window_switcher_items_per_row", 10)
    HIDE_SPECIAL_WORKSPACE = config.get("hide_special_workspace", True)
    DOCK_HIDE_SPECIAL_WORKSPACE_APPS = config.get(
        "dock_hide_special_workspace_apps", True
    )

    NOTIFICATION_TIMEOUT_STR = config.get("notification_timeout", "5s")
    NOTIFICATION_TIMEOUT = parse_timeout_string(NOTIFICATION_TIMEOUT_STR)
    NOTIFICATION_IGNORED_APPS_HISTORY = config.get(
        "notification_ignored_apps_history", ["Hyprshot"]
    )
    NOTIFICATION_LIMITED_APPS_HISTORY = config.get(
        "notification_limited_apps_history", ["Spotify"]
    )

else:
    WALLPAPERS_DIR = WALLPAPERS_DIR_DEFAULT
    DOCK_POSITION = "Bottom"
    DOCK_ENABLED = True
    DOCK_ALWAYS_OCCLUDED = False
    DOCK_AUTO_HIDE = True
    TERMINAL_COMMAND = "kitty -e"
    DOCK_THEME = "Pills"
    DOCK_ICON_SIZE = 60
    WINDOW_SWITCHER_ITEMS_PER_ROW = 10
    HIDE_SPECIAL_WORKSPACE = True
    DOCK_HIDE_SPECIAL_WORKSPACE_APPS = True

    NOTIFICATION_TIMEOUT_STR = "5s"
    NOTIFICATION_TIMEOUT = parse_timeout_string(NOTIFICATION_TIMEOUT_STR)
    NOTIFICATION_IGNORED_APPS_HISTORY = ["Hyprshot"]
    NOTIFICATION_LIMITED_APPS_HISTORY = ["Spotify"]
