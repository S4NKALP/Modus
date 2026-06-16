from fabric.utils import GLib
from fabric.widgets.eventbox import EventBox  # noqa: E402
from fabric.widgets.wayland import WaylandWindow as Window  # noqa: E402

from shared.window.popup_win import PopupWindow  # noqa: E402


class DismissLayer(Window):
    def __init__(self, on_dismiss, **kwargs):
        self.event_box = EventBox()
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

    def __init__(self, **kwargs):
        self._is_open = False
        self._hide_timeout_id = None
        self.dismiss_layer = DismissLayer(on_dismiss=self.toggle)
        kwargs["keyboard_mode"] = "on-demand"
        super().__init__(**kwargs)
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
        if active and active != self:
            try:
                if hasattr(active, "close_applet"):
                    active.close_applet()
                else:
                    active.hide()
            except Exception as e:
                print(f"[AppletWindow] Warning: failed to close active popup: {e}")

        AppletWindow._active_popup = self

        if self._hide_timeout_id is not None:
            GLib.source_remove(self._hide_timeout_id)
            self._hide_timeout_id = None

        child = self.get_child()
        if child:
            child.set_opacity(1.0)

        if hasattr(self, "dismiss_layer"):
            self.dismiss_layer.show()

        self.set_visible(True)
        self.set_focus(None)

    def close_applet(self):

        if not self._is_open:
            return

        self._is_open = False

        if self._hide_timeout_id is not None:
            GLib.source_remove(self._hide_timeout_id)
            self._hide_timeout_id = None

        if hasattr(self, "dismiss_layer"):
            self.dismiss_layer.hide()

        self.set_visible(False)

        if AppletWindow._active_popup == self:
            AppletWindow._active_popup = None

    def show(self):
        self.open_applet()

    def hide(self):
        self.close_applet()

    def destroy(self):
        if hasattr(self, "dismiss_layer"):
            self.dismiss_layer.destroy()
        if self._hide_timeout_id is not None:
            GLib.source_remove(self._hide_timeout_id)
        super().destroy()
