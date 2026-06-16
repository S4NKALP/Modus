from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from gi.repository import GLib
from utils.roam import modus_service
from shared.window.applet_window import AppletWindow

dropdowns = []


def dropdown_divider(comment):
    return Box(
        children=[Box(name="dropdown-divider", h_expand=True)],
        name="dropdown-divider-box",
        h_align="fill",
        h_expand=True,
        v_expand=True,
    )


class ModusDropdown(AppletWindow):
    def __init__(self, dropdown_children=None, dropdown_id=None, **kwargs):
        super().__init__(
            layer="top",
            exclusivity="auto",
            name="dropdown-menu",
            title="modus",
            visible=False,
            **kwargs,
        )

        self.id = dropdown_id or str(len(dropdowns))
        dropdowns.append(self)

        self.connect("notify::visible", self._on_visible_changed)
        modus_service.connect("dropdowns-hide-changed", self.hide_dropdown)

        self.dropdown = Box(
            children=dropdown_children or [],
            h_expand=True,
            name="dropdown-options",
            orientation="vertical",
        )

        self.child_box = CenterBox(start_children=[self.dropdown])

        self.event_box = EventBox(
            events=["enter-notify-event", "leave-notify-event"],
            child=self.child_box,
            all_visible=True,
        )

        self.children = [self.event_box]
        self.add_keybinding("escape", self.hide_dropdown)

    def toggle_dropdown(self, button, parent=None):
        self.toggle()
        modus_service.current_dropdown = self.id if self.is_visible() else None

    def hide_dropdown(self, *_):
        if self.is_visible():
            GLib.idle_add(lambda: self.hide())

    def _on_visible_changed(self, *_):
        if self.is_visible():
            modus_service.current_dropdown = self.id
        elif str(modus_service.current_dropdown) == str(self.id):
            modus_service.current_dropdown = None

    def hide_via_mousecapture(self):
        self.hide()

    def on_cursor_enter(self, *_):
        self.show()

    def on_cursor_leave(self, *_):
        if self.is_hovered():
            return
        self.hide()
        modus_service.dropdowns_hide = not modus_service.dropdowns_hide

    def destroy(self):
        """Clean up resources and global references"""
        global dropdowns
        if self in dropdowns:
            dropdowns.remove(self)

        try:
            modus_service.disconnect_by_func(self.hide_dropdown)
        except Exception:
            pass

        super().destroy()
