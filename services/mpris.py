import gi
from gi.repository import GLib, Playerctl

from config.data import ALLOWED_PLAYERS
from fabric import Fabricator
from fabric.core.service import Service, Signal

gi.require_version("Playerctl", "2.0")


class PlayerService(Service):
    @Signal
    def shuffle_toggle(self, player: Playerctl.Player, status: bool) -> None: ...

    @Signal
    def meta_change(self, metadata: GLib.Variant, player: Playerctl.Player) -> None: ...

    @Signal
    def pause(self) -> None: ...

    @Signal
    def play(self) -> None: ...

    @Signal
    def track_position(self, pos: float, dur: float) -> None: ...

    def __init__(self, player: Playerctl.Player, **kwargs):
        self._player: Playerctl.Player = player
        super().__init__(**kwargs)
        if player.props.player_name in ALLOWED_PLAYERS:
            self._player.connect("playback-status::playing", self.on_play)
            self._player.connect("playback-status::paused", self.on_pause)
            self._player.connect("shuffle", self.on_shuffle)
            self._player.connect("metadata", self.on_metadata)
            self._player.connect("seeked", self.on_seeked)

        self.status = self._player.props.playback_status
        self.pos_fabricator = Fabricator(
            interval=1000,  # 1s
            poll_from=lambda f, *_: self._safe_get_position(),
            on_changed=lambda f, *_: self.fabricating(),
        )
        # Add state tracking to prevent repeated operations
        self._fabricator_running = False
        self._cleanup_done = False
        self.poll_progress()

    def _safe_get_position(self):
        """Safely get player position with error handling"""
        try:
            if not self._player or self._cleanup_done:
                return 0
            return self._player.get_position()
        except Exception:
            # Player is no longer available, stop the fabricator
            if (
                hasattr(self, "pos_fabricator")
                and self.pos_fabricator
                and self._fabricator_running
            ):
                try:
                    self.pos_fabricator.stop()
                    self._fabricator_running = False
                except Exception:
                    pass
            return 0

    def cleanup(self):
        """Clean up resources when service is no longer needed"""
        if self._cleanup_done:
            return  # Already cleaned up

        try:
            if hasattr(self, "pos_fabricator") and self.pos_fabricator:
                if self._fabricator_running:
                    self.pos_fabricator.stop()
                    self._fabricator_running = False
                self.pos_fabricator = None
            self._cleanup_done = True
        except Exception as e:
            print(f"[DEBUG] Error during PlayerService cleanup: {e}")

    def on_seeked(self, player, position):
        if (
            not self._cleanup_done
            and self.status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
            and not self._fabricator_running
        ):
            try:
                self.pos_fabricator.start()
                self._fabricator_running = True
            except Exception:
                pass  # Ignore if already started

    def set_position(self, pos: float):
        if not self._cleanup_done and self._fabricator_running:
            try:
                self.pos_fabricator.stop()
                self._fabricator_running = False
            except Exception:
                pass  # Ignore if already stopped

        micro_pos = int(pos * 1_000_000)
        try:
            self._player.set_position(micro_pos)
        except GLib.Error as e:
            print(f"Failed to seek: {e}")

    def poll_progress(self):
        if self._cleanup_done:
            return  # Don't operate on cleaned up fabricator

        if self.status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING":
            if not self._fabricator_running:
                try:
                    self.pos_fabricator.start()
                    self._fabricator_running = True
                except Exception:
                    pass  # Ignore if already started
        else:
            if self._fabricator_running:
                try:
                    self.pos_fabricator.stop()
                    self._fabricator_running = False
                except Exception:
                    pass  # Ignore if already stopped

    def fabricating(self):
        try:
            # Check if cleanup has been done
            if self._cleanup_done:
                return

            # Validate player object
            if not self._player or not hasattr(self._player, "get_position"):
                return

            # Get position safely
            try:
                pos = self._player.get_position() / 1_000_000  # seconds
            except Exception:
                # Player is no longer available, stop fabricator
                if self._fabricator_running:
                    try:
                        self.pos_fabricator.stop()
                        self._fabricator_running = False
                    except Exception:
                        pass
                return

            # Get duration safely from multiple sources
            dur = 0.0  # Default to 0

            if (
                hasattr(self._player, "props")
                and hasattr(self._player.props, "metadata")
                and self._player.props.metadata
            ):
                metadata = self._player.props.metadata

                # Try mpris:length first (most common)
                try:
                    raw_dur = metadata["mpris:length"]
                    if raw_dur and raw_dur > 0:
                        dur = float(raw_dur) / 1_000_000  # seconds
                except (KeyError, Exception):
                    pass

                # Fallback to xesam:duration (alternative field)
                if dur <= 0:
                    try:
                        raw_dur = metadata["xesam:duration"]
                        if raw_dur and raw_dur > 0:
                            dur = float(raw_dur) / 1_000_000  # seconds
                    except (KeyError, Exception):
                        pass

                # Try to get duration from player directly (some players support this)
                if dur <= 0:
                    try:
                        if hasattr(self._player, "get_metadata"):
                            player_metadata = self._player.get_metadata()
                            if player_metadata:
                                raw_dur = player_metadata["mpris:length"]
                                if raw_dur and raw_dur > 0:
                                    dur = float(raw_dur) / 1_000_000
                    except (KeyError, Exception):
                        pass

            # Validate values before emitting signal
            # Allow dur=0 for position-only tracking
            if pos is not None and dur is not None and pos >= 0 and dur >= 0:
                self.track_position(pos, dur)

        except Exception:
            pass

    def on_play(self, player, status):
        self.status = player.props.playback_status
        self.poll_progress()
        self.play()

    def on_pause(self, player, status):
        self.poll_progress()
        self.pause()

    def on_shuffle(self, player, status):
        self.shuffle_toggle(player, status)

    def on_metadata(self, player, metadata):
        keys = metadata.keys()
        self.meta_change(metadata, player)


class PlayerManager(Service):
    @Signal
    def new_player(self, player: Playerctl.Player) -> Playerctl.Player: ...

    @Signal
    def player_vanish(self, player: Playerctl.Player) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._manager = Playerctl.PlayerManager()
        self._manager.connect("name-appeared", self._on_name_appeared, self._manager)
        self._manager.connect(
            "player-vanished", self._on_player_vanished, self._manager
        )

        self._players = {}

    def init_all_players(self):
        # invoked in the UI
        for player_obj in self._manager.props.player_names:
            name_str = player_obj.name
            if name_str in ALLOWED_PLAYERS:
                player = Playerctl.Player.new_from_name(player_obj)
                self._manager.manage_player(player)
                self.new_player(player)

    def _on_name_appeared(self, sender, name, manager):
        name_str = name.name
        if name_str in ALLOWED_PLAYERS:
            player = Playerctl.Player.new_from_name(name)
            self._manager.manage_player(player)
            self.new_player(player)

    def _on_player_vanished(self, sender, player, manager):
        self.player_vanish(player)
