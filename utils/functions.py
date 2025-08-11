import json
import os
import threading
from typing import Dict, List, Optional

from loguru import logger

# Threading helper functions


def thread(target, *args, **kwargs) -> threading.Thread:
    """
    Simply run the given function in a thread.
    The provided args and kwargs will be passed to the function.
    """
    th = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    th.start()
    return th


def run_in_thread(func):
    """
    Decorator to run the decorated function in a thread.
    """

    def wrapper(*args, **kwargs):
        return thread(func, *args, **kwargs)

    return wrapper


@run_in_thread
def write_json_file(data: Dict, path: str):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to write json: {e}")


def read_json_file(file_path: str) -> Optional[List]:
    if not os.path.exists(file_path):
        logger.error(f"JSON file {file_path} does not exist.")
        return None

    with open(file_path, "r") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to read JSON file {file_path}: {e}")
            return None


def get_wifi_icon_for_strength(strength: int) -> str:
    """
    Get the appropriate WiFi icon based on signal strength.

    Args:
        strength: Signal strength from 0-100

    Returns:
        Absolute path to the appropriate WiFi icon
    """
    # Get the current directory where this script is located
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Get the project root (parent of utils directory)
    project_root = os.path.dirname(current_dir)
    
    if strength >= 80:
        icon_name = "network-wireless-100.svg"
    elif strength >= 60:
        icon_name = "network-wireless-80.svg"
    elif strength >= 40:
        icon_name = "network-wireless-60.svg"
    elif strength >= 20:
        icon_name = "network-wireless-40.svg"
    elif strength > 0:
        icon_name = "network-wireless-20.svg"
    else:
        icon_name = "network-wireless-0.svg"

    return os.path.join(project_root, "config", "assets", "icons", "wifi", icon_name)


def get_wifi_connecting_icon() -> str:
    """
    Get the WiFi connecting icon path.

    Returns:
        Absolute path to the WiFi connecting icon
    """
    # Get the current directory where this script is located
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Get the project root (parent of utils directory)
    project_root = os.path.dirname(current_dir)
    
    return os.path.join(project_root, "config", "assets", "icons", "wifi", "wifi-connecting.svg")
