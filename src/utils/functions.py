import ctypes
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from functools import reduce
from typing import Dict, NamedTuple, Optional, TypeVar, cast

from fabric.utils import (
    Gdk,
    GdkPixbuf,
    Gtk,
    cairo,
    exec_shell_command_async,
    get_desktop_applications,
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


_DURATION_RE = re.compile(
    r"^\s*(\d+)\s*(s|sec|secs|m|min|mins|h|hr|hrs|hour|hours)?\s*$",
    re.IGNORECASE,
)
_UNIT_SECS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
}


def parse_timeout_string(timeout_str, in_seconds=False):
    """
    Parse timeout string in format like '5s', '10m', '2hr', '1hour' etc.

    Args:
        timeout_str: String to parse (e.g., "5s", "10m", "2hr", "1hour")
        in_seconds: If True, return seconds; if False, return milliseconds

    Returns:
        Parsed time value (milliseconds by default, seconds if in_seconds=True)
        Returns 5000 (ms) or 5 (s) as default on parse failure.
    """
    if not timeout_str or not isinstance(timeout_str, str):
        return 5 if in_seconds else 5000

    m = _DURATION_RE.match(timeout_str.strip())
    if not m:
        logger.warning(f"[functions] Could not parse timeout string: {timeout_str}")
        return 5 if in_seconds else 5000

    value = int(m.group(1))
    unit = m.group(2)  # None means bare number (seconds)

    if unit is None:
        seconds = value
    else:
        seconds = value * _UNIT_SECS.get(unit.lower(), 1)

    return seconds if in_seconds else seconds * 1000


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
        result = subprocess.run(
            ["wl-copy"],
            input=text.encode(),
            timeout=5,
        )
        return result.returncode == 0
    except FileNotFoundError:
        try:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(text, -1)
            clipboard.store()
            return True
        except Exception as e:
            logger.warning(
                f"[functions] clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD) failed: {e}"
            )
            return False
    except Exception as e:
        logger.warning(f"[functions] wl-copy failed: {e}")
        return False


def copy_image(image_path: str) -> bool:
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
        result = subprocess.run(
            ["wl-copy", "--type", "image/png"],
            input=image_data,
            timeout=5,
        )
        return result.returncode == 0
    except FileNotFoundError:
        try:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            image = GdkPixbuf.Pixbuf.new_from_file(image_path)
            clipboard.set_image(image)
            clipboard.store()
            return True
        except Exception as e:
            logger.warning(
                f"[functions] clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD) failed: {e}"
            )
            return False
    except Exception as e:
        logger.warning(f"[functions] wl-copy (image) failed: {e}")
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


def trigger_paste_shortcut(delay_ms: int = 50) -> bool:
    time.sleep(delay_ms / 1000)
    result = run_command(
        [
            "hyprctl",
            "dispatch",
            'hl.dsp.send_shortcut({ mods = "CTRL", key = "V" })',
        ],
        timeout=1,
    )
    return result.returncode == 0


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
    except (ValueError, TypeError) as e:
        # If it's a string, check if it starts with "special:"
        logger.warning(f"[functions] workspace_id = int(ws_id) failed: {e}")
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
    clean = re.sub(r"<[^>]+>", "", text)
    return html.escape(clean.replace("\n", " "))


# Process management


_desktop_apps_cache: list | None = None


def get_desktop_apps() -> list:
    """Return cached desktop applications, scanning once until invalidated.

    ``get_desktop_applications`` parses every .desktop file on disk, so the
    result is shared across all consumers (dock, spotlight) instead of being
    recomputed per caller. Call ``invalidate_desktop_apps_cache`` when the
    desktop dirs change to trigger a rescan.
    """
    global _desktop_apps_cache
    if _desktop_apps_cache is None:
        try:
            _desktop_apps_cache = list(get_desktop_applications(include_hidden=False))
        except Exception as e:
            logger.warning(f"[functions] get_desktop_applications failed: {e}")
            _desktop_apps_cache = []
    return list(_desktop_apps_cache)


def invalidate_desktop_apps_cache() -> None:
    global _desktop_apps_cache
    _desktop_apps_cache = None


def spawn_detached(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def kill_process(process_name: str):
    exec_shell_command_async(f"pkill {shlex.quote(process_name)}", lambda *_: None)


def is_process_running(process_name: str) -> bool:
    try:
        result = subprocess.run(["pidof", process_name], capture_output=True, text=True)
        return bool(result.stdout.strip())
    except Exception as e:
        logger.warning(
            f"[functions] result = subprocess.run(['pidof', process_name], capture_... failed: {e}"
        )
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
    except Exception as e:
        logger.warning(
            f"[functions] result = subprocess.run( ['pgrep', '-f', process_name], c... failed: {e}"
        )
        return []


# Binary lookup
def find_binary(name: str) -> str | None:
    return shutil.which(name)


def shell_split(s: str) -> list[str]:
    return shlex.split(s)


# General utilities
def format_mmss(seconds: int, pad: bool = False) -> str:
    """
    Convert a duration in seconds to a clock string.

    pad=True -> zero-padded "MM:SS" (e.g. "02:34").
    pad=False -> compact "M:SS" or "H:MM:SS" (e.g. "5:23", "1:02:03").

    Non-positive durations render as "0:00".
    """
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "0:00"

    if total <= 0:
        total = 0

    if pad:
        return f"{total // 60:02d}:{total % 60:02d}"

    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


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
    except (TypeError, ValueError) as e:
        logger.warning(f"[functions] total = int(seconds) failed: {e}")
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
        logger.warning(
            f"[functions] result = subprocess.run( args, capture_output=True, text=... failed: {e}"
        )
        return CommandResult(
            -1,
            (e.stdout or b"" if not text else e.stdout or ""),
            (e.stderr or (b"timeout" if not text else "timeout")),
        )
    except FileNotFoundError as e:
        logger.warning(
            f"[functions] result = subprocess.run( args, capture_output=True, text=... failed: {e}"
        )
        return CommandResult(127, "", str(e))
    except Exception as e:
        logger.warning(
            f"[functions] result = subprocess.run( args, capture_output=True, text=... failed: {e}"
        )
        return CommandResult(1, "", str(e))


def resolve_monitor(target: str) -> str | None:
    """Resolve the ``"active"`` capture target to a concrete monitor name.

    Returns ``None`` for non-active targets (the capture backend handles
    region/window/output directly).
    """
    if target != "active":
        return None
    from services.modus import get_active_monitor_name

    return get_active_monitor_name()


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
