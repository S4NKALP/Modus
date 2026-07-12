import ctypes
import json
import subprocess
from collections.abc import Callable, Iterable
from functools import reduce
from typing import NamedTuple, TypeVar, cast

from fabric.utils import (
    Gdk,
    GdkPixbuf,
    GLib,
    Gtk,
    cairo,
    exec_shell_command,
    invoke_repeater,
    logger,
    os,
    time,
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
                    cairo.RectangleInt,
                    children[i].get_preferred_size().minimum_size,  # type: ignore
                )
            ).height  # type: ignore
            for i in range(children_len)
        ),
    )


# Function to set the process name
def set_process_name(name: str):
    libc = ctypes.CDLL("libc.so.6")
    libc.prctl(15, name.encode("utf-8"), 0, 0, 0)


def write_json_file(data: dict, path: str):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to write json: {e}")


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


# Function to check if a workspace ID is special
def is_special_workspace_id(ws_id) -> bool:
    try:
        workspace_id = int(ws_id)
        return workspace_id < 0
    except (ValueError, TypeError):
        return bool(isinstance(ws_id, str) and ws_id.startswith("special:"))


# Function to check if a client is on a special workspace
def is_special_workspace(client: dict) -> bool:
    if "workspace" not in client:
        return False

    workspace = client["workspace"]
    if "name" in workspace:
        workspace_name = workspace["name"]
        if is_special_workspace_id(workspace_name):
            return True
    if "id" in workspace:
        workspace_id = workspace["id"]
        if is_special_workspace_id(workspace_id):
            return True

    return False


def add_style_class_lazy(widget: Gtk.Widget, class_name: str | Iterable[str]) -> int:
    return invoke_repeater(
        50, lambda: widget.add_style_class(class_name), initial_call=False
    )


def is_app_running(app_name: str) -> bool:
    return len(exec_shell_command(f"pidof {app_name}")) != 0


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


# Terminal helpers
def terminal_exec_command(terminal: str, command: str, title: str | None = None) -> str:
    title_flag = title or ""
    mapping = {
        "kitty": f"kitty{f" --title='{title_flag}'" if title_flag else ''} -e {command}",
        "alacritty": f"alacritty{f" --title '{title_flag}'" if title_flag else ''} -e {command}",
        "gnome-terminal": f"gnome-terminal{f" --title='{title_flag}'" if title_flag else ''} -- {command}",
        "xterm": f"xterm{f" -title '{title_flag}'" if title_flag else ''} -e {command}",
        "foot": f"foot {command}",
        "konsole": f"konsole -e {command}",
        "xfce4-terminal": f"xfce4-terminal -e '{command}'",
    }
    return mapping.get(terminal, f"{terminal} -e {command}")


def terminal_open_in_directory_command(
    terminal: str,
    directory: str,
    title: str | None = None,
    inner_command: str | None = None,
) -> str:
    title_segment = title or ""
    directory = directory
    if inner_command:
        mapping = {
            "kitty": f"kitty{f" --title='{title_segment}'" if title_segment else ''} --directory {directory} {inner_command}",
            "alacritty": f"alacritty{f" --title '{title_segment}'" if title_segment else ''} --working-directory {directory} -e {inner_command}",
            "gnome-terminal": f"gnome-terminal{f" --title='{title_segment}'" if title_segment else ''} --working-directory {directory} -- {inner_command}",
            "foot": f"foot --working-directory {directory} {inner_command}",
            "xfce4-terminal": f"xfce4-terminal --default-working-directory {directory} -e '{inner_command}'",
        }
        return mapping.get(
            terminal,
            f"{terminal} --working-directory {directory} -e {inner_command}",
        )

    mapping = {
        "kitty": f"kitty{f" --title='{title_segment}'" if title_segment else ''} --directory {directory}",
        "alacritty": f"alacritty{f" --title '{title_segment}'" if title_segment else ''} --working-directory {directory}",
        "gnome-terminal": f"gnome-terminal{f" --title='{title_segment}'" if title_segment else ''} --working-directory {directory}",
        "foot": f"foot --working-directory {directory}",
        "xfce4-terminal": f"xfce4-terminal --default-working-directory {directory}",
    }
    return mapping.get(terminal, f"{terminal} --working-directory {directory}")


# Subprocess helper with structured result and timeouts
class CommandResult(NamedTuple):
    returncode: int
    stdout: bytes | str
    stderr: bytes | str


def run_command(
    args: list[str],
    timeout: float | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
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


def trigger_paste_shortcut(delay_ms: int = 50) -> bool:
    time.sleep(delay_ms / 1000)
    result = run_command(["wtype", "-M", "ctrl", "v", "-m", "ctrl"], timeout=1)
    return result.returncode == 0


def debounce(ms: int):
    """
    Debounce a function.
    Useful for preventing UI flickering during fast typing.
    """

    def decorator(func: Callable):
        timer_id_attr = f"_debounce_timer_{func.__name__}"

        def wrapper(self, *args, **kwargs):
            if existing_timer := getattr(self, timer_id_attr, None):
                GLib.source_remove(existing_timer)

            def timeout_cb():
                setattr(self, timer_id_attr, 0)
                func(self, *args, **kwargs)
                return False

            setattr(self, timer_id_attr, GLib.timeout_add(ms, timeout_cb))

        return wrapper

    return decorator
