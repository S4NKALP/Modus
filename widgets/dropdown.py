from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox

from utils.roam import modus_service
from widgets.popup_window import PopupWindow

dropdowns = []


def dropdown_divider(comment):
    return Box(
        children=[Box(name="dropdown-divider", h_expand=True)],
        name="dropdown-divider-box",
        h_align="fill",
        h_expand=True,
        v_expand=True,
    )


class ModusDropdown(PopupWindow):
    def __init__(self, dropdown_children=None, dropdown_id=None, **kwargs):
        super().__init__(
            layer="top",
            exclusivity="auto",
            name="dropdown-menu",
            title="modus",
            keyboard_mode="none",
            visible=False,
            **kwargs,
        )

        self.id = dropdown_id or str(len(dropdowns))
        dropdowns.append(self)
        self._mousecapture_parent = None  # Will be set by mousecapture

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
        self.connect("button-press-event", self.hide_dropdown)
        self.add_keybinding("Escape", self.hide_dropdown)

    def toggle_dropdown(self, button, parent=None):
        self.set_visible(not self.is_visible())
        modus_service.current_dropdown = self.id if self.is_visible() else None

    def _init_mousecapture(self, mousecapture):
        """Store reference to mousecapture parent for hiding"""
        self._mousecapture_parent = mousecapture

    def hide_dropdown(self, widget, event):
        if self.is_visible():
            self.hide()
            if str(modus_service.current_dropdown) == str(self.id):
                modus_service.current_dropdown = None

    def hide_via_mousecapture(self):
        """Hide dropdown via mousecapture parent"""
        if self._mousecapture_parent:
            self._mousecapture_parent.hide_child_window()

    def _set_mousecapture(self, visible: bool) -> None:
        self.set_visible(visible)
        if visible:
            modus_service.current_dropdown = self.id
        else:
            if str(modus_service.current_dropdown) == str(self.id):
                modus_service.current_dropdown = None

    def on_cursor_enter(self, *_):
        self.set_visible(True)

    def on_cursor_leave(self, *_):
        if self.is_hovered():
            return
        self.set_visible(False)
        modus_service.dropdowns_hide = not modus_service.dropdowns_hide
