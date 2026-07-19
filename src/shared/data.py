from fabric.utils import GLib, get_relative_path, logger, os

from utils.functions import parse_timeout_string
from utils.gtk_utils import toml_file

HOME_DIR = GLib.get_home_dir()
APP_NAME = "modus"

CACHE_DIR = str(GLib.get_user_cache_dir()) + f"/{APP_NAME}"

CONFIG_DIR = os.path.expanduser(f"~/.config/{APP_NAME}")

SYSTEM_CACHE_DIR = GLib.get_user_cache_dir()


_PROJECT_ROOT = str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent)


def _get_wallpaper_path() -> str:
    try:
        from services.config import get_config

        custom = get_config("wallpapers_dir")
        if custom:
            expanded = os.path.expanduser(str(custom))
            if not os.path.isabs(expanded):
                expanded = os.path.join(_PROJECT_ROOT, expanded)
            return expanded
    except Exception as e:
        logger.warning(f"[data] Failed to load wallpapers_dir from config: {e}")
    return f"{HOME_DIR}/Pictures/Wallpapers"


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
