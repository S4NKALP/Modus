from gi.repository import Gdk, GLib
from fabric.utils.helpers import get_relative_path
import json
import os

import gi

gi.require_version("Gtk", "3.0")

APP_NAME = "modus"
APP_NAME_CAP = "Modus"


NOTIF_POS_KEY = "notif_pos"
NOTIF_POS_DEFAULT = "Top"

CACHE_DIR = str(GLib.get_user_cache_dir()) + f"/{APP_NAME}"

USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename
HOME_DIR = os.path.expanduser("~")

CONFIG_DIR = os.path.expanduser(f"~/{APP_NAME}")

screen = Gdk.Screen.get_default()
CURRENT_WIDTH = screen.get_width()
CURRENT_HEIGHT = screen.get_height()


WALLPAPERS_DIR_DEFAULT = get_relative_path("../assets/wallpapers_example")
CONFIG_FILE = get_relative_path("../config/config.json")
MATUGEN_STATE_FILE = os.path.join(CONFIG_DIR, "matugen")

WORKSPACE_NUMS = False
WORKSPACE_USE_CHINESE_NUMERAL = False
WORKSPACE_DOTS = False

DOCK_THEME = "Pills"


def load_config():
    """Load the configuration from config.json"""
    config_path = os.path.expanduser(f"~/{APP_NAME_CAP}/config/config.json")
    config = {}

    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")

    return config


if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    WALLPAPERS_DIR = config.get("wallpapers_dir", WALLPAPERS_DIR_DEFAULT)
    DOCK_POSITION = config.get("dock_position", "Bottom")
    VERTICAL = DOCK_POSITION in ["Left", "Right"]
    TERMINAL_COMMAND = config.get("terminal_command", "kitty -e")
    DOCK_ENABLED = config.get("dock_enabled", True)
    DOCK_AUTO_HIDE = config.get("dock_auto_hide", True)
    DOCK_ALWAYS_OCCLUDED = config.get("dock_always_occluded", False)
    DOCK_THEME = config.get("dock_theme", "Pills")
    DOCK_ICON_SIZE = config.get("dock_icon_size", 20)
    WORKSPACE_NUMS = config.get("workspace_nums", False)
    WORKSPACE_USE_CHINESE_NUMERAL = config.get("workspace_use_chinese_numerals", False)
    WORKSPACE_DOTS = config.get("workspace_dots", False)

    NOTIF_POS = config.get(NOTIF_POS_KEY, NOTIF_POS_DEFAULT)

    DOCK_COMPONENTS_VISIBILITY = {
        "workspaces": config.get("dock_workspaces_visible", True),
        "metrics": config.get("dock_metrics_visible", True),
        "battery": config.get("dock_battery_visible", True),
        "date_time": config.get("dock_date_time_visible", True),
        "controls": config.get("dock_controls_visible", True),
        "indicators": config.get("dock_indicators_visible", True),
        "systray": config.get("dock_tray_visible", True),
        "applications": config.get("dock_applications_visible", True),
        "music_player": config.get("dock_music_player_visible", True),
    }

    METRICS_DISKS = config.get("metrics_disks", ["/"])
    METRICS_VISIBLE = config.get(
        "metrics_visible",
        {"cpu": True, "ram": True, "disk": True, "swap": True, "gpu": False},
    )
else:
    WALLPAPERS_DIR = WALLPAPERS_DIR_DEFAULT
    DOCK_POSITION = "Bottom"
    VERTICAL = False
    DOCK_ENABLED = True
    DOCK_ALWAYS_OCCLUDED = False
    DOCK_AUTO_HIDE = True
    TERMINAL_COMMAND = "kitty -e"
    DOCK_THEME = "Pills"
    DOCK_ICON_SIZE = 20

    NOTIF_POS = NOTIF_POS_DEFAULT

    DOCK_COMPONENTS_VISIBILITY = {
        "workspaces": True,
        "metrics": True,
        "battery": True,
        "date_time": True,
        "controls": True,
        "indicators": True,
        "systray": True,
        "applications": True,
        "music_player": True,
    }

    METRICS_DISKS = ["/"]
    METRICS_VISIBLE = {
        "cpu": True,
        "ram": True,
        "disk": True,
        "swap": True,
        "gpu": False,
    }
