from fabric.utils import GLib, get_relative_path, logger, os

from utils.functions import parse_timeout_string
from utils.utils import toml_file

HOME_DIR = GLib.get_home_dir()
APP_NAME = "modus1"

CACHE_DIR = str(GLib.get_user_cache_dir()) + f"/{APP_NAME}"

CONFIG_DIR = os.path.expanduser(f"~/.config/{APP_NAME}")

SYSTEM_CACHE_DIR = GLib.get_user_cache_dir()
WALLPAPER_PATH = f"{HOME_DIR}/Pictures/Wallpapers"
WALLPAPER_THUMBS_PATH = f"{WALLPAPER_PATH}/.thumbnails"
WALLPAPERS_THUMBNAILS_SIZE = 200
WALLPAPERS_DIR_DEFAULT = get_relative_path("../assets/wallpapers_example/")

CONFIG_FILE = toml_file("config.toml")


CLIPBOARD_THUMBS_DIR = f"{GLib.get_user_cache_dir()}/{APP_NAME}/clipboard_thumbs"
CLIPBOARD_DB_PATH = f"{GLib.get_user_cache_dir()}/cliphist/db"


def load_config():
    """Load the configuration from config.toml"""
    try:
        from services.config import start_config_service

        service = start_config_service()
        return service.get_all()
    except ImportError:
        # Fallback to direct file loading
        config = {}

        if os.path.exists(CONFIG_FILE):
            try:
                import tomlkit

                with open(CONFIG_FILE) as f:
                    config = dict(tomlkit.load(f))
            except Exception as e:
                logger.error(f"Error loading config: {e}")

        return config


NOTIFICATION_TIMEOUT_STR = "5s"
NOTIFICATION_TIMEOUT = parse_timeout_string(NOTIFICATION_TIMEOUT_STR)
NOTIFICATION_IGNORED_APPS_HISTORY = ["Hyprshot"]
NOTIFICATION_LIMITED_APPS_HISTORY = ["Spotify"]
