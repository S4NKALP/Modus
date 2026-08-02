import os
import struct
from pathlib import Path
from typing import Literal

from fabric.utils import (
    Gdk,
    GLib,
    bulk_connect,
    exec_shell_command_async,
    logger,
)
from fabric.widgets.svg import Svg


# Function to set up cursor hover
def setup_cursor_hover(
    widget, cursor_name: Literal["pointer", "crosshair", "grab"] = "pointer"
):
    display = Gdk.Display.get_default()
    cursor = Gdk.Cursor.new_from_name(display, cursor_name)

    def on_enter_notify_event(widget, _):
        widget.get_window().set_cursor(cursor)

    def on_leave_notify_event(widget, _):
        # Restore default cursor when leaving the widget's area
        widget.get_window().set_cursor(None)

    bulk_connect(
        widget,
        {
            "enter-notify-event": on_enter_notify_event,
            "leave-notify-event": on_leave_notify_event,
        },
    )


# Base path to config directory
BASE_CONFIG_PATH = (Path(__file__).resolve().parent.parent.parent / "config").resolve()

# Base path to SVG assets
BASE_SVG_PATH = (Path(__file__).resolve().parent.parent / "assets" / "icons").resolve()


def svg_file(relative_path: str, **kwargs) -> Svg:
    """
    Return a fresh Svg widget for a given relative path.

    Avoids reusing the same widget instance across multiple containers, which
    can cause GTK warnings. Example:
        svg_file("misc/logo.svg", size=16)
    """

    def _resolve_path(path_like):
        s = str(path_like)
        marker = "/src/assets/icons/"
        if marker in s:
            rel = s.split(marker, 1)[1]
            return (BASE_SVG_PATH / rel).resolve()
        p = Path(s)
        if p.is_absolute():
            return p
        return (BASE_SVG_PATH / p).resolve()

    full_path = _resolve_path(relative_path)
    svg = Svg(svg_file=str(full_path), **kwargs)

    original_set_from_file = svg.set_from_file

    def _set_from_file_resolved(file_path):
        return original_set_from_file(str(_resolve_path(file_path)))

    svg.set_from_file = _set_from_file_resolved  # type: ignore[attr-defined]

    # Provide a convenience alias for dynamic updates
    def _dynamic_file(file_path):
        _set_from_file_resolved(file_path)
        return svg

    svg.dynamic_file = _dynamic_file  # type: ignore[attr-defined]

    return svg


def toml_file(relative_path: str) -> str:
    """Return absolute path to a TOML file in config/."""
    return str(BASE_CONFIG_PATH / relative_path)


def generate_colors_from_wallpaper(image_path: str) -> bool:
    cmd = f'matugen image "{image_path}" --source-color-index 0'
    return bool(exec_shell_command_async(cmd))


class EvdevLEDMonitor:
    """Helper to monitor EV_LED state changes without polling."""

    def __init__(self, led_path: Path, target_code: int, on_state_changed_cb):
        self.led_path = led_path
        self.target_code = target_code
        self.on_state_changed_cb = on_state_changed_cb
        self._fd = None
        self._watch_id = None
        self._last_state = None

    def _get_evdev_path(self) -> Path | None:
        if not self.led_path:
            return None
        try:
            device_path = self.led_path / "device"
            for child in device_path.iterdir():
                if child.name.startswith("event"):
                    return Path("/dev/input") / child.name
        except Exception as e:
            logger.warning(
                f"[utils] device_path = self.led_path / 'device' failed: {e}"
            )
        return None

    def start(self):
        evdev_path = self._get_evdev_path()
        if not evdev_path or not evdev_path.exists():
            logger.warning(f"Evdev path not found for {self.led_path}")
            return

        try:
            self._fd = os.open(evdev_path, os.O_RDONLY | os.O_NONBLOCK)
            self._watch_id = GLib.io_add_watch(
                self._fd,
                GLib.PRIORITY_DEFAULT,
                GLib.IOCondition.IN,
                self._on_evdev_data,
            )
        except PermissionError:
            logger.warning(
                f"Permission denied to read {evdev_path}. Add user to 'input' group."
            )
        except Exception as e:
            logger.error(f"Failed to start evdev monitoring: {e}")

    def _on_evdev_data(self, fd, condition):
        try:
            event_size = struct.calcsize("llHHi")
            while True:
                try:
                    data = os.read(fd, event_size)
                except BlockingIOError as e:
                    logger.warning(
                        f"[utils] data = os.read(fd, event_size) failed: {e}"
                    )
                    break

                if len(data) == event_size:
                    _tv_sec, _tv_usec, type_, code, value = struct.unpack("llHHi", data)
                    if type_ == 17 and code == self.target_code:
                        current_state = bool(value)
                        if current_state != self._last_state:
                            self._last_state = current_state
                            self.on_state_changed_cb(current_state)
        except Exception as e:
            logger.error(f"Evdev error: {e}")
            self.stop()
            return False
        return True

    def stop(self):
        if self._watch_id is not None:
            GLib.source_remove(self._watch_id)
            self._watch_id = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError as e:
                logger.warning(f"[utils] os.close(self._fd) failed: {e}")
            self._fd = None
