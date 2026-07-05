from fabric.utils import GLib, logger
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

from services.capslock import CapsLock
from services.keyboard_layout import KeyboardLayout
from utils.utils import svg_file

DISPLAY_MS = 2000  # how long each indicator stays visible


class KeyboardLayoutIndicator(Box):
    def __init__(self, show_cb, hide_cb, **kwargs):
        super().__init__(
            name="notch-kbd-layout",
            orientation="h",
            h_expand=True,
            v_align="center",
            **kwargs,
        )

        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._hide_timer_id = 0

        self._kbd = KeyboardLayout.get_initial()

        self._icon = svg_file(
            "misc/keyboard-layout.svg",
            size=16,
            name="notch-indicator-icon",
            v_align="center",
        )
        self._label = Label(
            name="notch-indicator-label",
            label=self._kbd.current_layout.upper(),
            v_align="center",
        )

        self.add(
            CenterBox(
                orientation="h",
                h_expand=True,
                start_children=self._icon,
                end_children=self._label,
            )
        )

        self._kbd.connect("layout_changed", self._on_layout_changed)

    def _on_layout_changed(self, _service, layout: str):
        self._label.set_label(layout.upper())
        self._show_cb(self)
        self._schedule_hide()

    def _schedule_hide(self):
        if self._hide_timer_id:
            GLib.source_remove(self._hide_timer_id)
        self._hide_timer_id = GLib.timeout_add(DISPLAY_MS, self._do_hide)

    def _do_hide(self):
        self._hide_timer_id = 0
        self._hide_cb()
        return False

    def destroy(self):
        if self._hide_timer_id:
            GLib.source_remove(self._hide_timer_id)
            self._hide_timer_id = 0
        try:
            self._kbd.disconnect_by_func(self._on_layout_changed)
        except Exception as e:
            logger.warning(f"[NotchIndicators] kbd disconnect: {e}")
        super().destroy()


class CapsLockIndicator(Box):
    def __init__(self, show_cb, hide_cb, **kwargs):
        super().__init__(
            name="notch-capslock",
            orientation="h",
            h_expand=True,
            v_align="center",
            **kwargs,
        )

        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._hide_timer_id = 0

        self._caps = CapsLock.get_initial()

        self._icon = svg_file(
            "misc/caps-lock.svg",
            size=16,
            name="notch-indicator-icon",
            v_align="center",
        )
        self._label = Label(
            name="notch-indicator-label",
            label="On",
            v_align="center",
        )

        self.add(
            CenterBox(
                orientation="h",
                h_expand=True,
                start_children=self._icon,
                end_children=self._label,
            )
        )

        # Accessing is_on triggers _ensure_monitoring_started() inside the service —
        # without this the 500ms LED poll never begins and state_changed never fires.
        _ = self._caps.is_on

        self._caps.connect("state_changed", self._on_state_changed)

    def _on_state_changed(self, _service, is_on: bool):
        if not is_on:
            return
        self._show_cb(self)
        self._schedule_hide()

    def _schedule_hide(self):
        if self._hide_timer_id:
            GLib.source_remove(self._hide_timer_id)
        self._hide_timer_id = GLib.timeout_add(DISPLAY_MS, self._do_hide)

    def _do_hide(self):
        self._hide_timer_id = 0
        self._hide_cb()
        return False

    def destroy(self):
        if self._hide_timer_id:
            GLib.source_remove(self._hide_timer_id)
            self._hide_timer_id = 0
        try:
            self._caps.disconnect_by_func(self._on_state_changed)
        except Exception as e:
            logger.warning(f"[NotchIndicators] caps disconnect: {e}")
        super().destroy()
