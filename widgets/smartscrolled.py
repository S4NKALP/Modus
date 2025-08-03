from gi.repository import Gtk, GLib

from fabric.widgets.box import Box
from fabric.widgets.scrolledwindow import ScrolledWindow


class SmartScrolledBox(Box):
    def __init__(
        self,
        max_height: int = 300,
        spacing: int = 6,
        **kwargs,
    ):
        super().__init__(orientation="v", spacing=spacing, **kwargs)

        self._max_height = max_height

        # The actual content box that holds children
        self.content_box = Box(orientation="v", spacing=spacing)

        # Viewport → for scrolling non-scrollable widgets like Box
        self.viewport = Gtk.Viewport()
        self.viewport.add(self.content_box)

        # ScrolledWindow → wrapper for vertical scrolling
        self.scroller = ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.add(self.viewport)

        self.add(self.scroller)

        # Initial size check
        GLib.idle_add(self._apply_height_constraint)

    def append(self, widget: Gtk.Widget):
        self.content_box.add(widget)
        self._apply_height_constraint()

    def remove(self, widget: Gtk.Widget):
        self.content_box.remove(widget)
        self._apply_height_constraint()

    def clear(self):
        for child in self.content_box.get_children():
            self.content_box.remove(child)
        self._apply_height_constraint()

    def update_height(self):
        """Manually trigger height update - useful when content is added externally."""
        self._apply_height_constraint()

    def force_height_constraint(self):
        """Force height constraint immediately."""
        self._apply_height_constraint()

    def _apply_height_constraint(self):
        """Apply height constraint immediately without delay."""
        _, nat_height = self.content_box.get_preferred_height()
        if nat_height > self._max_height:
            # Force height constraint and show scrollbar
            self.set_size_request(-1, self._max_height)
            self.scroller.set_size_request(-1, self._max_height)
            self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
        else:
            # Allow natural height, no size request
            self.set_size_request(-1, -1)
            self.scroller.set_size_request(-1, -1)
            self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)

    def get_vadjustment(self):
        """Get the vertical adjustment from the scrolled window."""
        return self.scroller.get_vadjustment()

    def get_hadjustment(self):
        """Get the horizontal adjustment from the scrolled window."""
        return self.scroller.get_hadjustment()
