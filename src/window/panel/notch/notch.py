from fabric.utils import Gdk, Gtk
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.shapes import Corner
from fabric.widgets.stack import Stack
from services.screencapture import screen_capture_service
from window.panel.notch.recording import RecordingIndicator
from window.panel.notch.player import NotchPlayer
from window.controlcenter.player import get_shared_mpris_manager


class Notch(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="panel-notch-wrap",
            orientation="h",
            spacing=0,
            v_align="center",
            h_align="center",
            h_expand=False,
            **kwargs,
        )

        self.recording_indicator = RecordingIndicator()
        self.recording_indicator.set_hexpand(True)
        self.recording_indicator.set_halign(Gtk.Align.FILL)

        self.player_widget = NotchPlayer()
        self.player_widget.set_hexpand(True)
        self.player_widget.set_halign(Gtk.Align.FILL)

        self._mpris = get_shared_mpris_manager()
        self._mpris.connect("new-player", self._on_new_player)
        self._mpris.connect("player-vanish", self._on_player_vanish)

        screen_capture_service.connect("recording-started", self._on_recording_started)
        screen_capture_service.connect("recording-stopped", self._on_recording_stopped)

        self._last_scroll_index = 0
        self._playing_services: list[str] = []

        self.notch_stack = Stack(
            name="panel-notch-stack",
            v_expand=True,
            h_expand=True,
            transition_type="crossfade",
            transition_duration=200,
            children=[self.recording_indicator, self.player_widget],
        )

        self.left_corner = Box(
            name="panel-notch-corner-left",
            orientation="v",
            h_align="start",
            children=[
                Corner(
                    name="panel-notch-corner",
                    orientation="top-right",
                    size=20,
                )
            ],
        )

        self.right_corner = Box(
            name="panel-notch-corner-right",
            orientation="v",
            h_align="end",
            children=[
                Corner(
                    name="panel-notch-corner",
                    orientation="top-left",
                    size=20,
                )
            ],
        )

        self.notch_box = CenterBox(
            name="panel-notch",
            orientation="h",
            h_align="center",
            v_align="center",
            start_children=self.left_corner,
            center_children=self.notch_stack,
            end_children=self.right_corner,
        )

        self.add(self.notch_box)

        self._init_state()

        self.connect("scroll-event", self._on_scroll)

    def _init_state(self):
        """One-time init: check current state, then rely on signals."""
        if screen_capture_service.is_recording:
            self.recording_indicator.start_timer()

        for name, svc in self._mpris.get_all_services().items():
            if svc.playback_status.lower() == "playing":
                self._playing_services.append(name)
            svc.connect("play", self._on_any_play)
            svc.connect("pause", self._on_any_pause)
            svc.connect("artwork-change", self._on_any_artwork)
            svc.connect("track-position", self._on_any_position)

        self._apply_stack_state()

    def _on_new_player(self, manager, name: str, service):
        service.connect("play", self._on_any_play)
        service.connect("pause", self._on_any_pause)
        service.connect("artwork-change", self._on_any_artwork)
        service.connect("track-position", self._on_any_position)

        if service.playback_status.lower() == "playing":
            self._playing_services.append(name)
            self._apply_stack_state()

    def _on_recording_started(self, service, path: str):
        self.recording_indicator.start_timer()
        self._apply_stack_state()

    def _on_recording_stopped(self, service, path: str):
        self.recording_indicator.stop_timer()
        self._apply_stack_state()

    def _on_any_artwork(self, service, local_path: str):
        self.player_widget._on_artwork_change(service, local_path)

    def _on_any_position(self, service, pos: float, dur: float):
        self.player_widget._on_track_position(service, pos, dur)

    def _on_player_vanish(self, manager, name: str):
        if name in self._playing_services:
            self._playing_services.remove(name)
            self._apply_stack_state()

    def _on_any_play(self, service):
        if service.player_name not in self._playing_services:
            self._playing_services.append(service.player_name)
        self._apply_stack_state()

    def _on_any_pause(self, service):
        if service.player_name in self._playing_services:
            self._playing_services.remove(service.player_name)
        self._apply_stack_state()

    def _on_scroll(self, widget, event):
        if event.direction == Gdk.ScrollDirection.UP:
            self._last_scroll_index -= 1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self._last_scroll_index += 1
        else:
            return

        self._apply_stack_state()

    def _apply_stack_state(self):
        is_recording = screen_capture_service.is_recording
        has_playing = len(self._playing_services) > 0

        if has_playing:
            name = self._playing_services[0]
            svc = self._mpris.get_player_service(name)
            self.player_widget.set_service(svc)
        else:
            self.player_widget.set_service(None)

        active_pages = []
        if is_recording:
            active_pages.append(0)
        if has_playing:
            active_pages.append(1)

        if not active_pages:
            if self.get_visible():
                self.set_visible(False)
            return

        if not self.get_visible():
            self.set_visible(True)

        if len(active_pages) == 1:
            target = active_pages[0]
        else:
            idx = self._last_scroll_index % len(active_pages)
            target = active_pages[idx]

        current = self.notch_stack.get_visible_child()
        desired = self.recording_indicator if target == 0 else self.player_widget

        if current != desired:
            self.notch_stack.set_visible_child(desired)

    def destroy(self):
        self.recording_indicator.destroy()
        self.player_widget.destroy()
        super().destroy()
