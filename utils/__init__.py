from .custom_image import *
from .icon_resolver import *
import json
import os
from fabric.utils import get_relative_path


def read_config():
    config_path = get_relative_path("../config/assets/modus.json")

    with open(config_path, "r") as file:
        # Load JSON data into a Python dictionary
        data = json.load(file)
    return data


default_wallpapers_dir = get_relative_path("../assets/wallpaper")
json_config_path = get_relative_path("../config/assets/config.json")

if os.path.exists(json_config_path):
    with open(json_config_path, "r") as f:
        config = json.load(f)
    WALLPAPERS_DIR = config.get("wallpapers_dir", default_wallpapers_dir)
else:
    WALLPAPERS_DIR = default_wallpapers_dir
