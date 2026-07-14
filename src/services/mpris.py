import hashlib
import mimetypes
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import gi
from fabric.utils import GLib, exec_shell_command_async, logger

gi.require_version("Playerctl", "2.0")
from fabric import Fabricator  # noqa: E402
from fabric.core.service import Property, Service, Signal  # noqa: E402
from gi.repository import Playerctl  # noqa: E402

from shared.data import CACHE_DIR  # noqa: E402

TEMP_DIR = CACHE_DIR

# Native Linux media artwork cache (libmediaart). Optional: when the GI
# namespace is unavailable we transparently fall back to our own cache dir,
# so the service keeps working without adding a hard dependency.
try:
    gi.require_version("MediaArt", "2.0")
    from gi.repository import MediaArt

    _MEDIAART_AVAILABLE = True
except (ValueError, ImportError):
    MediaArt = None
    _MEDIAART_AVAILABLE = False


def _mediaart_cache_path(artist: str | None, album: str | None, title: str | None):
    """Standard media-art cache path for a track, or None when unavailable.

    Does NOT download; merely derives the canonical cache location so we can
    both look artwork up and store new downloads following the same rules.
    """
    if not _MEDIAART_AVAILABLE:
        return None
    try:
        result = MediaArt.get_path(
            artist or None, album or None, title or None, MediaArt.Type.ALBUM
        )
    except Exception as e:
        logger.debug(f"MediaArt.get_path failed: {e}")
        return None
    # PyGObject return shape varies by version: (found, path, uri) or (path, uri).
    if isinstance(result, tuple):
        if len(result) == 3:
            found, path, _uri = result
        elif len(result) == 2:
            found, path = True, result[0]
        else:
            return None
        return path if found else None
    return result


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
    def can_seek(self) -> bool:
        return self._player.get_property("can_seek")

    @Property(str, "readable", default_value="")
    def player_name(self) -> str:
        try:
            return self._player.props.player_name or ""
        except Exception as e:
            logger.warning(
                f"[mpris] return self._player.props.player_name or '' failed: {e}"
            )
            return ""

    @Property(str, "readable", default_value="")
    def title(self) -> str:
        try:
            return self._player.get_title() or ""
        except Exception as e:
            logger.warning(f"[mpris] return self._player.get_title() or '' failed: {e}")
            return ""

    @Property(object, "readable")
    def artist(self) -> list:
        try:
            return list(self._player.props.metadata["xesam:artist"]) or []
        except Exception as e:
            logger.warning(
                f"[mpris] return list(self._player.props.metadata['xesam:artist']) ... failed: {e}"
            )
            return []

    @Property(str, "readable", default_value="")
    def album(self) -> str:
        try:
            return self._player.props.metadata["xesam:album"] or ""
        except Exception as e:
            logger.warning(
                f"[mpris] return self._player.props.metadata['xesam:album'] or '' failed: {e}"
            )
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
        except Exception as e:
            logger.warning(
                f"[mpris] val = int(self._player.props.playback_status) failed: {e}"
            )
            return "Stopped"

    @Property(int, "readable", default_value=0)
    def length(self) -> int:
        try:
            return int(self._player.props.metadata["mpris:length"])
        except Exception as e:
            logger.warning(
                f"[mpris] return int(self._player.props.metadata['mpris:length']) failed: {e}"
            )
            return 0

    @Property(int, "readable", default_value=0)
    def position(self) -> int:
        try:
            return int(self._player.get_position())
        except Exception as e:
            logger.warning(
                f"[mpris] return int(self._player.get_position()) failed: {e}"
            )
            return 0

    def play_pause(self, *_):
        try:
            self._player.play_pause()
        except GLib.Error as e:
            logger.warning(f"play_pause failed: {e}")

    def next(self, *_):
        try:
            self._player.next()
        except GLib.Error as e:
            logger.warning(f"next failed: {e}")

    def previous(self, *_):
        try:
            self._player.previous()
        except GLib.Error as e:
            logger.warning(f"previous failed: {e}")

    def __init__(self, player: Playerctl.Player, **kwargs):
        super().__init__(**kwargs)
        self._player: Playerctl.Player = player
        self._current_artwork_hash = ""
        self._current_artwork_path = ""
        self._is_cleaning_up = False
        self._signal_ids = []
        self._last_emitted_status = ""

        self._signal_ids.append(
            self._player.connect("playback-status", self.on_playback_status)
        )
        self._signal_ids.append(self._player.connect("metadata", self.on_metadata))
        self._signal_ids.append(self._player.connect("seeked", self.on_seeked))

        self._pos_polling = False  # guard: Fabricator.start() blindly creates a new
        # GLib timer every call — this flag prevents stacking
        self.pos_fabricator = Fabricator(
            interval=2000,
            poll_from=lambda f, *_: self.get_position(),
            on_changed=lambda f, *_: self.fabricating(),
        )
        self.status_fabricator = Fabricator(
            interval=5000,
            poll_from=lambda f, *_: self.playback_status,
            on_changed=lambda f, value: self._on_polled_status_change(value),
        )
        self.status_fabricator.start()
        self.poll_progress()

        try:
            metadata = self._player.props.metadata
            if metadata:
                # meta_change emission must not block artwork discovery.
                try:
                    self.meta_change(metadata, self._player)
                except Exception as e:
                    logger.debug(f"meta_change emit failed: {e}")
                self._handle_artwork(metadata)
        except Exception as e:
            logger.warning(f"Failed to initialize metadata: {e}")

        # Playerctl loads player properties asynchronously. For a player that
        # was already playing before Modus started, the initial metadata read
        # above can be empty, and the `metadata` signal only fires on *change*
        # — so it would never re-fire and artwork would stay missing. Browser
        # players (YouTube in Firefox/Chromium) in particular populate
        # `mpris:artUrl` lazily, seconds after playback begins. Re-read metadata
        # repeatedly for a short window so the artwork is eventually picked up.
        GLib.timeout_add(500, self._refresh_initial_state, 0)

    def _refresh_initial_state(self, attempt: int = 0):
        if self._is_cleaning_up:
            return False
        try:
            metadata = self._player.props.metadata
        except Exception as e:
            logger.warning(
                f"[mpris] metadata = self._player.props.metadata failed: {e}"
            )
            return False
        if metadata:
            # Push full metadata only once to avoid UI churn on every retry.
            if attempt == 0:
                try:
                    self.meta_change(metadata, self._player)
                except Exception as e:
                    logger.debug(f"meta_change emit failed: {e}")
            self._handle_artwork(metadata)
            self.fabricating(metadata)
            # Stop as soon as artwork was found/queued.
            if self._current_artwork_hash:
                return False
        # Retry for ~10s (browser players can be very slow to expose artUrl).
        if attempt < 12:
            GLib.timeout_add(800, self._refresh_initial_state, attempt + 1)
        return False

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

    def _start_pos_fabricator(self):
        """Start position polling only if not already running."""
        if self._pos_polling:
            return
        self._pos_polling = True
        self.pos_fabricator.start()

    def _stop_pos_fabricator(self):
        """Stop position polling and clear the guard flag."""
        if not self._pos_polling:
            return
        self._pos_polling = False
        self.pos_fabricator.stop()

    def seek_position(self, pos: float):
        if self._is_cleaning_up:
            return
        self._stop_pos_fabricator()
        current = self.get_position() / 1_000_000
        try:
            self._player.set_position(int(pos * 1_000_000))
        except GLib.Error:
            try:
                offset = pos - current
                self._player.seek(int(offset * 1_000_000))
            except GLib.Error:
                name = self.player_name
                if name:
                    # No shell: pass args as a list so player_name can't inject.
                    exec_shell_command_async(
                        ["playerctl", "-p", name, "position", str(pos)]
                    )
        finally:
            if self.playback_status.lower() == "playing":
                self._start_pos_fabricator()

    def seek(self, offset: float):
        if self._is_cleaning_up:
            return
        self._stop_pos_fabricator()
        try:
            self._player.seek(int(offset * 1_000_000))
        except GLib.Error as e:
            logger.error(f"Failed to seek: {e}")
        finally:
            if self.playback_status.lower() == "playing":
                self._start_pos_fabricator()

    def poll_progress(self):
        if self._is_cleaning_up:
            return
        if self.playback_status.lower() == "playing":
            self._start_pos_fabricator()
        else:
            self._stop_pos_fabricator()

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
            # Browser players (YouTube in Firefox/Chromium) populate
            # `mpris:artUrl` lazily and don't reliably emit the `metadata`
            # signal. Since fabricating runs every 2s while playing, this also
            # polls the artwork so it shows up even for an already-playing tab.
            self._handle_artwork(metadata)
        self.track_position(pos, dur)

    def on_seeked(self, player, position):
        if self._is_cleaning_up:
            return
        if self.playback_status.lower() == "playing":
            self._start_pos_fabricator()

    def _notify_playback(self, status_str: str):
        """Emit play/pause once per actual state change (dedupes the
        Playerctl signal and the status Fabricator so listeners don't churn)."""
        if self._is_cleaning_up:
            return
        status_str = (status_str or "").lower()
        if status_str == self._last_emitted_status:
            return
        self._last_emitted_status = status_str
        if status_str == "playing":
            self.play()
        else:
            self.pause()

    def on_playback_status(self, player, status):
        """DBus signal handler - instant when it fires (e.g. Modus buttons)."""
        if self._is_cleaning_up:
            return
        self.poll_progress()
        self._notify_playback(self.playback_status)

    def _on_polled_status_change(self, new_status: str):
        """Fabricator-driven status change - fires reliably for browser players
        that don't emit playback-status signals."""
        if self._is_cleaning_up:
            return
        self.poll_progress()
        self._notify_playback(new_status)

    def on_metadata(self, player, metadata):
        if self._is_cleaning_up:
            return
        self.meta_change(metadata, player)
        self.fabricating(metadata)

    def _meta_str(self, metadata, key: str) -> str | None:
        try:
            value = metadata[key]
        except (KeyError, TypeError, GLib.Error) as e:
            logger.warning(f"[mpris] value = metadata[key] failed: {e}")
            return None
        if isinstance(value, (list, tuple)):
            return " ".join(str(v) for v in value) if value else None
        return str(value) if value else None

    def _find_cached_artwork(self, metadata) -> str | None:
        """Locate already-cached artwork for this track (native MediaArt cache)."""
        if not _MEDIAART_AVAILABLE:
            return None
        artist = self._meta_str(metadata, "xesam:artist")
        album = self._meta_str(metadata, "xesam:album")
        title = self._meta_str(metadata, "xesam:title")
        if not (artist or album or title):
            return None
        base = _mediaart_cache_path(artist, album, title)
        if not base:
            return None
        base = Path(base)
        if base.exists():
            return str(base)
        # MediaArt files usually carry an extension; look for any sibling.
        matches = list(base.parent.glob(base.stem + ".*"))
        return str(matches[0]) if matches else None

    def _existing_local_artwork(self, artwork_hash: str, metadata) -> str | None:
        cached = self._find_cached_artwork(metadata)
        if cached:
            return cached
        cache_dir = TEMP_DIR / "player-art"
        matches = list(cache_dir.glob(f"{artwork_hash}.*"))
        return str(matches[0]) if matches else None

    def _handle_artwork(self, metadata):
        if self._is_cleaning_up:
            return
        try:
            art_url = metadata["mpris:artUrl"]
        except (KeyError, TypeError) as e:
            logger.warning(f"[mpris] art_url = metadata['mpris:artUrl'] failed: {e}")
            return
        if not art_url:
            return
        artwork_hash = hashlib.md5(art_url.encode()).hexdigest()

        if artwork_hash == self._current_artwork_hash:
            return
        self._current_artwork_hash = artwork_hash

        parsed = urllib.parse.urlparse(art_url)
        if parsed.scheme == "file":
            local = urllib.parse.unquote(parsed.path)
            if Path(local).exists():
                self._set_artwork(local)
            return

        if parsed.scheme in ("http", "https"):
            existing = self._existing_local_artwork(artwork_hash, metadata)
            if existing and Path(existing).exists():
                self._set_artwork(existing)
                return
            threading.Thread(
                target=self._download_artwork,
                args=(art_url, artwork_hash, metadata),
                daemon=True,
            ).start()

    def _set_artwork(self, path: str):
        if self._is_cleaning_up:
            return
        self._current_artwork_path = path
        self.artwork_change(path)

    def _artwork_target_path(self, artwork_hash: str, metadata, suffix: str) -> Path:
        """Where to store a freshly downloaded cover: the standard MediaArt
        cache location when available, otherwise our own fallback cache."""
        ma_base = self._find_cached_artwork(metadata)
        if ma_base:
            base = Path(ma_base)
            return base.parent / (base.stem + suffix)
        cache_dir = TEMP_DIR / "player-art"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{artwork_hash}{suffix}"

    def _download_artwork(self, art_url: str, artwork_hash: str, metadata):
        if self._is_cleaning_up:
            return
        try:
            with urllib.request.urlopen(art_url, timeout=5) as response:
                data = response.read()
                suffix = (
                    mimetypes.guess_extension(response.info().get_content_type())
                    or ".png"
                )
                target = self._artwork_target_path(artwork_hash, metadata, suffix)
                tmp = target.with_suffix(target.suffix + ".tmp")
                tmp.write_bytes(data)
                tmp.replace(target)

            if not self._is_cleaning_up:
                GLib.idle_add(self._set_artwork, str(target))

        except Exception as e:
            logger.error(f"Failed to download artwork: {e}")

    def cleanup(self):
        if self._is_cleaning_up:
            return
        self._is_cleaning_up = True

        try:
            if hasattr(self, "pos_fabricator"):
                self._stop_pos_fabricator()
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

    def _on_name_appeared(self, sender, name, _manager):
        self._create_player(name)

    def _on_player_vanished(self, sender, player, _manager):
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
