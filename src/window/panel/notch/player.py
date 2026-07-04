from fabric.utils import os
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

from services.mpris import PlayerService
from utils.utils import svg_file


def _fmt_time(seconds: float) -> str:
    secs = int(seconds)
    if secs < 0:
        return "0:00"
    m = secs // 60
    s = secs % 60
    return f"{m}:{s:02d}"


class NotchPlayer(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._service: PlayerService | None = None

        self.fallback_icon = svg_file("music.svg", size=16)

        self.album_art = Box(
            name="notch-player-art",
            children=[self.fallback_icon],
        )

        self.time_label = Label(
            name="notch-player-time",
            markup="0:00",
        )

        self.player_box = CenterBox(
            orientation="h",
            h_expand=True,
            start_children=self.album_art,
            end_children=self.time_label,
        )

        self.add(self.player_box)

    def set_service(self, service: PlayerService | None):
        if self._service is service:
            return

        self._service = service

        if service is None:
            self.time_label.set_markup("0:00")
            self._show_fallback()
            return

        self._update_from_service()

    def _show_fallback(self):
        self.album_art.set_style("")
        self.fallback_icon.set_visible(True)

    def _show_artwork(self, path: str):
        self.fallback_icon.set_visible(False)
        self.album_art.set_style(f"background-image:url('{path}')")

    def _update_from_service(self):
        if self._service is None:
            return

        cached = self._service.get_artwork()
        if cached and os.path.exists(cached):
            self._show_artwork(cached)
        else:
            self._show_fallback()

        pos = self._service.position / 1_000_000
        self.time_label.set_markup(_fmt_time(pos))

    def _on_artwork_change(self, service, local_path: str):
        if os.path.exists(local_path):
            self._show_artwork(local_path)

    def _on_track_position(self, service, pos: float, dur: float):
        if self._service is service:
            self.time_label.set_markup(_fmt_time(pos))

    def destroy(self):
        self._service = None
        super().destroy()
