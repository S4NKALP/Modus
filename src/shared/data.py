from fabric.utils import logger

from fabric.utils import GLib, get_relative_path, os

from utils.functions import parse_timeout_string
from utils.utils import toml_file

APP_NAME = "modus1"

CACHE_DIR = str(GLib.get_user_cache_dir()) + f"/{APP_NAME}"

CONFIG_DIR = os.path.expanduser(f"~/.config/{APP_NAME}")

WALLPAPERS_DIR_DEFAULT = get_relative_path("../assets/wallpapers_example/")
CONFIG_FILE = toml_file("config.toml")


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

                with open(CONFIG_FILE, "r") as f:
                    config = dict(tomlkit.load(f))
            except Exception as e:
                logger.error(f"Error loading config: {e}")

        return config


NOTIFICATION_TIMEOUT_STR = "5s"
NOTIFICATION_TIMEOUT = parse_timeout_string(NOTIFICATION_TIMEOUT_STR)
NOTIFICATION_IGNORED_APPS_HISTORY = ["Hyprshot"]
NOTIFICATION_LIMITED_APPS_HISTORY = ["Spotify"]
