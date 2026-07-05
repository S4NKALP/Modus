import math
import os
import time

from fabric.utils import GLib, Gtk
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox

from services.mpris import PlayerService
from utils.utils import svg_file

# tunables
_BARS = 10  # number of bars
_TICK_MS = 150  # ~7 fps — smooth with sine, very cheap
_H_MIN = 3  # minimum total bar height (px, both halves)
_H_MAX = 22  # maximum total bar height (px)
_BAR_W = 1  # bar pixel width
_SPACING = 4  # gap between bars

# Per-bar sine speeds (rad/s) and phases — makes motion look organic
_SPEEDS = [2.1, 3.3, 1.8, 2.9, 3.7, 1.5, 2.6, 3.1, 1.9, 2.4]
_PHASES = [0.0, 1.2, 2.4, 0.8, 1.9, 3.1, 0.5, 2.0, 1.4, 0.3]

_IDLE_HEIGHTS = [_H_MIN] * _BARS


class Visualizer(Box):
    """
    Center-anchored bar visualizer with a magenta glow.
    Bars grow symmetrically up AND down from the centre line,
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._t0 = time.monotonic()
        self._heights = list(_IDLE_HEIGHTS)

        self.set_valign(Gtk.Align.CENTER)
        self.set_vexpand(False)

        # Fixed widget size so all bars always fit
        total_w = _BARS * _BAR_W + (_BARS - 1) * _SPACING
        self.set_size_request(total_w, _H_MAX + 4)  # +4 gives glow room
        self.set_style("margin-right: 8px; margin-bottom: 2px;")
        self.connect("draw", self._on_draw)

    def animate(self) -> None:
        t = time.monotonic() - self._t0
        new = [
            int(
                _H_MIN
                + (math.sin(t * _SPEEDS[i] + _PHASES[i]) + 1) * 0.5 * (_H_MAX - _H_MIN)
            )
            for i in range(_BARS)
        ]
        if new != self._heights:
            self._heights = new
            self.queue_draw()

    def reset(self) -> None:
        if self._heights != _IDLE_HEIGHTS:
            self._heights = list(_IDLE_HEIGHTS)
            self.queue_draw()

    def _on_draw(self, widget, cr) -> None:
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        if w < 3 or h < 4:
            return

        ctx = self.get_style_context()
        found, color = ctx.lookup_color("primary")
        if found:
            r, g, b = color.red, color.green, color.blue
        else:
            r, g, b = 1.0, 1.0, 1.0  # fallback: white

        cy = h / 2.0  # vertical centre line

        for i, bh in enumerate(self._heights):
            x = i * (_BAR_W + _SPACING)
            half = bh / 2.0
            top = cy - half

            cr.set_source_rgba(r, g, b, 0.22)
            cr.rectangle(x - 2, top - 2, _BAR_W + 4, bh + 4)
            cr.fill()

            cr.set_source_rgb(r, g, b)
            cr.rectangle(x, top, _BAR_W, bh)
            cr.fill()


class NotchPlayer(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._service: PlayerService | None = None
        self._timer: int | None = None
        self._sigs: list[int] = []

        self.fallback_icon = svg_file("music.svg", size=18)

        self.album_art = Box(
            name="notch-player-art",
            children=[self.fallback_icon],
        )

        self.visualizer = Visualizer()

        self.player_box = CenterBox(
            orientation="h",
            h_expand=True,
            start_children=self.album_art,
            end_children=self.visualizer,
        )
        self.add(self.player_box)

    def set_service(self, service: PlayerService | None) -> None:
        if self._service is service:
            return

        self._disconnect_signals()
        self._service = service
        self._stop_timer()
        self._show_fallback()

        if service is None:
            return

        self._update_from_service()
        self._sigs.append(service.connect("play", self._on_play))
        self._sigs.append(service.connect("pause", self._on_pause))

        if service.playback_status == "Playing":
            self._start_timer()

    def _disconnect_signals(self) -> None:
        if self._service is not None:
            for sid in self._sigs:
                try:
                    self._service.disconnect(sid)
                except Exception:
                    pass
        self._sigs.clear()

    def _on_play(self, *_) -> None:
        self._start_timer()

    def _on_pause(self, *_) -> None:
        self._stop_timer()

    def _start_timer(self) -> None:
        if self._timer is not None:
            return
        self._timer = GLib.timeout_add(_TICK_MS, self._tick)

    def _stop_timer(self) -> None:
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        self.visualizer.reset()

    def _tick(self) -> bool:
        if self._service is None:
            return False
        self.visualizer.animate()
        return True

    def _show_fallback(self) -> None:
        self.album_art.set_size_request(-1, -1)
        self.album_art.set_style("")
        self.fallback_icon.set_visible(True)

    def _show_artwork(self, path: str) -> None:
        self.fallback_icon.set_visible(False)
        self.album_art.set_size_request(18, 18)
        self.album_art.set_style(f"background-image:url('{path}')")

    def _update_from_service(self) -> None:
        if self._service is None:
            return
        cached = self._service.get_artwork()
        if cached and os.path.exists(cached):
            self._show_artwork(cached)
        else:
            self._show_fallback()

    def _on_artwork_change(self, service, local_path: str) -> None:
        if os.path.exists(local_path):
            self._show_artwork(local_path)

    def destroy(self) -> None:
        self._disconnect_signals()
        self._stop_timer()
        self._service = None
        super().destroy()
