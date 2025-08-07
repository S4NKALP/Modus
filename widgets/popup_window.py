import contextlib
import gi  # type: ignore
from gi.repository import Gdk, Gtk, GtkLayerShell  # type: ignore

from widgets.wayland import WaylandWindow
from utils.monitors import HyprlandWithMonitors

gi.require_version("GtkLayerShell", "0.1")


class PopupWindow(WaylandWindow):
    """A simple popover window that can point to a widget."""

    def __init__(
        self,
        parent: WaylandWindow,
        pointing_to: Gtk.Widget | None = None,
        margin: tuple[int, ...] | str = "0px 0px 0px 0px",
        enable_boundary_checking: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.exclusivity = "none"
        self._is_centered = False
        self._parent = parent
        self._pointing_widget = pointing_to
        self._hyprland = HyprlandWithMonitors()
        self._base_margin = self.extract_margin(margin)
        self.margin = self._base_margin.values()
        self._enable_boundary_checking = enable_boundary_checking

        self.connect("notify::visible", self.do_update_handlers)

    def get_coords_for_widget(self, widget: Gtk.Widget) -> tuple[int, int]:
        if not ((toplevel := widget.get_toplevel()) and toplevel.is_toplevel()):  # type: ignore
            return 0, 0
        allocation = widget.get_allocation()
        x, y = widget.translate_coordinates(toplevel, allocation.x, allocation.y) or (
            0,
            0,
        )
        return round(x / 2), round(y / 2)

    def set_pointing_to(self, widget: Gtk.Widget | None):
        if self._pointing_widget:
            with contextlib.suppress(Exception):
                self._pointing_widget.disconnect_by_func(self.do_handle_size_allocate)
        self._pointing_widget = widget
        return self.do_update_handlers()

    def do_update_handlers(self, *_):
        if not self._pointing_widget:
            return

        if not self.get_visible():
            try:
                self._pointing_widget.disconnect_by_func(self.do_handle_size_allocate)
                self.disconnect_by_func(self.do_handle_size_allocate)
            except Exception:
                pass
            return

        self._pointing_widget.connect("size-allocate", self.do_handle_size_allocate)
        self.connect("size-allocate", self.do_handle_size_allocate)

        return self.do_handle_size_allocate()

    def do_handle_size_allocate(self, *_):
        return self.do_reposition(self.do_calculate_edges())

    def do_calculate_edges(self):
        move_axe = "x"
        parent_anchor = self._parent.anchor

        if len(parent_anchor) != 3:
            self.anchor = "left bottom"
            self._is_centered = True
            return move_axe

        if (
            GtkLayerShell.Edge.LEFT in parent_anchor
            and GtkLayerShell.Edge.RIGHT in parent_anchor
        ):
            # horizontal -> move on x-axies
            move_axe = "x"
            if GtkLayerShell.Edge.TOP in parent_anchor:
                self.anchor = "left top"
            else:
                self.anchor = "left bottom"
        elif (
            GtkLayerShell.Edge.TOP in parent_anchor
            and GtkLayerShell.Edge.BOTTOM in parent_anchor
        ):
            # vertical -> move on y-axies
            move_axe = "y"
            if GtkLayerShell.Edge.RIGHT in parent_anchor:
                self.anchor = "top right"
            else:
                self.anchor = "top left"

        self._is_centered = False
        return move_axe

    def do_reposition(self, move_axe: str):
        parent_margin = self._parent.margin
        parent_x_margin, parent_y_margin = parent_margin[0], parent_margin[3]

        height = self.get_allocated_height()
        width = self.get_allocated_width()

        # Get monitor geometry for boundary checking
        current_monitor_id = self._hyprland.get_current_gdk_monitor_id()
        if current_monitor_id is not None:
            monitor = self._hyprland.display.get_monitor(current_monitor_id)
            monitor_geometry = monitor.get_geometry()
            monitor_x, monitor_y = monitor_geometry.x, monitor_geometry.y
            monitor_width, monitor_height = monitor_geometry.width, monitor_geometry.height
        else:
            # Fallback to default screen
            screen = Gdk.Screen.get_default()
            monitor_x, monitor_y = 0, 0
            monitor_width, monitor_height = screen.get_width(), screen.get_height()

        if self._pointing_widget:
            coords = self.get_coords_for_widget(self._pointing_widget)
            coords_centered = (
                round(coords[0] + self._pointing_widget.get_allocated_width() / 2),
                round(coords[1] + self._pointing_widget.get_allocated_height() / 2),
            )
        else:
            coords_centered = (
                round(self._parent.get_allocated_width() / 2),
                round(self._parent.get_allocated_height() / 2),
            )

        if self._is_centered:
            # Calculate centered position with boundary checking
            centered_x = (
                (monitor_width / 2 - self._parent.get_allocated_width() / 2)
                - width / 2
            ) + coords_centered[0]

            # Apply boundary checking only if enabled
            if self._enable_boundary_checking:
                if centered_x < monitor_x:
                    centered_x = monitor_x
                elif centered_x + width > monitor_x + monitor_width:
                    centered_x = monitor_x + monitor_width - width

            self.margin = tuple(
                a + b
                for a, b in zip(
                    (0, 0, 0, centered_x),
                    self._base_margin.values(),
                )
            )
            return

        # Calculate position with boundary checking
        if move_axe == "x":
            # Horizontal positioning
            calculated_x = round((parent_x_margin + coords_centered[0]) - (width / 2))

            # Apply boundary checking only if enabled
            if self._enable_boundary_checking:
                if calculated_x < monitor_x:
                    calculated_x = monitor_x
                elif calculated_x + width > monitor_x + monitor_width:
                    calculated_x = monitor_x + monitor_width - width

            margin_values = (0, 0, 0, calculated_x)
        else:
            # Vertical positioning
            calculated_y = round((parent_y_margin + coords_centered[1]) - (height / 2))

            # Apply boundary checking only if enabled
            if self._enable_boundary_checking:
                if calculated_y < monitor_y:
                    calculated_y = monitor_y
                elif calculated_y + height > monitor_y + monitor_height:
                    calculated_y = monitor_y + monitor_height - height

            margin_values = (calculated_y, 0, 0, 0)

        self.margin = tuple(
            a + b
            for a, b in zip(
                margin_values,
                self._base_margin.values(),
            )
        )
