from functools import partial

from fabric.widgets.box import Box
from fabric.widgets.shapes import Corner
from fabric.widgets.wayland import WaylandWindow as Window

from config.data import DATA
from services.config_watcher import has_config_changed, on_config_change

bake_corner = partial(Corner, name="corner")

# Corner with defaults for standalone corner windows (fixed size, centered, non-expanding)
CornerBase = partial(
    bake_corner,
    h_expand=False,
    v_expand=False,
    h_align="center",
    v_align="center",
    size=20,
)


def expanded_corner(orientation: str, **kwargs):
    return bake_corner(orientation=orientation, v_expand=True, h_expand=True, **kwargs)


class MyCorner(Box):
    def __init__(self, corner):
        super().__init__(
            name="corner-container",
            children=CornerBase(orientation=corner),
        )


class CornerWindow(Window):
    def __init__(self, corner: str):
        anchor = {
            "top-left": "top left",
            "top-right": "top right",
            "bottom-left": "bottom left",
            "bottom-right": "bottom right",
        }[corner]

        super().__init__(
            layer="bottom",
            anchor=anchor,
            exclusivity="normal",
            pass_through=True,
            visible=False,
            all_visible=False,
        )

        # Size to content by not expanding and only containing the single corner widget
        content = Box(
            children=MyCorner(corner),
            h_expand=False,
            v_expand=False,
        )

        self.add(content)
        self.show_all()


# Create all corner windows
corners = [
    CornerWindow("top-left"),
    CornerWindow("top-right"),
    CornerWindow("bottom-left"),
    CornerWindow("bottom-right"),
]


def update_corners_visibility():
    data = DATA()
    corners_visible = data["corners"]
    for corner in corners:
        corner.set_visible(corners_visible)


def _on_config_change(new_config, old_config):
    if has_config_changed(old_config, new_config, "corners.enabled"):
        update_corners_visibility()


update_corners_visibility()
on_config_change(_on_config_change)
