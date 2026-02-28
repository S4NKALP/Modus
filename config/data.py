import json

from fabric.utils import Gdk, GLib, get_relative_path, os

from services.config import start_config_service
from utils.functions import parse_timeout_string

APP_NAME = "modus1"
APP_NAME_CAP = "Modus"


CACHE_DIR = str(GLib.get_user_cache_dir()) + f"/{APP_NAME}"
USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename
HOME_DIR = GLib.get_home_dir()

CONFIG_DIR = os.path.expanduser(f"~/.config/{APP_NAME}")

screen = Gdk.Screen.get_default()
CURRENT_WIDTH = screen.get_width()
CURRENT_HEIGHT = screen.get_height()


WALLPAPERS_DIR_DEFAULT = get_relative_path("../assets/wallpapers_example/")
CONFIG_FILE = get_relative_path("../config.json")
MATUGEN_STATE_FILE = os.path.join(CONFIG_DIR, "matugen")


def load_config():
    """Load the configuration from config.json"""
    try:
        service = start_config_service()
        return service.get_all()
    except ImportError:
        # Fallback to direct file loading
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

    PANEL_COMPONENTS_VISIBILITY = {
        "imac_button": config.get("imac_button_visible", True),
        "systray": config.get("systray_visible", True),
        "control_center": config.get("control_center_visible", True),
        "search": config.get("search_visible", True),
        "global_menu": config.get("global_menu_visible", True),
        "network": config.get("network_visible", True),
        "battery": config.get("battery_visible", True),
        "notification_center": config.get("notification_center_visible", True),
        "workspace_indicator": config.get("workspace_indicator_visible", True),
        "bluetooth": config.get("bluetooth_visible", True),
        "date_time": config.get("date_time_visible", True),
    }

else:
    WALLPAPERS_DIR = WALLPAPERS_DIR_DEFAULT
    DOCK_POSITION = "Bottom"
    DOCK_ENABLED = True
    DOCK_ALWAYS_OCCLUDED = False
    DOCK_AUTO_HIDE = True
    DOCK_ICON_SIZE = 52
    WINDOW_SWITCHER_ITEMS_PER_ROW = 10
    HIDE_SPECIAL_WORKSPACE = True
    DOCK_HIDE_SPECIAL_WORKSPACE_APPS = True

    NOTIFICATION_TIMEOUT_STR = "5s"
    NOTIFICATION_TIMEOUT = parse_timeout_string(NOTIFICATION_TIMEOUT_STR)
    NOTIFICATION_IGNORED_APPS_HISTORY = ["Hyprshot"]
    NOTIFICATION_LIMITED_APPS_HISTORY = ["Spotify"]

    PANEL_COMPONENTS_VISIBILITY = {
        "imac_button": True,
        "systray": True,
        "control_center": True,
        "search": True,
        "global_menu": True,
        "network": True,
        "battery": True,
        "notification_center": True,
        "workspace_indicator": True,
        "bluetooth": True,
        "date_time": True,
    }
