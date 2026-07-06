from pathlib import Path
from typing import Literal

from fabric.utils import Gdk, bulk_connect, exec_shell_command_async
from fabric.widgets.scale import Scale
from fabric.widgets.svg import Svg

from shared.widgets.animator import Animator


class AnimatedScale(Scale):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.animator = None

    def animate_value(self, value: float):
        if not self.animator:
            self.animator = Animator(
                bezier_curve=(0.34, 1.56, 0.64, 1.0),
                duration=0.8,
                min_value=self.min_value,
                max_value=self.value,
                tick_widget=self,
                notify_value=lambda p, *_: self.set_value(p.value),
            )
        self.animator.pause()
        self.animator.min_value = self.value
        self.animator.max_value = value
        self.animator.play()


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

    # Convenience method to update style and return the same instance
    def _dynamic_style(
        style: str,
        *,
        compiled: bool = True,
        append: bool = False,
        add_brackets: bool = True,
    ):
        svg.set_style(
            style, compiled=compiled, append=append, add_brackets=add_brackets
        )
        return svg

    svg.dynamic_style = _dynamic_style  # type: ignore[attr-defined]

    return svg


def toml_file(relative_path: str) -> str:
    """Return absolute path to a TOML file in config/."""
    return str(BASE_CONFIG_PATH / relative_path)


def generate_colors_from_wallpaper(image_path: str) -> bool:
    cmd = f'matugen image "{image_path}" --source-color-index 0'
    return bool(exec_shell_command_async(cmd))
