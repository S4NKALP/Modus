from fabric.audio import Audio
from fabric.utils import GLib, logger
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

from services.battery import Battery
from services.capslock import CapsLock
from services.keyboard_layout import KeyboardLayout
from services.numlock import NumLock
from utils.utils import svg_file

DISPLAY_MS = 2000  # how long each indicator stays visible (ms)


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
            "notch/keyboard-layout.svg",
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


# ── CapsLock ───────────────────────────────────────────────────────────────────


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
            "notch/caps-lock.svg",
            size=16,
            name="notch-indicator-icon",
            v_align="center",
        )
        self._label = Label(
            name="notch-indicator-label",
            label="On" if self._caps.is_on else "Off",
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

        self._caps.connect("state_changed", self._on_state_changed)

    def _on_state_changed(self, _service, is_on: bool):
        # Show for BOTH On and Off
        self._label.set_label("On" if is_on else "Off")
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


class NumLockIndicator(Box):
    def __init__(self, show_cb, hide_cb, **kwargs):
        super().__init__(
            name="notch-numlock",
            orientation="h",
            h_expand=True,
            v_align="center",
            **kwargs,
        )
        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._hide_timer_id = 0

        self._num = NumLock.get_initial()

        self._icon = svg_file(
            "notch/num-lock.svg",
            size=16,
            name="notch-indicator-icon",
            v_align="center",
        )
        self._label = Label(
            name="notch-indicator-label",
            label="On" if self._num.is_on else "Off",
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

        # is_on access also starts the 500ms LED poll inside the service
        self._num.connect("state_changed", self._on_state_changed)

    def _on_state_changed(self, _service, is_on: bool):
        # Show for BOTH On and Off
        self._label.set_label("On" if is_on else "Off")
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
            self._num.disconnect_by_func(self._on_state_changed)
        except Exception as e:
            logger.warning(f"[NotchIndicators] numlock disconnect: {e}")
        super().destroy()


class ChargingIndicator(Box):
    def __init__(self, show_cb, hide_cb, **kwargs):
        super().__init__(
            name="notch-charging",
            orientation="h",
            h_expand=True,
            v_align="center",
            **kwargs,
        )
        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._hide_timer_id = 0

        self._battery = Battery.get_initial()

        self._label = Label(
            name="notch-indicator-label",
            label="Charging",
            v_align="center",
        )
        self._icon = svg_file(
            "notch/charging.svg",
            size=24,
            name="notch-indicator-icon",
            v_align="center",
        )

        self.add(
            CenterBox(
                orientation="h",
                h_expand=True,
                start_children=self._label,
                end_children=self._icon,
            )
        )

        self._battery.connect("changed", self._on_battery_changed)

        GLib.timeout_add(500, self._initial_check)

    def _is_charger_connected(self) -> bool:
        return self._battery.charging or self._battery.charged

    def _initial_check(self):
        self._last_charger_state = self._is_charger_connected()
        if self._last_charger_state:
            self._show_cb(self)
            self._schedule_hide()
        return False  # one-shot

    def _on_battery_changed(self, _battery):
        connected = self._is_charger_connected()
        if connected and not self._last_charger_state:
            self._show_cb(self)
            self._schedule_hide()
        self._last_charger_state = connected

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
            self._battery.disconnect_by_func(self._on_battery_changed)
        except Exception as e:
            logger.warning(f"[NotchIndicators] charging disconnect: {e}")
        super().destroy()


# ── Microphone ─────────────────────────────────────────────────────────────────


class MicrophoneIndicator(Box):
    def __init__(self, show_cb, hide_cb, **kwargs):
        super().__init__(
            name="notch-mic",
            orientation="h",
            h_expand=True,
            v_align="center",
            **kwargs,
        )
        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._hide_timer_id = 0

        self._audio = Audio()
        self._mic_muted = True

        self._label = Label(
            name="notch-indicator-label",
            label="Microphone",
            v_align="center",
        )
        self._state_icon = svg_file(
            "notch/mic-off.svg",
            size=16,
            name="notch-indicator-icon",
            v_align="center",
        )

        self.add(
            CenterBox(
                orientation="h",
                h_expand=True,
                start_children=self._label,
                end_children=self._state_icon,
            )
        )

        self._audio.connect("notify::microphone", self._on_mic_device_changed)
        if self._audio.microphone:
            self._connect_mic_signals()

    def _connect_mic_signals(self):
        mic = self._audio.microphone
        if mic is None:
            return
        # Disconnect from a previously-connected device if it changed, and
        # avoid stacking duplicate handlers on the same device.
        old = getattr(self, "_mic_device", None)
        if old is not None and old is not mic:
            try:
                old.disconnect_by_func(self._on_mic_stream_changed)
            except Exception as e:
                logger.warning(
                    f"[indicators] old.disconnect_by_func(self._on_mic_stream_changed) failed: {e}"
                )
        try:
            mic.disconnect_by_func(self._on_mic_stream_changed)
        except Exception as e:
            logger.warning(
                f"[indicators] mic.disconnect_by_func(self._on_mic_stream_changed) failed: {e}"
            )
        mic.connect("changed", self._on_mic_stream_changed)
        self._mic_device = mic
        self._sync_state()

    def _on_mic_device_changed(self, *_):
        self._connect_mic_signals()
        self._show_cb(self)
        self._schedule_hide()

    def _on_mic_stream_changed(self, *_):
        self._sync_state()
        self._show_cb(self)
        self._schedule_hide()

    def _sync_state(self):
        if self._audio.microphone:
            self._mic_muted = self._audio.microphone.muted
            self._state_icon.dynamic_file(
                "notch/mic-off.svg" if self._mic_muted else "notch/mic-on.svg"
            )

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
            self._audio.disconnect_by_func(self._on_mic_device_changed)
        except Exception as e:
            logger.warning(
                f"[indicators] self._audio.disconnect_by_func(self._on_mic_device_changed) failed: {e}"
            )
        old = getattr(self, "_mic_device", None)
        target = old if old is not None else self._audio.microphone
        if target is not None:
            try:
                target.disconnect_by_func(self._on_mic_stream_changed)
            except Exception as e:
                logger.warning(f"[NotchIndicators] mic disconnect: {e}")
        super().destroy()
