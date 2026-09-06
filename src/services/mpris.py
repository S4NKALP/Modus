import hashlib
import mimetypes
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import gi
from fabric.core.service import Property, Service, Signal
from fabric.utils import Gio, GLib, logger

from shared.data import CACHE_DIR

# libmediaart: native Linux album art cache used by GNOME/GTK apps (Rhythmbox,
# Lollypop, etc.). We follow its cache paths so artwork is shared across apps
# instead of duplicated in our own cache dir.
try:
    gi.require_version("MediaArt", "2.0")
    from gi.repository import MediaArt

    _MEDIAART_AVAILABLE = True
except (ValueError, ImportError):
    MediaArt = None
    _MEDIAART_AVAILABLE = False

TEMP_DIR = Path(CACHE_DIR)

MPRIS_PLAYER_PREFIX = "org.mpris.MediaPlayer2."
PLAYERCTLD_SERVICE = "org.mpris.MediaPlayer2.playerctld"
MPRIS_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
MPRIS_PLAYER_PATH = "/org/mpris/MediaPlayer2"

# Bounded timeout (ms) for synchronous player reads so a hung player cannot
# block the main loop forever.
_MPRIS_CALL_TIMEOUT = 5000

_MPRIS_PLAYER_IFACE_INFO = Gio.DBusNodeInfo.new_for_xml(
    """<node>
    <interface name="org.mpris.MediaPlayer2.Player">
        <method name="Next"/>
        <method name="Previous"/>
        <method name="PlayPause"/>
        <method name="SetPosition">
            <parameter type="i" name="Position" direction="in"/>
        </method>
        <method name="Seek">
            <parameter type="x" name="Offset" direction="in"/>
        </method>
        <property type="s" name="PlaybackStatus" access="read"/>
        <property type="a{sv}" name="Metadata" access="read"/>
        <property type="d" name="Volume" access="readwrite"/>
        <property type="b" name="CanSeek" access="read"/>
    </interface>
</node>"""
).lookup_interface("org.mpris.MediaPlayer2.Player")


def _variant_to_str(variant) -> str | None:
    if variant is None:
        return None
    if isinstance(variant, str):
        return variant
    vtype = variant.get_type_string()
    if vtype == "s":
        return variant.get_string()
    if vtype == "ay":
        raw = variant.get_fixed_array()
        return raw.tobytes().decode("utf-8", errors="replace") if len(raw) > 0 else None
    return None


def _is_valid_art_url(url: str) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in ("http", "https", "file")


