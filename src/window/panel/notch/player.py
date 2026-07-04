import random

from fabric.utils import Gtk, GLib, os
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox

from services.mpris import PlayerService
from utils.utils import svg_file


class Visualizer(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._heights = [4, 4, 4]
        self.set_valign(Gtk.Align.CENTER)
        self.set_vexpand(False)
        self.set_size_request(-1, 20)
        self.set_style("margin-right: 8px; margin-bottom: 2px; padding: 0 4px;")
        self.connect("draw", self._on_draw)

    def set_heights(self, heights):
        self._heights = heights
        self.queue_draw()

    def _on_draw(self, widget, cr):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        n = len(self._heights)
        if n == 0 or w < 3 or h < 4:
            return

        spacing = 3
        bar_w = max(3, (w - spacing * (n - 1)) // n)
        cr.set_source_rgb(1, 1, 1)

        for i, bh in enumerate(self._heights):
            x = i * (bar_w + spacing)
            y = h - bh
            cr.rectangle(x, y, bar_w, bh)
            cr.fill()


class NotchPlayer(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._service: PlayerService | None = None
        self._vis_timeout = None

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

    def set_service(self, service: PlayerService | None):
        if self._service is service:
            return

        self._service = service

        self._stop_visualizer()
        self._show_fallback()

        if service is not None:
            self._update_from_service()
            self._start_visualizer()

    def _start_visualizer(self):
        if self._vis_timeout is not None:
            return
        self._vis_timeout = GLib.timeout_add(200, self._animate_bars)

    def _stop_visualizer(self):
        if self._vis_timeout is not None:
            GLib.source_remove(self._vis_timeout)
            self._vis_timeout = None

    def _animate_bars(self):
        if self._service is None:
            self._stop_visualizer()
            return False

        playing = self._service.playback_status
        if playing != "Playing":
            self.visualizer.set_heights([4, 4, 4])
            return True

        heights = [random.randint(4, 20) for _ in range(3)]
        self.visualizer.set_heights(heights)
        return True

    def _show_fallback(self):
        self.album_art.set_size_request(-1, -1)
        self.album_art.set_style("")
        self.fallback_icon.set_visible(True)

    def _show_artwork(self, path: str):
        self.fallback_icon.set_visible(False)
        self.album_art.set_size_request(18, 18)
        self.album_art.set_style(f"background-image:url('{path}')")

    def _update_from_service(self):
        if self._service is None:
            return

        cached = self._service.get_artwork()
        if cached and os.path.exists(cached):
            self._show_artwork(cached)
        else:
            self._show_fallback()

    def _on_artwork_change(self, service, local_path: str):
        if os.path.exists(local_path):
            self._show_artwork(local_path)

    def destroy(self):
        self._stop_visualizer()
        self._service = None
        super().destroy()
