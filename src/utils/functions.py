import ctypes
import html
import json
import os
import subprocess
import threading
from collections.abc import Callable
from functools import reduce
from typing import Dict, NamedTuple, Optional, TypeVar, cast

from fabric.utils import (
    Gdk,
    GdkPixbuf,
    Gtk,
    cairo,
    exec_shell_command_async,
    logger,
)
from fabric.widgets.box import Box

T = TypeVar("T")


class Rectangle(NamedTuple):
    x: float
    y: float
    width: float
    height: float


def get_children_height_limit(
    viewport: Box,
    max_n_children: int,
    transform_func: Callable[[Gtk.Widget], cairo.RectangleInt] | None = None,
) -> int:
    spacing: int = viewport.get_spacing()

    children = viewport.children
    children_len = len(viewport.children)

    if children_len < 1:
        return 0

    if children_len > max_n_children:
        children_len = max_n_children

    # calculate the new height
    # ( <the spacing for each child combined, last child doesn't have spacing> ) + ( <the total height of all the children> )
    return (spacing * (children_len - 1)) + reduce(
        lambda x, y: x + y,
        (
            (
                transform_func(children[i])
                if transform_func
                else cast(
                    "cairo.RectangleInt",
                    children[i].get_preferred_size().minimum_size,  # type: ignore
                )
            ).height  # type: ignore
            for i in range(children_len)
        ),
    )


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


def copy_text(text: str) -> bool:
    try:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()
        return True
    except Exception:
        return False


def copy_image(image_path: str) -> bool:
    try:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        image = GdkPixbuf.Pixbuf.new_from_file(image_path)
        clipboard.set_image(image)
        clipboard.store()
        return True
    except Exception:
        return False


def read_json_file(file_path: str) -> dict | None:
    if not os.path.exists(file_path):
        logger.error(f"JSON file {file_path} does not exist.")
        return None

    with open(file_path) as file:
        try:
            return json.load(file)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to read JSON file {file_path}: {e}")
            return None


def trigger_paste_shortcut():
    try:
        subprocess.Popen(
            ["sh", "-c", "wl-paste | wtype -"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass


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
        return bool(isinstance(ws_id, str) and ws_id.startswith("special:"))


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
    import re

    clean = re.sub(r"<[^>]+>", "", text)
    return html.escape(clean.replace("\n", " "))


# Process management


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


# Binary lookup
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


def fuzzy_score(query: str, text: str) -> int:
    """
    Fuzzy match scoring. Returns score > 0 if all query chars found in order.
    Heavily rewards prefix matches, word-boundary matches, and consecutive runs.
    Returns 0 if no match.
    """
    if not query or not text:
        return 0

    query = query.lower()
    text = text.lower()

    # Exact match
    if query == text:
        return 10000

    # Prefix match
    if text.startswith(query):
        return 5000 + (100 - len(text))

    # Check all query chars exist in order
    qi = 0
    for char in text:
        if qi < len(query) and char == query[qi]:
            qi += 1
    if qi < len(query):
        return 0

    # Find best alignment — try each possible start position in text
    best_score = 0

    for start in range(len(text)):
        if text[start] != query[0]:
            continue

        qi = 0
        score = 0
        prev = start - 1

        for ti in range(start, len(text)):
            if qi >= len(query):
                break
            if text[ti] == query[qi]:
                # Word boundary bonus (huge)
                if (
                    prev < 0
                    or text[prev] == " "
                    or text[prev] == "-"
                    or text[prev] == "_"
                ):
                    score += 50

                # Consecutive bonus
                if prev == ti - 1:
                    score += 20

                # Exact position in query bonus
                score += 5

                prev = ti
                qi += 1

        if qi < len(query):
            continue

        # How much of the text was consumed (tighter = better)
        span = prev - start + 1
        score += max(0, 200 - span * 3)

        # Prefer shorter texts
        score += max(0, 100 - len(text))

        # Prefer matches at start
        score += max(0, 50 - start)

        if score > best_score:
            best_score = score

    return best_score


def fuzzy_filter(query: str, items: list, key=None, limit: int = 50) -> list:
    """
    Filter and rank items by fuzzy match score.
    Returns top `limit` items sorted by score (best first).
    """
    if not query:
        return items[:limit]

    scored = []
    for item in items:
        text = key(item) if key else str(item)
        score = fuzzy_score(query, text)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]