def _mediaart_cache_path(artist: str | None, album: str | None, title: str | None):
    if not _MEDIAART_AVAILABLE:
        return None
    try:
        result = MediaArt.get_path(
            artist or None, album or None, title or None, MediaArt.Type.ALBUM
        )
    except Exception as e:
        logger.debug(f"MediaArt.get_path failed: {e}")
        return None
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
    def meta_change(self, metadata: object, player: object) -> None: ...

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
        v = self._proxy.get_cached_property("CanSeek")
        return v.get_boolean() if v else False

    @Property(str, "readable", default_value="")
    def player_name(self) -> str:
        return self._name

    @Property(object, "readable")
    def metadata(self) -> dict:
        return self._get_metadata() or {}

    @Property(str, "readable", default_value="")
    def title(self) -> str:
        m = self._get_metadata()
        v = m.get("xesam:title") if m else None
        return _variant_to_str(v) or ""

    @Property(object, "readable")
    def artist(self) -> list:
        m = self._get_metadata()
        v = m.get("xesam:artist") if m else None
        if v is None:
            return []
        if isinstance(v, list):
            return v or []
        if isinstance(v, str):
            return [v]
        if v.get_type_string() == "as":
            return list(v.unpack()) or []
        s = _variant_to_str(v)
        return [s] if s else []

    @Property(str, "readable", default_value="")
    def album(self) -> str:
        m = self._get_metadata()
        v = m.get("xesam:album") if m else None
        return _variant_to_str(v) or ""

    @Property(str, "readable", default_value="Stopped")
    def playback_status(self) -> str:
        v = self._proxy.get_cached_property("PlaybackStatus")
        if v is None:
            return "Stopped"
        return v.get_string() if isinstance(v, GLib.Variant) else str(v)

    @Property(int, "readable", default_value=0)
    def length(self) -> int:
        m = self._get_metadata()
        v = m.get("mpris:length") if m else None
        if v is None:
            return 0
        if isinstance(v, int):
            return v
        if isinstance(v, GLib.Variant):
            return v.get_uint64() if v.get_type_string() == "t" else int(v)
        return int(v)

    @Property(int, "readable", default_value=0)
    def position(self) -> int:
        if self._is_cleaning_up:
            return 0
        try:
            result = self._proxy.call_sync(
                "org.freedesktop.DBus.Properties.Get",
                GLib.Variant("(ss)", (MPRIS_PLAYER_IFACE, "Position")),
                Gio.DBusCallFlags.NONE,
                _MPRIS_CALL_TIMEOUT,
                None,
            )
            return result.get_child_value(0).unpack()
        except GLib.Error as e:
            logger.warning(f"[mpris] position failed: {e}")
            return 0

    def play_pause(self, *_):
        self._call_async("PlayPause")

    def next(self, *_):
        self._call_async("Next")

    def previous(self, *_):
        self._call_async("Previous")

    def _call_async(self, method: str, args=None):
        """Fire-and-forget player control call; never blocks the main loop."""

        def _on_reply(proxy, res, _user_data):
            try:
                proxy.call_finish(res)
            except GLib.Error as e:
                logger.warning(f"[mpris] {method} failed: {e}")

        try:
            self._proxy.call(method, args, Gio.DBusCallFlags.NONE, -1, None, _on_reply)
        except GLib.Error as e:
            logger.warning(f"[mpris] {method} call failed: {e}")

    def __init__(self, name: str, proxy: Gio.DBusProxy, **kwargs):
        super().__init__(**kwargs)
        self._name = name
        self._proxy = proxy
        self._metadata_cache: dict | None = None
        self._current_artwork_hash = ""
        self._current_artwork_path = ""
        self._is_cleaning_up = False
        self._artwork_generation = 0
        self._signal_ids = []
        self._subscription_ids: list[int] = []
        self._last_emitted_status = ""
        self._failed_covers: set[str] = set()
        self._download_threads: dict[str, threading.Thread] = {}

        self._signal_ids.append(
            self._proxy.connect("g-properties-changed", self._on_properties_changed)
        )

        self._subscribe_seeked()

        if self.playback_status.lower() == "playing":
            self.fabricating()

        metadata = self._get_metadata()
        if metadata:
            self.meta_change(metadata, self)
            self._handle_artwork(metadata)

        # Browser players (YouTube in Firefox/Chromium) populate
        # `mpris:artUrl` lazily, seconds after playback begins. Re-read
        # metadata repeatedly for a short window so artwork is picked up.
        GLib.timeout_add(500, self._refresh_initial_state, 0)

    def _refresh_initial_state(self, attempt: int = 0):
        if self._is_cleaning_up:
            return False
        metadata = self._get_metadata()
        if metadata:
            if attempt == 0:
                self.meta_change(metadata, self)
            self._handle_artwork(metadata)
            self.fabricating(metadata)
            if self._current_artwork_hash:
                return False
        if attempt < 12:
            GLib.timeout_add(800, self._refresh_initial_state, attempt + 1)
        return False

    def _subscribe_seeked(self):
        conn = self._proxy.get_connection()
        if conn:
            self._subscription_ids.append(
                conn.signal_subscribe(
                    self._proxy.get_name(),
                    MPRIS_PLAYER_IFACE,
                    "Seeked",
                    MPRIS_PLAYER_PATH,
                    None,
                    Gio.DBusSignalFlags.NONE,
                    self._on_seeked,
                )
            )

    def _on_seeked(
        self,
        _connection,
        _sender_name,
        _object_path,
        _interface_name,
        _signal_name,
        params: GLib.Variant,
    ):
        if self._is_cleaning_up:
            return
        try:
            pos = params.unpack()[0] / 1_000_000
        except Exception as e:
            logger.warning(f"[mpris] Seeked unpack failed: {e}")
            return
        m = self._get_metadata()
        dur = 0
        if m is not None:
            v = m.get("mpris:length")
            if v is not None:
                dur = (
                    v.get_uint64() / 1_000_000
                    if isinstance(v, GLib.Variant) and v.get_type_string() == "t"
                    else int(v) / 1_000_000
                )
        self.track_position(pos, dur)

    def get_artwork(self) -> str:
        return self._current_artwork_path

    def get_position(self) -> float:
        if self._is_cleaning_up:
            return 0
        try:
            result = self._proxy.call_sync(
                "org.freedesktop.DBus.Properties.Get",
                GLib.Variant("(ss)", (MPRIS_PLAYER_IFACE, "Position")),
                Gio.DBusCallFlags.NONE,
                _MPRIS_CALL_TIMEOUT,
                None,
            )
            return result.get_child_value(0).unpack() / 1_000_000
        except GLib.Error as e:
            logger.warning(f"Could not get position: {e}")
            return 0

    def seek_position(self, pos: float):
        if self._is_cleaning_up:
            return
        try:
            self._proxy.call_sync(
                "SetPosition",
                GLib.Variant("(i)", (int(pos * 1_000_000),)),
                Gio.DBusCallFlags.NONE,
                _MPRIS_CALL_TIMEOUT,
                None,
            )
        except GLib.Error:
            # SetPosition unsupported: fall back to a relative Seek.
            current = self.get_position() / 1_000_000
            offset = pos - current
            self._call_async("Seek", GLib.Variant("(x)", (int(offset * 1_000_000),)))
        finally:
            self.poll_progress()

    def seek(self, offset: float):
        if self._is_cleaning_up:
            return
        try:
            self._call_async("Seek", GLib.Variant("(x)", (int(offset * 1_000_000),)))
        except GLib.Error as e:
            logger.error(f"Failed to seek: {e}")
        finally:
            self.poll_progress()

    def poll_progress(self):
        if self._is_cleaning_up:
            return
        if self.playback_status.lower() == "playing":
            self.fabricating()

    def fabricating(self, metadata=None):
        if self._is_cleaning_up:
            return
        try:
            result = self._proxy.call_sync(
                "org.freedesktop.DBus.Properties.Get",
                GLib.Variant("(ss)", (MPRIS_PLAYER_IFACE, "Position")),
                Gio.DBusCallFlags.NONE,
                _MPRIS_CALL_TIMEOUT,
                None,
            )
            pos = result.get_child_value(0).unpack() / 1_000_000
        except GLib.Error as e:
            logger.warning(f"Failed to get position: {e}")
            return
        dur = 0
        if metadata is None:
            metadata = self._get_metadata()
        if metadata is not None:
            v = metadata.get("mpris:length")
            if v is not None:
                dur = (
                    v.get_uint64() / 1_000_000
                    if isinstance(v, GLib.Variant) and v.get_type_string() == "t"
                    else int(v) / 1_000_000
                )
            self._handle_artwork(metadata)
        self.track_position(pos, dur)

    def _on_properties_changed(self, _proxy, changed_properties, _changed_invalidated):
        if self._is_cleaning_up:
            return
        props = changed_properties.unpack()

        if "PlaybackStatus" in props:
            self.poll_progress()
            self._notify_playback(props["PlaybackStatus"])

        if "Metadata" in props:
            metadata = props["Metadata"]
            if isinstance(metadata, dict):
                self._metadata_cache = metadata
                self.meta_change(metadata, self)
                self.fabricating(metadata)
            elif isinstance(metadata, GLib.Variant):
                unpacked = metadata.unpack()
                if isinstance(unpacked, dict):
                    self._metadata_cache = unpacked
                    self.meta_change(unpacked, self)
                    self.fabricating(unpacked)

    def _notify_playback(self, status_str: str):
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

    def _get_metadata(self) -> dict | None:
        if self._metadata_cache is not None:
            return self._metadata_cache
        v = self._proxy.get_cached_property("Metadata")
        if v is None:
            return None
        unpacked = v.unpack() if isinstance(v, GLib.Variant) else v
        self._metadata_cache = unpacked if isinstance(unpacked, dict) else None
        return self._metadata_cache

    def _meta_str(self, metadata, key: str) -> str | None:
        value = metadata.get(key)
        if value is None:
            return None
        if isinstance(value, GLib.Variant):
            return _variant_to_str(value)
        if isinstance(value, (list, tuple)):
            return " ".join(str(v) for v in value) if value else None
        return str(value) if value else None

    def _find_cached_artwork(self, metadata) -> str | None:
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
        art_url_raw = metadata.get("mpris:artUrl")
        if art_url_raw is None:
            return
        art_url = (
            art_url_raw.get_string()
            if isinstance(art_url_raw, GLib.Variant)
            else str(art_url_raw)
        )
        if not _is_valid_art_url(art_url):
            return
        artwork_hash = hashlib.md5(art_url.encode()).hexdigest()

        if artwork_hash == self._current_artwork_hash:
            return
        if artwork_hash in self._failed_covers:
            return
        self._current_artwork_hash = artwork_hash

        for h in list(self._download_threads):
            if h != artwork_hash:
                del self._download_threads[h]

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
            gen = self._artwork_generation
            t = threading.Thread(
                target=self._download_artwork,
                args=(art_url, artwork_hash, metadata, gen),
                daemon=True,
            )
            self._download_threads[artwork_hash] = t
            t.start()

    def _set_artwork(self, path: str):
        if self._is_cleaning_up:
            return
        self._current_artwork_path = path
        self.artwork_change(path)

    def _artwork_target_path(self, artwork_hash: str, metadata, suffix: str) -> Path:
        ma_base = self._find_cached_artwork(metadata)
        if ma_base:
            base = Path(ma_base)
            return base.parent / (base.stem + suffix)
        cache_dir = TEMP_DIR / "player-art"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{artwork_hash}{suffix}"

    def _download_artwork(self, art_url: str, artwork_hash: str, metadata, gen: int):
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

            if not self._is_cleaning_up and gen == self._artwork_generation:
                GLib.idle_add(self._set_artwork, str(target))

        except Exception as e:
            logger.error(f"Failed to download artwork: {e}")
            if not self._is_cleaning_up:
                self._failed_covers.add(artwork_hash)
        finally:
            self._download_threads.pop(artwork_hash, None)

    def cleanup(self):
        if self._is_cleaning_up:
            return
        self._is_cleaning_up = True
        self._artwork_generation += 1

        for sid in self._signal_ids:
            try:
                self._proxy.disconnect(sid)
            except Exception as e:
                logger.warning(f"Error disconnecting signal: {e}")
        self._signal_ids.clear()

        conn = self._proxy.get_connection()
        for sid in self._subscription_ids:
            try:
                if conn:
                    conn.signal_unsubscribe(sid)
            except Exception as e:
                logger.warning(f"Error unsubscribing signal: {e}")
        self._subscription_ids.clear()

        self._current_artwork_path = ""
        self._metadata_cache = None
        self._failed_covers.clear()
        self._download_threads.clear()


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
        self._connection: Gio.DBusConnection | None = None
        self._services: dict[str, PlayerService] = {}
        self._owner_watch_id = 0

        try:
            self._connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as e:
            logger.error(f"Failed to connect to session bus: {e}")
            return

        self._owner_watch_id = self._connection.signal_subscribe(
            None,
            "org.freedesktop.DBus",
            "NameOwnerChanged",
            "/org/freedesktop/DBus",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_name_owner_changed,
        )
        self._init_existing_players()

    def _init_existing_players(self):
        if not self._connection:
            return
        try:
            result = self._connection.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "ListNames",
                None,
                GLib.VariantType("(as)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            names = result.get_child_value(0).unpack()
            for name in names:
                if name.startswith(MPRIS_PLAYER_PREFIX) and name != PLAYERCTLD_SERVICE:
                    self._create_player(name)
        except GLib.Error as e:
            logger.error(f"Failed to list bus names: {e}")

    def _on_name_owner_changed(
        self, _connection, _sender, _object_path, _interface, _signal_name, parameters
    ):
        name, old_owner, new_owner = parameters.unpack()
        if not name.startswith(MPRIS_PLAYER_PREFIX) or name == PLAYERCTLD_SERVICE:
            return
        if new_owner and not old_owner:
            self._create_player(name)
        elif old_owner and not new_owner:
            self._on_player_vanished(name)

    def _create_player(self, name: str):
        if name in self._services:
            return
        try:
            proxy = Gio.DBusProxy.new_sync(
                self._connection,
                Gio.DBusProxyFlags.NONE,
                _MPRIS_PLAYER_IFACE_INFO,
                name,
                MPRIS_PLAYER_PATH,
                MPRIS_PLAYER_IFACE,
                None,
            )
            service = PlayerService(name, proxy)
            self._services[name] = service
            self.new_player(name, service)
        except GLib.Error as e:
            logger.error(f"Failed to create player {name}: {e}")

    def _on_player_vanished(self, name: str):
        if name in self._services:
            self._services[name].cleanup()
            del self._services[name]
            self.player_vanish(name)

    def get_player_service(self, name: str) -> PlayerService | None:
        return self._services.get(name)

    def get_all_services(self) -> dict[str, PlayerService]:
        return self._services.copy()
