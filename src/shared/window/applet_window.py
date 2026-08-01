from fabric.utils import GLib, logger
from fabric.widgets.eventbox import EventBox
from fabric.widgets.wayland import WaylandWindow as Window

from shared.window.popup_win import PopupWindow


class DismissLayer(Window):
    def __init__(self, on_dismiss, **kwargs):
        self.event_box = EventBox(events=["button-press"])
        super().__init__(
            anchor="left right top bottom",
            layer="top",
            exclusivity="none",
            keyboard_mode="none",
            child=self.event_box,
            visible=False,
            **kwargs,
        )
        self.event_box.connect("button-press-event", lambda *_: on_dismiss())


class AppletWindow(PopupWindow):
    _active_popup = None

    def __init__(self, edge_margin: int = 0, **kwargs):
        self._is_open = False
        self._hide_timeout_id = None
        self._parent_dropdown = kwargs.pop("parent_dropdown", None)
        self._child_dropdown = None
        self.dismiss_layer = DismissLayer(on_dismiss=self.toggle)
        kwargs["keyboard_mode"] = "on-demand"
        super().__init__(edge_margin=edge_margin, **kwargs)
        self.add_keybinding("escape", lambda *_: self.toggle())

    def toggle(self, *_):
        if self._is_open:
            self.close_applet()
        else:
            self.open_applet()

    def open_applet(self):
        if self._is_open:
            return

        self._is_open = True

        active = AppletWindow._active_popup
        if (
            active
            and active != self
            and active is not getattr(self, "_parent_dropdown", None)
        ):
            try:
                if hasattr(active, "close_applet"):
                    active.close_applet()
                else:
                    active.hide()
            except Exception as e:
                logger.error(
                    f"[AppletWindow] Warning: failed to close active popup: {e}"
                )

        AppletWindow._active_popup = self

        if self._parent_dropdown:
            self._parent_dropdown._child_dropdown = self

        if self._hide_timeout_id is not None:
            GLib.source_remove(self._hide_timeout_id)
            self._hide_timeout_id = None

        child = self.get_child()
        if child:
            child.set_opacity(1.0)

        if hasattr(self, "dismiss_layer"):
            self.dismiss_layer.show()

        self.set_visible(True)

    def close_applet(self):
        if not self._is_open:
            return

        self._is_open = False

        if hasattr(self, "_child_dropdown") and self._child_dropdown:
            try:
                self._child_dropdown.close_applet()
            except Exception:
                pass
            self._child_dropdown = None

        if self._hide_timeout_id is not None:
            GLib.source_remove(self._hide_timeout_id)
            self._hide_timeout_id = None

        if hasattr(self, "dismiss_layer"):
            self.dismiss_layer.hide()

        self.set_visible(False)

        if hasattr(self, "_parent") and self._parent:
            self._parent.set_visible(True)

        if AppletWindow._active_popup == self:
            AppletWindow._active_popup = None

    def show(self):
        self.open_applet()

    def hide(self):
        self.close_applet()

    def destroy(self):
        if AppletWindow._active_popup == self:
            AppletWindow._active_popup = None
        parent = getattr(self, "_parent_dropdown", None)
        if parent is not None and getattr(parent, "_child_dropdown", None) is self:
            parent._child_dropdown = None
        if hasattr(self, "dismiss_layer"):
            self.dismiss_layer.destroy()
        if self._hide_timeout_id is not None:
            GLib.source_remove(self._hide_timeout_id)
            self._hide_timeout_id = None
        super().destroy()
