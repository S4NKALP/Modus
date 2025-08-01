from typing import Any

import cairo
from gi.repository import GLib, GtkLayerShell  # type: ignore

from fabric.widgets.eventbox import EventBox
from fabric.widgets.widget import Widget
from utils.roam import modus_service
from widgets.wayland import WaylandWindow as Window


class MouseCapture(Window):
    """A background overlay that captures outside clicks without blocking child window interactions"""

    def __init__(self, layer: str, child_window: Window, **kwargs):
        super().__init__(
            layer="top",  # Use top layer to capture events
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
            events=["button-press-event"],
            all_visible=True,
        )
        self.event_box.connect("button-press-event", self.on_overlay_click)
        self.children = [self.event_box]

        # Make the overlay transparent
        self.set_app_paintable(True)
        self.connect("draw", self.on_draw)

        # Add escape key binding to child window
        if hasattr(self.child_window, "add_keybinding"):
            self.child_window.add_keybinding("Escape", self.hide_child_window)

    def on_draw(self, _widget, cr):
        """Make overlay transparent"""
        cr.set_source_rgba(0, 0, 0, 0)  # Fully transparent
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        return False

    def on_overlay_click(self, _widget, event):
        """Handle overlay clicks - check if click is outside child window"""
        if not self.child_window.is_visible():
            return False

        # Get click coordinates
        click_x = event.x_root
        click_y = event.y_root

        # Get child window bounds
        try:
            child_x, child_y = self.child_window.get_position()
            child_allocation = self.child_window.get_allocation()

            # Check if click is inside child window bounds
            inside_child = (
                child_x <= click_x <= child_x + child_allocation.width
                and child_y <= click_y <= child_y + child_allocation.height
            )

            if not inside_child:
                # Click is outside child window - hide it with delay
                GLib.timeout_add(
                    50, lambda: self.hide_child_window(None, None) or False
                )
                return True  # Consume the event

        except Exception as e:
            print(f"Error checking click position: {e}")
            # If we can't determine position, hide child window to be safe
            GLib.timeout_add(50, lambda: self.hide_child_window(None, None) or False)
            return True

        # Click is inside child window - don't consume event
        return False

    def show_child_window(self, widget: Widget = None, event: Any = None) -> None:
        self.set_child_window_visible(True)

    def hide_child_window(self, widget: Widget = None, event: Any = None) -> None:
        self.set_child_window_visible(False)

    def set_child_window_visible(self, visible: bool) -> None:
        if visible:
            self.child_window.show()
            self.show()
        else:
            self.child_window.hide()
            self.hide()

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
