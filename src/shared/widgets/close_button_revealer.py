from fabric.utils import Gdk, GLib
from gi.repository import Gtk


class CloseButtonRevealerMixin:
    _close_button_hide_timeout_id: int | None
    _hovered: bool
    _is_close_button_hovered: bool
    close_button_revealer: Gtk.Revealer

    def _schedule_close_button_hide(self):
        self._cancel_close_button_hide()
        self._close_button_hide_timeout_id = GLib.timeout_add(
            80, self._do_hide_close_button
        )

    def _cancel_close_button_hide(self):
        if self._close_button_hide_timeout_id is not None:
            GLib.source_remove(self._close_button_hide_timeout_id)
            self._close_button_hide_timeout_id = None

    def _do_hide_close_button(self):
        self._close_button_hide_timeout_id = None
        if not self._hovered and not self._is_close_button_hovered:
            self.close_button_revealer.set_reveal_child(False)
        return False

    def _on_hover_enter(self, widget, event):
        if hasattr(event, "detail") and event.detail == Gdk.NotifyType.INFERIOR:
            return False
        self._hovered = True
        self._cancel_close_button_hide()
        self.close_button_revealer.set_reveal_child(True)
        return False

    def _on_hover_leave(self, widget, event):
        if hasattr(event, "detail") and event.detail == Gdk.NotifyType.INFERIOR:
            return False
        self._hovered = False
        self._schedule_close_button_hide()
        return False

    def _on_close_button_enter(self, widget, event):
        self._is_close_button_hovered = True
        self._cancel_close_button_hide()
        return False

    def _on_close_button_leave(self, widget, event):
        self._is_close_button_hovered = False
        self._schedule_close_button_hide()
        return False
