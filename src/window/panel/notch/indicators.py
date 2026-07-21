from fabric.audio import Audio
from fabric.utils import GLib, logger

from services.battery import Battery
from services.capslock import CapsLock
from services.keyboard_layout import KeyboardLayout
from services.numlock import NumLock

from .indicator_base import BaseNotchIndicator


class KeyboardLayoutIndicator(BaseNotchIndicator):
    def __init__(self, show_cb, hide_cb, **kwargs):
        self._kbd = KeyboardLayout.get_initial()
        super().__init__(
            name="notch-kbd-layout",
            icon_name="notch/keyboard-layout.svg",
            label_text=self._kbd.current_layout.upper(),
            show_cb=show_cb,
            hide_cb=hide_cb,
            **kwargs,
        )
        self._kbd.connect("layout_changed", self._on_layout_changed)

    def _on_layout_changed(self, _service, layout: str):
        self._label.set_label(layout.upper())
        self._show_cb(self)
        self._schedule_hide()

    def _on_destroy(self):
        self._kbd.disconnect_by_func(self._on_layout_changed)


class CapsLockIndicator(BaseNotchIndicator):
    def __init__(self, show_cb, hide_cb, **kwargs):
        self._caps = CapsLock.get_initial()
        super().__init__(
            name="notch-capslock",
            icon_name="notch/caps-lock.svg",
            label_text="On" if self._caps.is_on else "Off",
            show_cb=show_cb,
            hide_cb=hide_cb,
            **kwargs,
        )
        self._caps.connect("state_changed", self._on_state_changed)

    def _on_state_changed(self, _service, is_on: bool):
        self._label.set_label("On" if is_on else "Off")
        self._show_cb(self)
        self._schedule_hide()

    def _on_destroy(self):
        self._caps.disconnect_by_func(self._on_state_changed)


class NumLockIndicator(BaseNotchIndicator):
    def __init__(self, show_cb, hide_cb, **kwargs):
        self._num = NumLock.get_initial()
        super().__init__(
            name="notch-numlock",
            icon_name="notch/num-lock.svg",
            label_text="On" if self._num.is_on else "Off",
            show_cb=show_cb,
            hide_cb=hide_cb,
            **kwargs,
        )
        self._num.connect("state_changed", self._on_state_changed)

    def _on_state_changed(self, _service, is_on: bool):
        self._label.set_label("On" if is_on else "Off")
        self._show_cb(self)
        self._schedule_hide()

    def _on_destroy(self):
        self._num.disconnect_by_func(self._on_state_changed)


class ChargingIndicator(BaseNotchIndicator):
    def __init__(self, show_cb, hide_cb, **kwargs):
        self._battery = Battery.get_initial()
        self._last_charger_state = self._is_charger_connected()
        super().__init__(
            name="notch-charging",
            icon_name="notch/charging.svg",
            label_text="Charging",
            show_cb=show_cb,
            hide_cb=hide_cb,
            icon_size=24,
            icon_first=False,
            **kwargs,
        )
        self._battery.connect("changed", self._on_battery_changed)
        if self._last_charger_state:
            GLib.timeout_add(500, self._initial_show)

    def _is_charger_connected(self) -> bool:
        return self._battery.charging or self._battery.charged

    def _initial_show(self):
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

    def _on_destroy(self):
        self._battery.disconnect_by_func(self._on_battery_changed)


class MicrophoneIndicator(BaseNotchIndicator):
    def __init__(self, show_cb, hide_cb, **kwargs):
        self._audio = Audio()
        self._mic_muted = True
        super().__init__(
            name="notch-mic",
            icon_name="notch/mic-off.svg",
            label_text="Microphone",
            show_cb=show_cb,
            hide_cb=hide_cb,
            icon_first=False,
            **kwargs,
        )
        self._audio.connect("notify::microphone", self._on_mic_device_changed)
        if self._audio.microphone:
            self._connect_mic_signals()

    def _connect_mic_signals(self):
        mic = self._audio.microphone
        if mic is None:
            return
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
            self._icon.dynamic_file(
                "notch/mic-off.svg" if self._mic_muted else "notch/mic-on.svg"
            )

    def _on_destroy(self):
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
