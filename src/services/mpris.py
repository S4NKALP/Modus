import hashlib
import mimetypes
import urllib.parse
import urllib.request
from pathlib import Path

import gi
from fabric.utils import GLib, logger

gi.require_version("Playerctl", "2.0")
from fabric import Fabricator  # noqa: E402
from fabric.core.service import Property, Service, Signal  # noqa: E402
from gi.repository import Playerctl  # noqa: E402

from shared.data import CACHE_DIR  # noqa: E402

TEMP_DIR = CACHE_DIR


class PlayerService(Service):
    @Signal
    def meta_change(self, metadata: GLib.Variant, player: Playerctl.Player) -> None: ...

    @Signal
    def artwork_change(self, local_path: str) -> None: ...

    @Signal
    def pause(self) -> None: ...

    @Signal
    def play(self) -> None: ...

    @Signal
    def track_position(self, pos: float, dur: float) -> None: ...

    @Property(bool, "readable", default_value=False)
    def can_go_previous(self) -> bool:
        return self._player.get_property("can_go_previous")

    @Property(bool, "readable", default_value=False)
    def can_go_next(self) -> bool:
        return self._player.get_property("can_go_next")

    @Property(bool, "readable", default_value=False)
    def can_pause(self) -> bool:
        return self._player.get_property("can_pause")

    @Property(bool, "readable", default_value=False)
    def can_play(self) -> bool:
        return self._player.get_property("can_play")

    @Property(bool, "readable", default_value=False)
    def can_seek(self) -> bool:
        return self._player.get_property("can_seek")

    @Property(bool, "readable", default_value=False)
    def can_control(self) -> bool:
        return self._player.get_property("can_control")

    @Property(str, "readable", default_value="")
    def player_name(self) -> str:
        try:
            return self._player.props.player_name or ""
        except Exception:
            return ""

    @Property(str, "readable", default_value="")
    def arturl(self) -> str:
        try:
            return self._player.props.metadata["mpris:artUrl"] or ""
        except Exception:
            return ""

    @Property(str, "readable", default_value="")
    def title(self) -> str:
        try:
            return self._player.get_title() or ""
        except Exception:
            return ""

    @Property(object, "readable")
    def artist(self) -> list:
        try:
            return list(self._player.props.metadata["xesam:artist"]) or []
        except Exception:
            return []

    @Property(str, "readable", default_value="")
    def album(self) -> str:
        try:
            return self._player.props.metadata["xesam:album"] or ""
        except Exception:
            return ""

    @Property(str, "readable", default_value="Stopped")
    def playback_status(self) -> str:
        try:
            val = int(self._player.props.playback_status)
            if val == 0:
                return "Playing"
            elif val == 1:
                return "Paused"
            else:
                return "Stopped"
        except Exception:
            return "Stopped"

    @Property(int, "readable", default_value=0)
    def length(self) -> int:
        try:
            return int(self._player.props.metadata["mpris:length"])
        except Exception:
            return 0

    @Property(int, "readable", default_value=0)
    def position(self) -> int:
        try:
            return int(self._player.get_position())
        except Exception:
            return 0

    def play_pause(self, *_):
        try:
            self._player.play_pause()
        except Exception as e:
            logger.warning(f"play_pause failed: {e}")

    def next(self, *_):
        try:
            self._player.next()
        except Exception as e:
            logger.warning(f"next failed: {e}")

    def previous(self, *_):
        try:
            self._player.previous()
        except Exception as e:
            logger.warning(f"previous failed: {e}")

    def __init__(self, player: Playerctl.Player, **kwargs):
        super().__init__(**kwargs)
        self._player: Playerctl.Player = player
        self._current_artwork_hash = ""
        self._current_artwork_path = ""
        self._is_cleaning_up = False
        self._cached_playback_status = int(self._player.props.playback_status)
        self._signal_ids = []

        self._signal_ids.append(
            self._player.connect("playback-status", self.on_playback_status)
        )
        self._signal_ids.append(self._player.connect("metadata", self.on_metadata))
        self._signal_ids.append(self._player.connect("seeked", self.on_seeked))

        self.status = self._player.props.playback_status
        self._last_polled_status = self.playback_status
        self.pos_fabricator = Fabricator(
            interval=1000,
            poll_from=lambda f, *_: self.get_position(),
            on_changed=lambda f, *_: self.fabricating(),
        )
        self.status_fabricator = Fabricator(
            interval=250,
            poll_from=lambda f, *_: self.playback_status,
            on_changed=lambda f, value: self._on_polled_status_change(value),
        )
        self.status_fabricator.start()
        self.poll_progress()

        try:
            metadata = self._player.props.metadata
            if metadata:
                self.meta_change(metadata, self._player)
                self._handle_artwork(metadata)
        except Exception as e:
            logger.warning(f"Failed to initialize metadata: {e}")

    def get_artwork(self) -> str:
        return self._current_artwork_path

    def get_position(self) -> float:
        if self._is_cleaning_up:
            return 0
        try:
            return self._player.get_position()
        except Exception as e:
            logger.warning(f"Could not get position: {e}")
            return 0

    def seek_position(self, pos: float):
        if self._is_cleaning_up:
            return
        self.pos_fabricator.stop()
        current = self.get_position() / 1_000_000
        try:
            self._player.set_position(int(pos * 1_000_000))
        except Exception:
            try:
                offset = pos - current
                self._player.seek(int(offset * 1_000_000))
            except Exception:
                import os

                os.system(f"playerctl -p {self.player_name} position {pos}")
        finally:
            if self.playback_status.lower() == "playing":
                self.pos_fabricator.start()

    def seek(self, offset: float):
        if self._is_cleaning_up:
            return
        self.pos_fabricator.stop()
        try:
            self._player.seek(int(offset * 1_000_000))
        except GLib.Error as e:
            logger.error(f"Failed to seek: {e}")
        finally:
            if self.playback_status.lower() == "playing":
                self.pos_fabricator.start()

    def poll_progress(self):
        if self._is_cleaning_up:
            return
        if self.playback_status.lower() == "playing":
            self.pos_fabricator.start()
        else:
            self.pos_fabricator.stop()

    def fabricating(self, metadata=None):
        if self._is_cleaning_up:
            return
        try:
            pos = self._player.get_position() / 1_000_000
        except GLib.Error as e:
            logger.warning(f"Failed to get position: {e}")
            return
        dur = 0
        if metadata is None:
            try:
                metadata = self._player.props.metadata
            except Exception:
                metadata = None
        if metadata is not None:
            try:
                dur = metadata["mpris:length"] / 1_000_000
            except Exception:
                dur = 0
        self.track_position(pos, dur)

    def on_seeked(self, player, position):
        if self._is_cleaning_up:
            return
        if self.playback_status.lower() == "playing":
            self.pos_fabricator.start()

    def on_playback_status(self, player, status):
        """DBus signal handler - instant when it fires (e.g. Modus buttons)."""
        if self._is_cleaning_up:
            return
        self.status = status
        self.poll_progress()
        if self.playback_status.lower() == "playing":
            self.play()
        else:
            self.pause()

    def _on_polled_status_change(self, new_status: str):
        """Fabricator-driven status change - fires reliably every second."""
        if self._is_cleaning_up:
            return
        self.poll_progress()
        if new_status.lower() == "playing":
            self.play()
        else:
            self.pause()

    def on_metadata(self, player, metadata):
        if self._is_cleaning_up:
            return
        self.meta_change(metadata, player)
        self._handle_artwork(metadata)
        self.fabricating(metadata)

    def _handle_artwork(self, metadata):
        if self._is_cleaning_up:
            return
        try:
            art_url = metadata["mpris:artUrl"]
        except Exception:
            return
        artwork_hash = hashlib.md5(art_url.encode()).hexdigest()

        if artwork_hash == self._current_artwork_hash:
            return

        self._current_artwork_hash = artwork_hash
        parsed = urllib.parse.urlparse(art_url)

        if parsed.scheme == "file":
            self._set_artwork(urllib.parse.unquote(parsed.path))
        elif parsed.scheme in ("http", "https"):
            GLib.Thread.new(
                "download-artwork",
                self._download_artwork,
                art_url,
                artwork_hash,
            )

    def _set_artwork(self, path: str):
        self._current_artwork_path = path
        self.artwork_change(path)

    def _download_artwork(self, art_url: str, artwork_hash: str):
        if self._is_cleaning_up:
            return
        try:
            cache_dir = TEMP_DIR / "player-art"
            cache_dir.mkdir(parents=True, exist_ok=True)

            filename_hash = hashlib.md5(art_url.encode()).hexdigest()
            parsed = urllib.parse.urlparse(art_url)

            local_arturl = None
            url_suffix = Path(parsed.path).suffix
            if url_suffix:
                test_path = cache_dir / f"{filename_hash}{url_suffix}"
                if test_path.exists():
                    local_arturl = test_path
            else:
                existing = list(cache_dir.glob(f"{filename_hash}.*"))
                if existing:
                    local_arturl = existing[0]

            if not local_arturl:
                with urllib.request.urlopen(art_url, timeout=5) as response:
                    data = response.read()
                    suffix = (
                        mimetypes.guess_extension(response.info().get_content_type())
                        or ".png"
                    )
                    local_arturl = cache_dir / f"{filename_hash}{suffix}"
                    tmp = local_arturl.with_suffix(".tmp")
                    tmp.write_bytes(data)
                    tmp.replace(local_arturl)

            GLib.idle_add(self._set_artwork, str(local_arturl))

        except Exception as e:
            logger.error(f"Failed to download artwork: {e}")

    def cleanup(self):
        if self._is_cleaning_up:
            return
        self._is_cleaning_up = True

        try:
            if hasattr(self, "pos_fabricator"):
                self.pos_fabricator.stop()
        except Exception as e:
            logger.error(f"Error stopping fabricator: {e}")

        try:
            if hasattr(self, "status_fabricator"):
                self.status_fabricator.stop()
        except Exception as e:
            logger.error(f"Error stopping status fabricator: {e}")

        for signal_id in self._signal_ids:
            try:
                self._player.disconnect(signal_id)
            except Exception as e:
                logger.warning(f"Error disconnecting signal: {e}")
        self._signal_ids.clear()
        self._current_artwork_path = ""


