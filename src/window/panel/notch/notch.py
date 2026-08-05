from fabric.utils import Gdk, GLib, Gtk, logger
from fabric.widgets.box import Box
from fabric.widgets.stack import Stack

from services.modus import screen_recorder_service
from window.controlcenter.player import get_shared_mpris_manager
from window.panel.notch.indicators import (
    CapsLockIndicator,
    ChargingIndicator,
    KeyboardLayoutIndicator,
    MicrophoneIndicator,
    NumLockIndicator,
)
from window.panel.notch.pill import NotchPill
from window.panel.notch.player import NotchPlayer
from window.panel.notch.recording import RecordingIndicator


class Notch(NotchPill):
    def __init__(self, idle_widget=None, **kwargs):
        self.recording_indicator = RecordingIndicator()
        self.recording_indicator.set_hexpand(True)
        self.recording_indicator.set_halign(Gtk.Align.FILL)

        self.player_widget = NotchPlayer()
        self.player_widget.set_hexpand(True)
        self.player_widget.set_halign(Gtk.Align.FILL)

        self.idle_widget = (
            idle_widget
            if idle_widget is not None
            else Box(name="notch-idle", h_expand=True)
        )

        self._last_scroll_index = 0
        self._last_scroll_time = 0
        self._last_recording_check = 0
        self._is_active_recording = False
        self._music_services: list[str] = []
        # Must be set BEFORE indicator widgets are created
        self._transient_active = False

        # Transient indicator pages — shown on change, hidden after 2 s
        self.kbd_indicator = KeyboardLayoutIndicator(
            show_cb=self._show_transient,
            hide_cb=self._hide_transient,
        )
        self.caps_indicator = CapsLockIndicator(
            show_cb=self._show_transient,
            hide_cb=self._hide_transient,
        )
        self.num_indicator = NumLockIndicator(
            show_cb=self._show_transient,
            hide_cb=self._hide_transient,
        )
        self.mic_indicator = MicrophoneIndicator(
            show_cb=self._show_transient,
            hide_cb=self._hide_transient,
        )
        # Persistent indicator — now also transient (2s), deferred via idle_add
        self.charging_indicator = ChargingIndicator(
            show_cb=self._show_transient,
            hide_cb=self._hide_transient,
        )

        self._mpris = get_shared_mpris_manager()
        self._mpris.connect("new-player", self._on_new_player)
        self._mpris.connect("player-vanish", self._on_player_vanish)

        screen_recorder_service.connect("started", self._on_recording_started)
        screen_recorder_service.connect("stopped", self._on_recording_stopped)

        self.notch_stack = Stack(
            name="panel-notch-stack",
            v_expand=True,
            h_expand=True,
            transition_type="none",
            children=[
                self.idle_widget,
                self.recording_indicator,
                self.player_widget,
                self.kbd_indicator,
                self.caps_indicator,
                self.num_indicator,
                self.mic_indicator,
                self.charging_indicator,
            ],
        )
        self._last_stack_page = 0

        super().__init__(center_widget=self.notch_stack, **kwargs)

        self._init_state()

        self.notch_stack.connect("scroll-event", self._on_scroll)

    # Transient indicator show / hide

    def _show_transient(self, widget):
        """Make a transient indicator the visible notch page."""
        self._transient_active = True
        if self.notch_stack.get_visible_child() != widget:
            self.notch_stack.set_visible_child(widget)

    def _hide_transient(self):
        """Return to normal notch state after the indicator timer expires."""
        self._transient_active = False
        self._apply_stack_state()

    # Init / MPRIS / recording

    def _init_state(self):
        self._is_active_recording = screen_recorder_service.recording
        if self._is_active_recording:
            self.recording_indicator.start_timer()

        for name, svc in self._mpris.get_all_services().items():
            self._music_services.append(name)
            svc.connect("artwork-change", self._on_any_artwork)

        self._apply_stack_state()

    def _on_new_player(self, _manager, name: str, service):
        service.connect("artwork-change", self._on_any_artwork)
        if name not in self._music_services:
            self._music_services.append(name)
            self._apply_stack_state()

    def _on_recording_started(self, service, path: str):
        self._is_active_recording = True
        self.recording_indicator.start_timer()
        self._apply_stack_state()

    def _on_recording_stopped(self, service, path: str):
        self._is_active_recording = False
        self.recording_indicator.stop_timer()
        self._apply_stack_state()

    def _on_any_artwork(self, service, local_path: str):
        self.player_widget._on_artwork_change(service, local_path)

    def _on_player_vanish(self, _manager, name: str):
        if name in self._music_services:
            self._music_services.remove(name)
            try:
                svc = self._mpris.get_player_service(name)
                if svc is not None:
                    svc.disconnect_by_func(self._on_any_artwork)
            except Exception as e:
                logger.warning(
                    f"[notch] svc = self._mpris.get_player_service(name) failed: {e}"
                )
            self._apply_stack_state()

    # Scroll

    def _on_scroll(self, widget, event):
        now = GLib.get_monotonic_time()
        if now - self._last_scroll_time < 100_000:
            return True
        self._last_scroll_time = now

        # Cancel transient indicator so scroll can navigate
        if self._transient_active:
            self._transient_active = False

        dy = 0
        if event.direction == Gdk.ScrollDirection.UP:
            dy = -1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            dy = 1
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            if event.delta_y < -0.1:
                dy = -1
            elif event.delta_y > 0.1:
                dy = 1
            else:
                return True
        else:
            return True

        self._last_scroll_index += dy
        self._apply_stack_state()
        return True

    # Stack state

    def _apply_stack_state(self):
        # Don't override a transient indicator that is still counting down
        if self._transient_active:
            return

        is_recording = self._is_active_recording

        now = GLib.get_monotonic_time()
        if now - self._last_recording_check > 3_000_000:
            self._last_recording_check = now
            if self._is_active_recording and not screen_recorder_service.recording:
                self._is_active_recording = False
                is_recording = False
                self.recording_indicator.stop_timer()

        has_music = len(self._music_services) > 0

        if has_music:
            name = self._music_services[0]
            svc = self._mpris.get_player_service(name)
            self.player_widget.set_service(svc)
        else:
            self.player_widget.set_service(None)

        active_pages = []
        if is_recording:
            active_pages.append(1)
        if has_music:
            active_pages.append(2)

        if not active_pages:
            if self.notch_stack.get_visible_child() != self.idle_widget:
                self.notch_stack.set_visible_child(self.idle_widget)
            return

        pages = {
            1: self.recording_indicator,
            2: self.player_widget,
        }

        if len(active_pages) == 1:
            target = active_pages[0]
        else:
            target = active_pages[self._last_scroll_index % len(active_pages)]

        desired = pages[target]

        if self.notch_stack.get_visible_child() != desired:
            self.notch_stack.set_visible_child(desired)

    def destroy(self):
        self.recording_indicator.destroy()
        self.player_widget.destroy()
        self.kbd_indicator.destroy()
        self.caps_indicator.destroy()
        self.num_indicator.destroy()
        self.mic_indicator.destroy()
        self.charging_indicator.destroy()
        super().destroy()
