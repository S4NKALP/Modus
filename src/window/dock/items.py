from dataclasses import dataclass
from typing import Optional

from fabric.utils import GdkPixbuf

from .constants import MIN_SCALE


@dataclass
class DockItem:
    app_id: str
    app_data: object
    is_pinned: bool = False
    is_trash: bool = False

    is_running: bool = False
    instance_address: Optional[str] = None
    app_class: Optional[str] = None
    client_data: Optional[dict] = None
    workspace_id: Optional[int] = None

    pixbuf: Optional[GdkPixbuf.Pixbuf] = None
    tooltip: str = ""

    icon_surface: object = None
    icon_surface_pixbuf: object = None

    current_scale: float = MIN_SCALE
    target_scale: float = MIN_SCALE

    render_x: float = 0.0
    render_y: float = 0.0
    render_w: float = 0.0
    render_h: float = 0.0

    drag_index: int = 0
    is_dragging: bool = False

    def hit(self, mx: float, my: float) -> bool:
        return (
            self.render_x <= mx <= self.render_x + self.render_w
            and self.render_y <= my <= self.render_y + self.render_h
        )


class DockModel:
    def __init__(self):
        self.items: list[DockItem] = []

    def get_by_address(self, address: str) -> Optional[DockItem]:
        for item in self.items:
            if item.instance_address == address:
                return item
        return None

    def get_by_id(self, app_id: str) -> Optional[DockItem]:
        for item in self.items:
            if item.app_id.lower() == app_id.lower():
                return item
        return None

    def pinned_items(self) -> list[DockItem]:
        return [i for i in self.items if i.is_pinned]

    def running_only_items(self) -> list[DockItem]:
        return [i for i in self.items if not i.is_pinned and not i.is_trash]

    def has_running_only(self) -> bool:
        return any(not i.is_pinned and not i.is_trash for i in self.items)

    def has_pinned(self) -> bool:
        return any(i.is_pinned for i in self.items)


class DockHitTest:
    @staticmethod
    def find_item(items: list[DockItem], mx: float, my: float) -> Optional[DockItem]:
        for item in reversed(items):
            if item.hit(mx, my):
                return item
        return None
