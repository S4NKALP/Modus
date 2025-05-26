import os
import json
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib

from fabric.utils import get_relative_path

APP_NAME = "modus"
APP_NAME_CAP = "Modus"

CACHE_DIR = str(GLib.get_user_cache_dir()) + f"/{APP_NAME}"
STATE_DIR = str(GLib.get_user_state_dir() + f"/{APP_NAME}")


USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename
HOME_DIR = os.path.expanduser("~")

CONFIG_DIR = os.path.expanduser(f"~/{APP_NAME}")

screen = Gdk.Screen.get_default()
CURRENT_WIDTH = screen.get_width()
CURRENT_HEIGHT = screen.get_height()

WALLPAPERS_DIR_DEFAULT = get_relative_path("../assets/wallpaper")
MATUGEN_STATE_FILE = os.path.join(CONFIG_DIR, "matugen")
CONFIG_FILE = get_relative_path("../config/assets/config.json")

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    WALLPAPERS_DIR = config.get("wallpapers_dir", WALLPAPERS_DIR_DEFAULT)
    VERTICAL = config.get("vertical", False)  # Use saved value or False as default
    VERTICAL_RIGHT_ALIGN = config.get("vertical_right_align", False)  # Right side by default
    BOTTOM_BAR = config.get("bottom_bar", False)  # Use saved value or False as default
    CENTERED_BAR = config.get("centered_bar", False)  # Load centered bar setting
    TERMINAL_COMMAND = config.get(
        "terminal_command", "kitty -e"
    )  # Load terminal command
    DOCK_ENABLED = config.get("dock_enabled", True)  # Load dock visibility setting
    DOCK_ALWAYS_OCCLUDED = config.get(
        "dock_always_occluded", False
    )  # Load dock hover-only setting
    DOCK_ICON_SIZE = config.get("dock_icon_size", 28)  # Load dock icon size setting
    OSD_ENABLED = config.get("osd_enabled", True)  # Load OSD visibility setting

    # Load bar component visibility settings
    BAR_COMPONENTS_VISIBILITY = {
        "button_app": config.get("bar_button_app_visible", True),
        "tray": config.get("bar_tray_visible", True),
        # "button_tools": config.get("bar_button_tools_visible", True),
        "workspaces": config.get("bar_workspaes_visible", True),
        "metrics": config.get("bar_metrics_visible", True),
        "language": config.get("bar_language_visible", True),
        "date_time": config.get("bar_date_time_visible", True),
        "updates": config.get("bar_updates_visible", True),
        "indicators": config.get("bar_indicators", True),
    }

    BAR_METRICS_DISKS = config.get("bar_metrics_disks", ["/"])
    METRICS_VISIBLE = config.get(
        "metrics_visible",
        {"cpu": True, "ram": True, "disk": True, "swap": True},
    )
else:
    WALLPAPERS_DIR = WALLPAPERS_DIR_DEFAULT
    VERTICAL = False  # Default value when no config exists
    VERTICAL_RIGHT_ALIGN = False  # Default to right alignment
    BOTTOM_BAR = False  # Default value for bottom bar
    CENTERED_BAR = False  # Default value for centered bar
    DOCK_ENABLED = True  # Default value for dock visibility
    DOCK_ALWAYS_OCCLUDED = False  # Default value for dock hover-only mode
    OSD_ENABLED = True  # Default value for OSD visibility
    TERMINAL_COMMAND = "kitty -e"  # Default terminal command when no config
    DOCK_ICON_SIZE = 28  # Default dock icon size when no config

    # Default values for component visibility (all visible)
    BAR_COMPONENTS_VISIBILITY = {
        "button_aps": True,
        "tray": True,
        # "button_tools": True,
        "workspaces": True,
        "metrics": True,
        "language": True,
        "date_time": True,
        "indicators": True,
        "updates": True,
    }

    BAR_METRICS_DISKS = ["/"]
    METRICS_VISIBLE = {
        "cpu": True,
        "ram": True,
        "disk": True,
        "swap": True,
    }


def read_config():
    config_path = get_relative_path("./assets/modus.json")

    with open(config_path, "r") as file:
        # Load JSON data into a Python dictionary
        data = json.load(file)
    return data


def load_config():
    """Load the configuration from config.json"""
    config_path = get_relative_path("./assets/config.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
    return config
