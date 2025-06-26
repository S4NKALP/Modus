import contextlib
from typing import Optional

import gi
from fabric.core.service import Property, Service, Signal
from fabric.utils.helpers import get_enum_member_name, snake_case_to_kebab_case
from gi.repository import Playerctl
from loguru import logger

gi.require_version("Playerctl", "2.0")


class MediaPlayer(Service):
    """A service to manage a media player."""

    @Signal
    def exit(self) -> None: ...

    @Signal
    def metadata_changed(self) -> None: ...

    @Signal
    def playback_status_changed(self) -> None: ...

    @Property(str, flags="read-write")
    def player_name(self) -> str:
        return self._player.get_property("player_name")

    @Property(int, "read-write", default_value=0)
    def track_position(self) -> int:
        return self._player.get_property("position")

    @track_position.setter
    def track_position(self, new_pos: int):
        self._player.set_position(new_pos)

    @Property(str, flags="read-write")
    def album_image_url(self) -> str:
        return self._player.get_property("metadata").unpack().get("mpris:artUrl", None)

    @Property(int, flags="read-write")
    def track_duration(self) -> int:
        default_duration = minutes_to_microseconds(5)
        metadata = self._player.get_property("metadata").unpack()
        duration = metadata.get("mpris:length", default_duration)  # Default: 5 minutes
        return default_duration if duration == 0 else duration

    @Property(str, flags="readable")
    def status(self) -> str:
        return snake_case_to_kebab_case(
            get_enum_member_name(
                self._player.get_property("playback-status"),  # type: ignore
                default="unknown",
            )
        )

    @Property(str, flags="readable")
    def track(self) -> str:
        return (
            f"{self.track_artist} {self.track_title}"
            if self.player_name == "spotify"
            else self.track_title or "Music"
        )

    @Property(str, flags="readable")
    def track_title(self) -> str:
        return self._player.get_title()

    @Property(str, flags="readable")
    def track_artist(self) -> str:
        return self._player.get_artist()

    @Property(bool, "readable", default_value=False)
    def can_go_next(self) -> bool:
        return self._player.get_property("can_go_next")

    @Property(bool, "readable", default_value=False)
    def can_go_previous(self) -> bool:
        return self._player.get_property("can_go_previous")

    @Property(bool, "readable", default_value=False)
    def can_seek(self) -> bool:
        return self._player.get_property("can_seek")

    @Property(bool, "readable", default_value=False)
    def can_pause(self) -> bool:
        return self._player.get_property("can_pause")

    def __init__(self, player):
        super().__init__()
        self._player = player
        self._signal_connectors = {}

        signals = {
            "seeked": lambda *args: self.notify("track_position"),
            "playback-status": lambda *args: self._on_playback_status_changed(),
            "metadata": lambda *args: self._on_metadata_changed(),
            "exit": lambda *args: self._on_exit(),
        }

        for signal_name, handler in signals.items():
            self._signal_connectors[signal_name] = self._player.connect(
                signal_name, handler
            )

    def _on_playback_status_changed(self):
        self.notify("status")
        self.playback_status_changed.emit()

    def _on_metadata_changed(self):
        for prop in [
            "track_duration",
            "track_position",
            "track_title",
            "track_artist",
            "track",
            "album_image_url",
        ]:
            self.notify(prop)
        self.metadata_changed.emit()

    def _on_exit(self):
        for signal_id in self._signal_connectors.values():
            with contextlib.suppress(Exception):
                self._player.disconnect(signal_id)
        del self._player
        self.exit.emit()

    def play_pause(self):
        if self.can_pause:
            self._player.play_pause()

    def next(self):
        if self.can_go_next:
            self._player.next()

    def previous(self):
        if self.can_go_previous:
            self._player.previous()

    def get_position(self):
        return self._player.get_position() if self._player else 0


@staticmethod
def minutes_to_microseconds(minutes):
    return minutes * 60 * 1000000


class MediaManager(Service):
    """MediaManager Service using Playerctl to control media players"""

    @Signal
    def player_appeared(self) -> None: ...

    @Signal
    def player_vanished(self) -> None: ...

    @Property(list, "readable")
    def player_names(self):
        return self._manager.get_property("player_names")

    @Property(list[MediaPlayer], "readable")
    def players(self) -> list[MediaPlayer]:
        return self._players.values()

    @Property(MediaPlayer, "readable")
    def current_player(self) -> Optional[MediaPlayer]:
        current_player = None
        for player in self.players:
            if player.status == "playing":
                return player
            current_player = player
        return current_player

    def __init__(self):
        super().__init__()
        self._manager = Playerctl.PlayerManager()
        self._players: dict[str, MediaPlayer] = {}

        self._manager.connect(
            "name-appeared", lambda _, player: self._on_player_appeared(player=player)
        )
        self._manager.connect(
            "player-vanished", lambda _, player: self._on_player_vanished(player=player)
        )

        for player in self._manager.get_property("player-names"):
            self._on_player_appeared(player=player)

    def _on_player_appeared(self, player):
        """Callback when a new player appears"""
        player = Playerctl.Player.new_from_name(player)
        player_name = player.get_property("player_name")

        logger.info(f"[Media] New player appeared: {player_name}")

        self._manager.manage_player(player)
        self._players[player_name] = MediaPlayer(player=player)
        self.notify("current-player")
        self.player_appeared.emit()

    def _on_player_vanished(self, player):
        """Callback when a player disappears"""
        player_name = player.get_property("player_name") or "Unknown"
        logger.info(f"[Media] Player vanished: {player_name}")
        self._players.pop(player_name)
        self.notify("current-player")
        self.player_vanished.emit()