class PlayerManager(Service):
    _instance = None

    @Signal
    def new_player(self, player_name: str, service: PlayerService) -> None: ...

    @Signal
    def player_vanish(self, player_name: str) -> None: ...

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_singleton()
        return cls._instance

    def _init_singleton(self):
        super().__init__()
        self._manager = Playerctl.PlayerManager()
        self._services: dict[str, PlayerService] = {}
        self._player_objects: dict[str, Playerctl.Player] = {}

        self._manager.connect("name-appeared", self._on_name_appeared, self._manager)
        self._manager.connect(
            "player-vanished", self._on_player_vanished, self._manager
        )
        self._init_existing_players()

    def _init_existing_players(self):
        for player_obj in self._manager.props.player_names:
            self._create_player(player_obj)

    def _create_player(self, name_obj):
        name_str = name_obj.name
        if name_str in self._services:
            return
        try:
            player = Playerctl.Player.new_from_name(name_obj)
            self._manager.manage_player(player)
            service = PlayerService(player)
            self._services[name_str] = service
            self._player_objects[name_str] = player
            self.new_player(name_str, service)
        except Exception as e:
            logger.error(f"Failed to create player {name_str}: {e}")

    def _on_name_appeared(self, sender, name, manager):
        self._create_player(name)

    def _on_player_vanished(self, sender, player, manager):
        name = player.props.player_name
        if name in self._services:
            self._services[name].cleanup()
            del self._services[name]
        self._player_objects.pop(name, None)
        self.player_vanish(name)

    def get_player_service(self, name: str) -> PlayerService | None:
        return self._services.get(name)

    def get_all_services(self) -> dict[str, PlayerService]:
        return self._services.copy()
