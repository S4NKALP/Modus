import ctypes
import html
import json
import os
import subprocess
import threading
from typing import Dict, NamedTuple, Optional, TypeVar

from fabric.utils import (
    exec_shell_command_async,
    logger,
)

T = TypeVar("T")


def set_process_name(name: str):
    libc = ctypes.CDLL("libc.so.6")
    libc.prctl(15, name.encode("utf-8"), 0, 0, 0)  # 15 = PR_SET_NAME


def parse_timeout_string(timeout_str):
    """
    Parse timeout string in format like '5s', '10m', '30s' etc.
    Returns timeout in milliseconds.
    """
    if not timeout_str or not isinstance(timeout_str, str):
        return 5000

    timeout_str = timeout_str.strip().lower()

    if timeout_str.endswith("s"):
        try:
            seconds = int(timeout_str[:-1])
            return seconds * 1000
        except ValueError:
            return 5000
    elif timeout_str.endswith("m"):
        try:
            minutes = int(timeout_str[:-1])
            return minutes * 60 * 1000
        except ValueError:
            return 5000
    else:
        try:
            seconds = int(timeout_str)
            return seconds * 1000
        except ValueError:
            return 5000


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


def write_json_file(data: Dict, path: str):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to write json: {e}")


def read_json_file(file_path: str) -> Optional[Dict]:
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
        Relative path to the appropriate WiFi icon
    """
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

    return f"wifi/{icon_name}"


def get_wifi_connecting_icon() -> str:
    """
    Get the WiFi connecting icon path.

    Returns:
        Relative path to the WiFi connecting icon
    """
    return "wifi/wifi-connecting.svg"


def is_special_workspace_id(ws_id) -> bool:
    """
    Check if a workspace ID represents a special workspace.

    Args:
        ws_id: Workspace ID (can be int, string, or other types)

    Returns:
        True if the workspace is special, False otherwise
    """
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


def is_special_workspace(client: dict) -> bool:
    """
    Check if a client is in a special workspace.

    Args:
        client: Client data dictionary from Hyprland

    Returns:
        True if the client is in a special workspace, False otherwise
    """
    if "workspace" not in client:
        return False

    workspace = client["workspace"]

    # Check workspace name first
    if "name" in workspace:
        workspace_name = str(workspace["name"])
        # Special workspaces typically start with "special:" or have negative IDs
        if workspace_name.startswith("special:"):
            return True

    # Check workspace ID
    if "id" in workspace:
        workspace_id = workspace["id"]
        # Special workspaces have negative IDs
        if workspace_id < 0:
            return True

    return False


def escape_markup_text(text: str) -> str:
    return html.escape(text.replace("\n", " "))


# --- Process management ---


def spawn_detached(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def kill_process(process_name: str):
    exec_shell_command_async(f"pkill {process_name}", lambda *_: None)


def is_process_running(process_name: str) -> bool:
    try:
        result = subprocess.run(["pidof", process_name], capture_output=True, text=True)
        return bool(result.stdout.strip())
    except Exception:
        return False


def is_app_running(app_name: str) -> bool:
    return is_process_running(app_name)


def find_process_pid(process_name: str, timeout: float | None = None) -> list[str]:
    try:
        result = subprocess.run(
            ["pgrep", "-f", process_name],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return [pid for pid in result.stdout.strip().split() if pid]
    except Exception:
        return []


def toggle_command(command: str, full_command: str):
    if is_process_running(command):
        kill_process(command)
    else:
        spawn_detached(full_command.split(" "))


# --- Binary lookup ---


def find_binary(name: str) -> str | None:
    try:
        result = subprocess.run(["which", name], capture_output=True, text=True)
        return result.stdout.strip() or None
    except Exception:
        return None


# General utilities
def format_duration(seconds: int) -> str:
    """
    Convert a duration in seconds to a compact human-friendly string.

    Examples:
        0 -> "N/A"
        59 -> "0m"
        61 -> "1m"
        3600 -> "1h 0m"
    """
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "N/A"

    if total <= 0:
        return "N/A"

    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def clear_children(container) -> None:
    """
    Destroy all children of a GTK container-like widget which exposes get_children().
    """
    try:
        for child in list(container.get_children()):
            child.destroy()
    except Exception as e:
        logger.warning(f"clear_children failed: {e}")


class CommandResult(NamedTuple):
    returncode: int
    stdout: bytes | str
    stderr: bytes | str


def run_command(
    args: list[str],
    timeout: float | None = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    *,
    input: bytes | str | None = None,
    text: bool = True,
) -> CommandResult:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=text,
            timeout=timeout,
            cwd=cwd,
            env=env,
            input=input,
        )
        return CommandResult(result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired as e:
        return CommandResult(
            -1,
            (e.stdout or b"" if not text else e.stdout or ""),
            (e.stderr or (b"timeout" if not text else "timeout")),
        )
    except FileNotFoundError as e:
        return CommandResult(127, "", str(e))
    except Exception as e:
        return CommandResult(1, "", str(e))
