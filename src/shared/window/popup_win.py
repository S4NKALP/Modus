from fabric.utils import Gdk, GLib, Gtk, logger
from fabric.widgets.wayland import WaylandWindow
from gi.repository import GtkLayerShell


def _get_monitor_geometry(widget: Gtk.Widget) -> tuple[int, int]:
    screen = Gdk.Screen.get_default()
    window = widget.get_toplevel().get_window()

    if window is None:
        return 0, screen.get_width()

    monitor_index = screen.get_monitor_at_window(window)
    geo = screen.get_monitor_geometry(monitor_index)

    return geo.x, geo.width


class PopupWindow(WaylandWindow):
    def __init__(
        self,
        parent: WaylandWindow | None = None,
        pointing_to: Gtk.Widget | None = None,
        margin: tuple[int, ...] | str = "0px 0px 0px 0px",
        edge_margin: int = 0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.exclusivity = "none"

        self._parent = parent
        self._pointing_widget = pointing_to
        self._base_margin = self.extract_margin(margin)
        self.margin = self._base_margin.values()
        self.edge_margin = edge_margin
        self.connect("notify::visible", self.do_update_handlers)

    def get_coords_for_widget(self, widget: Gtk.Widget) -> tuple[int, int]:
        if not ((toplevel := widget.get_toplevel()) and toplevel.is_toplevel()):
            return 0, 0
        allocation = widget.get_allocation()
        x, y = widget.translate_coordinates(toplevel, allocation.x, allocation.y) or (
            0,
            0,
        )
        return round(x / 2), round(y / 2)

    def set_pointing_to(self, widget: Gtk.Widget | None):
        if self._pointing_widget:
            try:
                self._pointing_widget.disconnect_by_func(self.do_handle_size_allocate)
            except Exception as e:
                if "nothing connected" not in str(e):
                    logger.error(f"Error disconnecting signal: {e}")
        self._pointing_widget = widget
        return self.do_update_handlers()

    def get_parent_window(self):
        if not self._parent:
            return None
        if hasattr(self._parent, "anchor"):
            return self._parent
        toplevel = self._parent.get_toplevel()
        if hasattr(toplevel, "anchor"):
            return toplevel
        return None

    def do_update_handlers(self, *_):
        if not self._pointing_widget:
            return

        if not self.get_visible():
            try:
                self._pointing_widget.disconnect_by_func(self.do_handle_size_allocate)
                self.disconnect_by_func(self.do_handle_size_allocate)
            except Exception as e:
                if "nothing connected" not in str(e):
                    logger.error(f"Error disconnecting signal: {e}")
            return

        self._pointing_widget.connect("size-allocate", self.do_handle_size_allocate)
        self.connect("size-allocate", self.do_handle_size_allocate)

        GLib.timeout_add(10, self._do_delayed_reposition)

    def _do_delayed_reposition(self):
        self.do_reposition(self.do_calculate_edges())
        return False

    def do_handle_size_allocate(self, *_):
        if not self.get_visible():
            return
        return self.do_reposition(self.do_calculate_edges())

    def do_calculate_edges(self):
        move_axe = "x"
        parent_window = self.get_parent_window()
        if not parent_window:
            return move_axe

        parent_anchor = parent_window.anchor

        if len(parent_anchor) == 1:
            if GtkLayerShell.Edge.TOP in parent_anchor:
                self.anchor = "left top"
            else:
                self.anchor = "left bottom"
            return move_axe

        if len(parent_anchor) != 3:
            return move_axe

        if (
            GtkLayerShell.Edge.LEFT in parent_anchor
            and GtkLayerShell.Edge.RIGHT in parent_anchor
        ):
            move_axe = "x"
            if GtkLayerShell.Edge.TOP in parent_anchor:
                self.anchor = "left top"
            else:
                self.anchor = "left bottom"
        elif (
            GtkLayerShell.Edge.TOP in parent_anchor
            and GtkLayerShell.Edge.BOTTOM in parent_anchor
        ):
            move_axe = "y"
            if GtkLayerShell.Edge.RIGHT in parent_anchor:
                self.anchor = "top right"
            else:
                self.anchor = "top left"

        return move_axe

    def do_reposition(self, move_axe: str):
        parent_window = self.get_parent_window()
        if not parent_window:
            return

        parent_margin = parent_window.margin
        parent_x_margin, parent_y_margin = parent_margin[0], parent_margin[3]

        height = self.get_allocated_height()
        width = self.get_allocated_width()

        monitor_x, monitor_width = _get_monitor_geometry(parent_window)

        if self._pointing_widget:
            coords = self.get_coords_for_widget(self._pointing_widget)
            coords_centered = (
                round(coords[0] + self._pointing_widget.get_allocated_width() / 2),
                round(coords[1] + self._pointing_widget.get_allocated_height() / 2),
            )
        else:
            coords_centered = (
                round(parent_window.get_allocated_width() / 2),
                round(parent_window.get_allocated_height() / 2),
            )

        if move_axe == "x":
            if len(parent_window.anchor) == 1:
                bar_width = parent_window.get_allocated_width()
                bar_left = (monitor_width - bar_width) // 2
                raw_margin = round((bar_left + coords_centered[0]) - (width / 2))
            else:
                raw_margin = round((parent_x_margin + coords_centered[0]) - (width / 2))
            min_margin = self.edge_margin
            max_margin = monitor_width - width - self.edge_margin
            clamped = max(min_margin, min(raw_margin, max_margin))
            position_margins = (0, 0, 0, clamped)
        else:
            raw_margin = round((parent_y_margin + coords_centered[1]) - (height / 2))
            monitor_height = Gdk.Screen.get_default().get_height()
            min_margin = self.edge_margin
            max_margin = monitor_height - height - self.edge_margin
            clamped = max(min_margin, min(raw_margin, max_margin))
            position_margins = (clamped, 0, 0, 0)

        new_margin = tuple(
            a + b for a, b in zip(position_margins, self._base_margin.values())
        )
        new_margin = (
            max(0, new_margin[0]),
            new_margin[1],
            max(0, new_margin[2]),
            new_margin[3],
        )

        if tuple(self.margin) != tuple(new_margin):
            self.margin = new_margin
