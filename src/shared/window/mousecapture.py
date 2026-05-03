from fabric.utils import Any, Gdk, cairo, GLib
from fabric.widgets.eventbox import EventBox
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.widget import Widget
from gi.repository import GtkLayerShell  # type: ignore

from utils.monitors import HyprlandWithMonitors
from utils.roam import modus_service


class MouseCapture(Window):
    """A background overlay that captures outside clicks without blocking child window interactions"""

    def __init__(self, layer: str, child_window: Window, **kwargs):
        super().__init__(
            layer=layer,  # Use the passed layer
            anchor="top bottom left right",
            exclusivity="auto",
            title="modus",
            name="MouseCapture",
            keyboard_mode="none",  # Don't steal keyboard
            all_visible=False,
            visible=False,
            **kwargs,
        )

        GtkLayerShell.set_exclusive_zone(self, -1)

        self.child_window = child_window

        # Ensure child window is on overlay layer to be above this capture
        if hasattr(self.child_window, "layer"):
            self.child_window.layer = "overlay"

        if hasattr(self.child_window, "_init_mousecapture"):
            self.child_window._init_mousecapture(self)

        # Create transparent event box that captures clicks
        self.event_box = EventBox(
            events=[
                "button-press-event",
                "button-release-event",
                "pointer-motion-mask",  # Listen for mouse movement
                "enter-notify-mask",
            ],
            all_visible=True,
        )
        self.event_box.connect("button-press-event", self.on_overlay_click)
        self.event_box.connect("motion-notify-event", self.on_mouse_motion)
        self.event_box.connect("enter-notify-event", self.on_mouse_motion)
        self.children = [self.event_box]

        self._hyprland = HyprlandWithMonitors()
        self._cursor_pointer = Gdk.Cursor.new_from_name(
            Gdk.Display.get_default(), "pointer"
        )
        self._cursor_default = None  # Resets to default arrow

        # Make the overlay transparent
        self.set_app_paintable(True)
        self.connect("draw", self.on_draw)
        self.connect("size-allocate", lambda *_: self.update_input_region())
        self.connect("map", lambda *_: self.update_input_region())
        self.connect("notify::visible", lambda *_: self.update_input_region())

        # Add escape key binding to child window
        if hasattr(self.child_window, "add_keybinding"):
            self.child_window.add_keybinding("Escape", self.hide_child_window)

    def on_draw(self, _widget, cr):
        """Make overlay transparent"""
        cr.set_source_rgba(0, 0, 0, 0)  # Fully transparent
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        return False

    def _get_child_window_bounds(self) -> tuple[int, int, int, int]:
        """Calculates absolute screen bounds for the child window using Gdk origin"""
        try:
            window = self.child_window.get_window()
            if not window:
                # Fallback to allocation if window isn't mapped yet
                alloc = self.child_window.get_allocation()
                return 0, 0, alloc.width, alloc.height

            # get_origin provides absolute screen coordinates
            success, x, y = window.get_origin()
            if not success:
                alloc = self.child_window.get_allocation()
                return 0, 0, alloc.width, alloc.height

            alloc = self.child_window.get_allocation()
            return x, y, alloc.width, alloc.height

        except Exception as e:
            print(f"Error calculating child window bounds: {e}")
            alloc = self.child_window.get_allocation()
            return 0, 0, alloc.width, alloc.height

    def _get_widget_absolute_bounds(self, widget: Widget) -> tuple[int, int, int, int]:
        """Calculates absolute screen bounds for a widget in another window"""
        try:
            toplevel = widget.get_toplevel()
            if not toplevel or not toplevel.get_window():
                return 0, 0, 0, 0

            # Get the origin of the window containing the widget
            success, wx, wy = toplevel.get_window().get_origin()
            if not success:
                return 0, 0, 0, 0

            # Get relative position within toplevel
            alloc = widget.get_allocation()
            rx, ry = widget.translate_coordinates(toplevel, 0, 0) or (0, 0)

            return wx + rx, wy + ry, alloc.width, alloc.height
        except Exception as e:
            print(f"Error calculating widget absolute bounds: {e}")
            return 0, 0, 0, 0

    def update_input_region(self):
        """Punches holes in the input region for the trigger button and child window"""
        window = self.get_window()
        if not window:
            return

        try:
            # Full screen region
            alloc = self.get_allocation()
            region = cairo.Region(cairo.RectangleInt(0, 0, alloc.width, alloc.height))

            # Punch hole for trigger button (relative to this overlay window)
            pointing_widget = getattr(self.child_window, "_pointing_widget", None)
            if pointing_widget:
                # get_widget_absolute_bounds returns screen-absolute coords.
                # Since overlay is full screen on its monitor, we just need to subtract its monitor's X/Y
                px, py, pw, ph = self._get_widget_absolute_bounds(pointing_widget)
                monitor = self._hyprland.display.get_monitor_at_window(window)
                if monitor:
                    mx, my = monitor.get_geometry().x, monitor.get_geometry().y
                    region.subtract(cairo.RectangleInt(px - mx, py - my, pw, ph))

            # Punch hole for child window
            cx, cy, cw, ch = self._get_child_window_bounds()
            monitor = self._hyprland.display.get_monitor_at_window(window)
            if monitor:
                mx, my = monitor.get_geometry().x, monitor.get_geometry().y
                region.subtract(cairo.RectangleInt(cx - mx, cy - my, cw, ch))

            window.input_shape_combine_region(region, 0, 0)
        except Exception as e:
            print(f"Error updating input region: {e}")

    def on_mouse_motion(self, _widget, event):
        """Update cursor feedback based on position"""
        # (This is mostly redundant now with input regions but kept for extra safety)
        if not self.child_window.is_visible():
            return False

        return False

    def on_overlay_click(self, _widget, event):
        """Handle overlay clicks - check if click is outside child window"""
        if not self.child_window.is_visible():
            return False

        # Support double and triple clicks too
        if event.type not in [
            Gdk.EventType.BUTTON_PRESS,
            Gdk.EventType._2BUTTON_PRESS,
            Gdk.EventType._3BUTTON_PRESS,
        ]:
            return False

        # Use window-local coordinates for robust detection
        click_x = event.x
        click_y = event.y

        # Get window position relative to monitor for absolute -> local conversion
        window = self.get_window()
        mx, my = 0, 0
        if window:
            monitor = self._hyprland.display.get_monitor_at_window(window)
            if monitor:
                geom = monitor.get_geometry()
                mx, my = geom.x, geom.y

        # Check if click is on the "trigger" (pointing) widget
        pointing_widget = getattr(self.child_window, "_pointing_widget", None)
        if pointing_widget:
            px_abs, py_abs, pw, ph = self._get_widget_absolute_bounds(pointing_widget)
            px, py = px_abs - mx, py_abs - my
            if px <= click_x <= px + pw and py <= click_y <= py + ph:
                # Clicked the button that opened us - hide and consume
                self.hide_child_window()
                return True

        # Get child window bounds (monitor-relative)
        cx_abs, cy_abs, cw, ch = self._get_child_window_bounds()
        cx, cy = cx_abs - mx, cy_abs - my

        # Check if click is inside child window bounds
        inside_child = cx <= click_x <= cx + cw and cy <= click_y <= cy + ch

        if not inside_child:
            # Click is outside child window - hide it immediately
            # No delay to avoid race conditions with toggle buttons
            self.hide_child_window()
            return True  # Consume the event

        # Click is inside child window - don't consume event
        return False

    def show_child_window(self, widget: Widget = None, event: Any = None) -> None:
        self.set_child_window_visible(True)

    def hide_child_window(self, widget: Widget = None, event: Any = None) -> None:

        self.set_child_window_visible(False)

    def set_child_window_visible(self, visible: bool) -> None:
        if visible:
            # Connect to child window size changes to keep input region in sync
            self._size_handler = self.child_window.connect(
                "size-allocate", lambda *_: self.update_input_region()
            )
            self.child_window.show()
            self.show()
            # Force update with a small delay to ensure window is mapped
            GLib.timeout_add(50, self.update_input_region)
        else:
            if hasattr(self, "_size_handler") and self._size_handler:
                self.child_window.disconnect(self._size_handler)
                self._size_handler = None
            self.child_window.hide()
            self.hide()

        # Update styling on the trigger button
        pointing_widget = getattr(self.child_window, "_pointing_widget", None)
        if pointing_widget:
            if visible:
                pointing_widget.add_style_class("active")
            else:
                pointing_widget.remove_style_class("active")

        if hasattr(self.child_window, "_set_mousecapture"):
            self.child_window._set_mousecapture(visible)

    def toggle_mousecapture(self, *_) -> None:
        if self.is_visible():
            self.set_child_window_visible(False)
        else:
            self.set_child_window_visible(True)


