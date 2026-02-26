import ctypes
import html
import json
import threading
from typing import Dict, List, Optional

from fabric.utils import logger, os


# Function to set the process name
def set_process_name(name: str):
    libc = ctypes.CDLL("libc.so.6")
    libc.prctl(15, name.encode("utf-8"), 0, 0, 0)


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

    return os.path.join(
        project_root, "config", "assets", "icons", "wifi", "wifi-connecting.svg"
    )


# Function to check if a workspace ID is special
def is_special_workspace_id(ws_id) -> bool:
    try:
        # Convert to int if it's a string
        workspace_id = int(ws_id)
        # Special workspaces have negative IDs
        return workspace_id < 0
    except (ValueError, TypeError):
        # If it's a string, check if it starts with "special:"
        if isinstance(ws_id, str) and ws_id.startswith("special:"):
            return True
        return False


# Function to check if a client is on a special workspace
def is_special_workspace(client: dict) -> bool:
    if "workspace" not in client:
        return False

    workspace = client["workspace"]

    # Check workspace name first
    if "name" in workspace:
        workspace_name = workspace["name"]
        if is_special_workspace_id(workspace_name):
            return True

    # Check workspace ID
    if "id" in workspace:
        workspace_id = workspace["id"]
        if is_special_workspace_id(workspace_id):
            return True

    return False


def escape_markup_text(text: str) -> str:
    """
    Escape special characters in text to make it safe for Pango markup.

    Args:
        text: Raw text that may contain special characters

    Returns:
        Escaped text safe for use in Pango markup
    """
    if not text or not isinstance(text, str):
        return ""

    # Use html.escape to escape XML/HTML special characters
    # This handles &, <, >, and quotes
    return html.escape(text)
