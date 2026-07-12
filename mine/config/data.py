from fabric.utils import Gdk, GLib, get_relative_path, logger, os

from utils.constants import DEFAULT
from utils.functions import read_json_file, write_json_file

APP_NAME = "modus"
APP_NAME_CAP = "Modus"
HOME_DIR = GLib.get_home_dir()

CACHE_DIR = f"{GLib.get_user_cache_dir()}/{APP_NAME}"
os.makedirs(CACHE_DIR, exist_ok=True)
ICON_CACHE_FILE = f"{CACHE_DIR}/icons.json"
CONFIG_FILE = get_relative_path("../config.json")

SYSTEM_CACHE_DIR = GLib.get_user_cache_dir()
WALLPAPER_PATH = f"{HOME_DIR}/Pictures/Wallpapers"
WALLPAPER_THUMBS_PATH = f"{WALLPAPER_PATH}/.thumbnails"
WALLPAPERS_THUMBNAILS_SIZE = 200

RECENT_EMOJIS_FILE = f"{CACHE_DIR}/recent_emojis.json"

# Matugen template and output paths
MATUGEN_TEMPLATE_PATH = get_relative_path("../config/matugen/templates/modus.css")
MATUGEN_OUTPUT_PATH = get_relative_path("../styles/colors.css")

CLIPBOARD_THUMBS_DIR = f"{GLib.get_user_cache_dir()}/{APP_NAME}/clipboard_thumbs"
CLIPBOARD_DB_PATH = f"{GLib.get_user_cache_dir()}/cliphist/db"

plugins = f"{GLib.get_user_state_dir()}/{APP_NAME}"

screen = Gdk.Screen.get_default()
CURRENT_WIDTH = screen.get_width()
CURRENT_HEIGHT = screen.get_height()


def generate_default_config():
    """Generate default config.json file if it doesn't exist"""
    if not os.path.exists(CONFIG_FILE):
        write_json_file(DEFAULT, CONFIG_FILE)
        logger.success("Config file generated successfully")


def DATA():
    config = read_json_file(CONFIG_FILE) or {}
    debug = config.get("debug", {})
    panel = config.get("panel", {})
    corners = config.get("corners", {})
    wallpaper_dir = config.get("wallpaper_dir", {})
    osd = config.get("osd", {})
    notifications = config.get("notifications", {})
    keyboard_layout = config.get("keyboard_layout", {})

    return {
        "debug": debug.get("enabled"),
        "wallpaper_dir": wallpaper_dir.get("path"),
        "corners": corners.get("enabled"),
        "panel_enabled": panel.get("enabled"),
        "panel_autohide": panel.get("autohide"),
        "panel_position": panel.get("position"),
        "systray": panel.get("systray", {}).get("enabled"),
        "systray_hide_icons": panel.get("systray", {}).get("hide_items", []),
        "datetime": panel.get("datetime", {}).get("enabled"),
        "datetime_12hrs": panel.get("datetime", {}).get("12hrs"),
        "battery": panel.get("battery", {}).get("enabled"),
        "battery_label": panel.get("battery", {}).get("label"),
        "battery_hide_on_full": panel.get("battery", {}).get("hide_on_full"),
        "battery_icon_size": panel.get("battery", {}).get("icon_size", 16),
        "network": panel.get("network", {}).get("enabled"),
        "bluetooth": panel.get("bluetooth", {}).get("enabled"),
        "workspace": panel.get("workspace", {}).get("enabled"),
        "workspace_hide_special": panel.get("workspace", {}).get("hide_special_ws"),
        "taskbar": panel.get("taskbar", {}).get("enabled"),
        "taskbar_icon_size": panel.get("taskbar", {}).get("icon_size"),
        "taskbar_hide_empty": panel.get("taskbar", {}).get("hide_empty"),
        "taskbar_hide_special": panel.get("taskbar", {}).get("hide_special"),
        "taskbar_group_apps": panel.get("taskbar", {}).get("group_apps"),
        "osd": osd.get("enabled"),
        "osd_audio": osd.get("audio"),
        "osd_brightness": osd.get("brightness"),
        "osd_capslock": osd.get("capslock"),
        "osd_kb_layout": osd.get("kb_layout"),
        "osd_network": osd.get("network"),
        "osd_microphone": osd.get("microphone"),
        "osd_battery": osd.get("battery"),
        "osd_cooldown_ms": osd.get("cooldown_ms"),
        "osd_position": osd.get("position"),
        "notifications": notifications.get("enabled"),
        "notifications_timeout": notifications.get("timeout"),
        "notifications_image_size": notifications.get("image_size"),
        "notifications_width": notifications.get("width"),
        "notifications_buttons_per_row": notifications.get("buttons_per_row"),
        "notifications_enabled": notifications.get("enabled"),
        "notifications_corner_size": notifications.get("corner_size"),
        "notifications_revealer_duration": notifications.get("revealer_duration"),
        "keyboard_layouts": keyboard_layout.get("layouts", ["us", "np"]),
    }


def update_setting(key: str, value) -> bool:
    """Update a specific setting in config.json."""
    config = read_json_file(CONFIG_FILE) or {}
    key_map = {
        "osd": ("osd", "enabled"),
        "osd_position": ("osd", "position"),
        "osd_audio": ("osd", "audio"),
        "osd_brightness": ("osd", "brightness"),
        "osd_capslock": ("osd", "capslock"),
        "osd_kb_layout": ("osd", "kb_layout"),
        "osd_network": ("osd", "network"),
        "osd_microphone": ("osd", "microphone"),
        "osd_battery": ("osd", "battery"),
        "panel_enabled": ("panel", "enabled"),
        "panel_position": ("panel", "position"),
        "panel_autohide": ("panel", "autohide"),
        "systray": ("panel", "systray", "enabled"),
        "systray_hide_icons": ("panel", "systray", "hide_items"),
        "network": ("panel", "network", "enabled"),
        "bluetooth": ("panel", "bluetooth", "enabled"),
        "datetime": ("panel", "datetime", "enabled"),
        "datetime_12hrs": ("panel", "datetime", "12hrs"),
        "battery": ("panel", "battery", "enabled"),
        "battery_label": ("panel", "battery", "label"),
        "battery_hide_on_full": ("panel", "battery", "hide_on_full"),
        "workspace": ("panel", "workspace", "enabled"),
        "workspace_hide_special": ("panel", "workspace", "hide_special_ws"),
        "taskbar": ("panel", "taskbar", "enabled"),
        "taskbar_hide_empty": ("panel", "taskbar", "hide_empty"),
        "notifications": ("notifications", "enabled"),
        "wallpaper_dir": ("wallpaper_dir", "path"),
        "corners": ("corners", "enabled"),
        "debug": ("debug", "enabled"),
    }

    if key not in key_map:
        logger.warning(f"Unknown setting key: {key}")
        return False

    path = key_map[key]
    if len(path) == 2:
        if path[0] not in config:
            config[path[0]] = {}
        config[path[0]][path[1]] = value
    elif len(path) == 3:
        if path[0] not in config:
            config[path[0]] = {}
        if path[1] not in config[path[0]]:
            config[path[0]][path[1]] = {}
        config[path[0]][path[1]][path[2]] = value

    write_json_file(config, CONFIG_FILE)
    return True