class DropDownMouseCapture(MouseCapture):
    """A specialized MouseCapture for dropdown menus with service integration"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        modus_service.connect("dropdowns-hide-changed", self.dropdowns_hide_changed)

    def hide_child_window(self, widget: Widget = None, event: Any = None) -> None:
        """Hide child window and update dropdown service state"""
        # Update service state before hiding to prevent conflicts
        if hasattr(self.child_window, "id"):
            if str(modus_service.current_dropdown) == str(self.child_window.id):
                modus_service.current_dropdown = None
        super().hide_child_window(widget, event)

    def dropdowns_hide_changed(self, widget: Widget = None, event: Any = None) -> None:
        """Handle dropdown service hide changes"""
        if hasattr(self.child_window, "id"):
            if modus_service.current_dropdown == self.child_window.id:
                return
        return self.hide_child_window(widget, event)

    def destroy(self):
        """Clean up signal connections"""
        try:
            modus_service.disconnect_by_func(self.dropdowns_hide_changed)
        except Exception:
            pass
        super().destroy()


def add_destroy_to_mousecapture():
    # Base MouseCapture
    def mc_destroy(self):
        # Child window should be destroyed by its owner, but we should null references
        self.child_window = None
        Window.destroy(self)

    MouseCapture.destroy = mc_destroy


# Apply destroy to base class
add_destroy_to_mousecapture()
