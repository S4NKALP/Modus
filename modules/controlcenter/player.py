import urllib.parse
from urllib.parse import urlparse

from gi.repository import GLib
from loguru import logger

import config.data as data
from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.svg import Svg
from services.mpris import PlayerManager, PlayerService


class Player(Box):
    def __init__(self, player, **kwargs):
        super().__init__(style_classes="player-box", **kwargs)

        self._player = PlayerService(player=player)

        self.duration = 0.0

        self._player.connect("pause", self.on_pause)
        self._player.connect("play", self.on_play)
        self._player.connect("meta-change", self.on_metadata)
        self._player.connect("shuffle-toggle", self.on_shuffle)
        self._player.connect("track-position", self.on_update_track_position)

        player.connect("metadata", self.on_direct_metadata_change)

        self.player_name = Image(
            name=player.props.player_name,
            style_classes="player-icon",
            icon_name=self._get_player_icon_name(player.props.player_name),
            size=20,
        )

        self.song = Label(
            name="song",
            label="song",
            justification="left",
            h_align="start",
            ellipsization="end",
            max_chars_width=15,
        )
        self.artist = Label(
            name="artist",
            label="artist",
            justification="left",
            h_align="start",
        )
        self.music = Box(
            name="music",
            h_expand=True,
            v_expand=True,
            children=[self.song],
        )

        self.play_pause_button = Button(
            name="play-pause-button",
            child=Svg(
                svg_file=get_relative_path("../../config/assets/icons/media/play.svg"),
                size=20,
            ),
            tooltip_text="Play/Pause",
            on_clicked=lambda b, *_: self.handle_play_pause(player),
        )

        self.shuffle_button = Button(
            name="shuffle-button",
            child=Svg(
                svg_file=get_relative_path(
                    "../../config/assets/icons/media/shuffle.svg"
                ),
                size=20,
            ),
            on_clicked=lambda b, *_: self.handle_shuffle(b, player),
        )

        self.album_cover = Box(style_classes="album-image")
        self.album_cover.set_style(
            f"background-image:url('{data.HOME_DIR}/.current.wall')"
        )

        self.children = [
            self.album_cover,
            Box(
                name="source",
                v_align="end",
                children=self.player_name,
            ),
            Box(
                orientation="v",
                v_expand=True,
                h_expand=True,
                style="padding-left:10px;",
                children=[
                    CenterBox(
                        name="details",
                        center_children=self.music,
                    ),
                    Box(
                        name="controls",
                        spacing=5,
                        h_expand=True,
                        children=[
                            CenterBox(
                                h_expand=True,
                                v_expand=True,
                                center_children=[
                                    Button(
                                        name="prev-button",
                                        child=Svg(
                                            svg_file=get_relative_path(
                                                "../../config/assets/icons/media/previous.svg"
                                            ),
                                            size=20,
                                        ),
                                        on_clicked=lambda b, *_: self.handle_prev(
                                            player
                                        ),
                                    ),
                                    self.play_pause_button,
                                    Button(
                                        name="next-button",
                                        child=Svg(
                                            svg_file=get_relative_path(
                                                "../../config/assets/icons/media/next.svg"
                                            ),
                                            size=20,
                                        ),
                                        on_clicked=lambda b, *_: self.handle_next(
                                            player
                                        ),
                                    ),
                                    self.shuffle_button,
                                ],
                            )
                        ],
                    ),
                ],
            ),
        ]

        self.on_metadata(self._player, metadata=player.props.metadata, player=player)

    def _get_player_icon_name(self, player_name):
        symbolic_players = [
            "spotify",
            "firefox",
            "chromium",
            "chrome",
            "brave",
            "vivaldi",
        ]

        if player_name.lower() in symbolic_players:
            icon_name = f"{player_name.lower()}-symbolic"
            return icon_name
        else:
            return player_name.lower()

    def _update_play_pause_icon(self, is_playing):
        if is_playing:
            self.play_pause_button.get_child().set_from_file(
                get_relative_path("../../config/assets/icons/media/pause.svg")
            )
        else:
            self.play_pause_button.get_child().set_from_file(
                get_relative_path("../../config/assets/icons/media/play.svg")
            )

    def _update_shuffle_icon(self, is_shuffled):
        if is_shuffled:
            self.shuffle_button.get_child().set_from_file(
                get_relative_path("../../config/assets/icons/media/shuffle.svg")
            )
            self.shuffle_button.get_child().set_name("shuffle")
        else:
            self.shuffle_button.get_child().set_from_file(
                get_relative_path("../../config/assets/icons/media/no-shuffle.svg")
            )
            self.shuffle_button.get_child().set_name("disable-shuffle")

    def on_direct_metadata_change(self, player, metadata):
        try:
            logger.debug(f"Direct metadata change for {player.props.player_name}")
            self.on_metadata(self._player, metadata, player)
        except Exception as e:
            logger.warning(f"Failed to handle direct metadata change: {e}")

    def on_update_track_position(self, sender, pos, dur):
        if dur == 0:
            return
        self.duration = dur

    def on_seek(self, sender, ratio):
        pos = ratio * self.duration  # duration in seconds
        print(f"Seeking to {pos:.2f}s")
        self._player.set_position(int(pos))

    def skip_forward(self, seconds=10):
        self._player._player.seek(seconds * 1000000)

    def skip_backward(self, seconds=10):
        self._player._player.seek(-1 * seconds * 1000000)

    def _is_shuffle_supported(self, player):
        try:
            _ = player.props.shuffle
            return True
        except Exception:
            return False

    def on_metadata(self, sender, metadata, player):
        keys = metadata.keys()
        if "xesam:artist" in keys and "xesam:title" in keys:
            song_title = metadata["xesam:title"]
            self.song.set_label(song_title)

            artist_list = metadata["xesam:artist"]
            artist_name = artist_list[0] if artist_list else "Unknown Artist"
            self.artist.set_label(artist_name)

            self._handle_thumbnail(metadata, player)

        if (
            player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        ):
            self.on_play(self._player)

        if self._is_shuffle_supported(player):
            if player.props.shuffle == True:
                self._update_shuffle_icon(True)
            else:
                self._update_shuffle_icon(False)
        else:
            self.shuffle_button.set_visible(False)

    def _handle_thumbnail(self, metadata, player):
        keys = metadata.keys()
        player_name = player.props.player_name

        browser_players = ["firefox", "chromium", "vivaldi", "brave"]
        is_browser = player_name in browser_players

        thumbnail_url = None

        if "mpris:artUrl" in keys:
            art_url = metadata["mpris:artUrl"]
            if art_url and art_url.strip():
                if art_url.startswith("data:image/"):
                    thumbnail_url = art_url
                elif art_url.startswith("http"):
                    thumbnail_url = art_url
                elif art_url.startswith("file://"):
                    thumbnail_url = art_url

        if is_browser and not thumbnail_url and "xesam:url" in keys:
            webpage_url = metadata["xesam:url"]
            if webpage_url and webpage_url.startswith("http"):
                # Try to extract actual media thumbnail from the webpage
                thumbnail_url = self._extract_media_thumbnail(
                    webpage_url, metadata, player_name
                )

        if is_browser and not thumbnail_url:
            thumbnail_url = self._extract_from_browser_metadata(metadata, player_name)

        if thumbnail_url:
            logger.debug(f"Setting media thumbnail for {player_name}: {thumbnail_url}")
            self.album_cover.set_style(f"background-image:url('{thumbnail_url}')")
        else:
            logger.debug(
                f"No media thumbnail found for {player_name}, using default wallpaper"
            )
            self.album_cover.set_style(
                f"background-image:url('{data.HOME_DIR}/.current.wall')"
            )

    def _extract_media_thumbnail(self, webpage_url, metadata, player_name):
        try:
            parsed_url = urlparse(webpage_url)
            domain = parsed_url.netloc
            path = parsed_url.path

            logger.debug(
                f"Extracting media thumbnail for {player_name} from: {webpage_url}"
            )

            if "youtube.com" in domain or "youtu.be" in domain:
                video_id = self._extract_youtube_video_id(webpage_url)
                if video_id:
                    logger.debug(f"Extracted YouTube video ID: {video_id}")
                    return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

            elif "vimeo.com" in domain:
                video_id = self._extract_vimeo_video_id(webpage_url)
                if video_id:
                    logger.debug(f"Extracted Vimeo video ID: {video_id}")
                    return f"https://vumbnail.com/{video_id}.jpg"

            elif "twitch.tv" in domain:
                channel_name = self._extract_twitch_channel(webpage_url)
                if channel_name:
                    logger.debug(f"Extracted Twitch channel: {channel_name}")
                    return f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{channel_name}-1280x720.jpg"

            return self._extract_from_metadata_fields(metadata, player_name)

        except Exception as e:
            logger.warning(f"Failed to extract media thumbnail: {e}")
            return None

    def _extract_youtube_video_id(self, url):
        try:
            if "youtube.com/watch" in url:
                query = urlparse(url).query
                params = dict(urllib.parse.parse_qsl(query))
                return params.get("v")
            elif "youtu.be/" in url:
                path = urlparse(url).path
                return path.strip("/")
            elif "youtube.com/embed/" in url:
                path = urlparse(url).path
                return path.split("/")[-1]
        except Exception as e:
            logger.warning(f"Failed to extract YouTube video ID: {e}")
            return None

    def _extract_vimeo_video_id(self, url):
        try:
            path = urlparse(url).path
            video_id = path.strip("/")
            if video_id.isdigit():
                return video_id
        except Exception as e:
            logger.warning(f"Failed to extract Vimeo video ID: {e}")
            return None

    def _extract_twitch_channel(self, url):
        try:
            path = urlparse(url).path
            channel = path.strip("/")
            if channel and not channel.startswith("videos"):
                return channel
        except Exception as e:
            logger.warning(f"Failed to extract Twitch channel: {e}")
            return None

    def _extract_from_browser_metadata(self, metadata, player_name):
        try:
            keys = metadata.keys()

            thumbnail_fields = [
                "mpris:artUrl",
                "xesam:artUrl",
                "xesam:albumArt",
                "xesam:thumbnail",
                "xesam:image",
                "xesam:cover",
            ]

            for field in thumbnail_fields:
                if field in keys:
                    value = metadata[field]
                    if value and isinstance(value, str) and value.strip():
                        if value.startswith(("http://", "https://", "data:image/")):
                            logger.debug(f"Found thumbnail in {field}: {value}")
                            return value

            return None

        except Exception as e:
            logger.warning(f"Failed to extract from browser metadata: {e}")
            return None

    def _extract_from_metadata_fields(self, metadata, player_name):
        try:
            keys = metadata.keys()

            thumbnail_fields = [
                "mpris:artUrl",
                "xesam:artUrl",
                "xesam:albumArt",
                "xesam:thumbnail",
                "xesam:image",
                "xesam:cover",
                "xesam:albumArtUrl",
            ]

            for field in thumbnail_fields:
                if field in keys:
                    value = metadata[field]
                    if value and isinstance(value, str) and value.strip():
                        if value.startswith(
                            ("http://", "https://", "data:image/", "file://")
                        ):
                            logger.debug(f"Found thumbnail in {field}: {value}")
                            return value

            return None

        except Exception as e:
            logger.warning(f"Failed to extract from metadata fields: {e}")
            return None

    def on_pause(self, sender):
        self._update_play_pause_icon(False)

    def on_play(self, sender):
        self._update_play_pause_icon(True)

    def on_shuffle(self, sender, player, status):
        print("callback status", status)
        self._update_shuffle_icon(status)

    def handle_next(self, player):
        self._player._player.next()
        self._refresh_metadata_after_delay(player)

        if player.props.player_name in ["firefox", "chromium", "vivaldi", "brave"]:
            self._refresh_metadata_immediate(player)

    def handle_prev(self, player):
        self._player._player.previous()
        self._refresh_metadata_after_delay(player)

        if player.props.player_name in ["firefox", "chromium", "vivaldi", "brave"]:
            self._refresh_metadata_immediate(player)

    def _refresh_metadata_immediate(self, player):
        try:
            current_metadata = player.props.metadata
            if current_metadata:
                logger.debug(
                    f"Immediate metadata refresh for {player.props.player_name}"
                )
                self.on_metadata(self._player, current_metadata, player)
        except Exception as e:
            logger.warning(f"Failed immediate metadata refresh: {e}")

    def _refresh_metadata_after_delay(self, player):
        def refresh_metadata():
            try:
                current_metadata = player.props.metadata
                if current_metadata:
                    logger.debug(f"Refreshing metadata for {player.props.player_name}")
                    self.on_metadata(self._player, current_metadata, player)
                else:
                    logger.debug(
                        f"No metadata available for {
                            player.props.player_name
                        }, retrying..."
                    )
                    GLib.timeout_add(1000, refresh_metadata)
            except Exception as e:
                logger.warning(f"Failed to refresh metadata: {e}")

        GLib.timeout_add(500, refresh_metadata)

    def handle_play_pause(self, player):
        is_playing = (
            self._player._player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        )

        def _set_play_ui():
            self._update_play_pause_icon(True)

        def _set_pause_ui():
            self._update_play_pause_icon(False)

        if is_playing:
            _set_pause_ui()
        else:
            _set_play_ui()

        try:
            self._player._player.play_pause()
        except Exception as e:
            if is_playing:
                _set_pause_ui()
            else:
                _set_play_ui()
            logger.warning("Failed to toggle playback:", e)

    def handle_shuffle(self, shuffle_button, player):
        print("shuffle", player.props.shuffle)

        if not self._is_shuffle_supported(player):
            print(f"Shuffle not supported for {player.props.player_name}")
            return

        try:
            if player.props.shuffle == False:
                player.set_shuffle(True)
                print("setting to true", player.props.player_name)
            else:
                player.set_shuffle(False)
        except Exception as e:
            print(f"Failed to toggle shuffle for {player.props.player_name}: {e}")
            pass
        shuffle_button.get_child().set_style("color: var(--outline)")


class Placheholder(Box):
    def __init__(self, **kwargs):
        super().__init__(style_classes="player-box", **kwargs)

        self.album_cover = Box(style_classes="album-image")
        self.album_cover.set_style(
            f"background-image:url('{data.HOME_DIR}/.current.wall')"
        )
        self.player_name = Image(
            name="player-icon",
            icon_name="media-player-48",
            size=20,
        )

        self.children = [
            self.album_cover,
            Box(
                name="source",
                v_align="end",
                children=self.player_name,
            ),
            Box(
                orientation="v",
                v_expand=True,
                h_expand=True,
                style="padding-left:10px;",
                v_align="center",
                children=[
                    CenterBox(
                        name="details",
                        center_children=Label(
                            label="Nothing Playing", style="color:black;"
                        ),
                    )
                ],
            ),
        ]


class PlayerContainer(Box):
    def __init__(self, **kwargs):
        super().__init__(name="player-container", **kwargs)

        self.manager = PlayerManager()
        self.manager.connect("new-player", self.new_player)
        self.manager.connect("player-vanish", self.on_player_vanish)
        self.placeholder = Placheholder()
        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=100,
            children=[self.placeholder],
        )

        self.player_stack = Stack(
            name="player-stack",
            transition_type="crossfade",
            transition_duration=100,
            children=[],
        )

        self.player_switch_container = CenterBox(
            name="player-switch-container",
            orientation="v",
            center_children=[],
        )
        self.tile_icon = Image(
            name="disc",
            style="font-size:30px; margin:0px; padding:0px;",
            icon_name="disc-symbolic",
            size=30,
        )

        self.tile_view = CenterBox(
            v_expand=False,
            center_children=self.tile_icon,
        )
        self.event_box = EventBox(
            events=["scroll"],
            child=Box(children=[self.stack, self.player_switch_container]),
        )
        self.children = self.event_box
        self.players = []
        self.manager.init_all_players()
        self.event_box.connect("scroll-event", self.on_scroll)
        self.stack.connect("notify::visible-child", self.on_visible_child_changed)

    def new_player(self, manager, player):
        new_player = Player(player=player)
        new_player.set_name(player.props.player_name)
        self.players.append(new_player)
        self.stack.add_named(new_player, player.props.player_name)
        if len(self.players) == 1:
            self.stack.remove(self.placeholder)

        self.player_switch_container.add_center(
            Button(
                name=player.props.player_name,
                style_classes="player-button",
                on_clicked=lambda b: self.switch_player(player.props.player_name, b),
            )
        )
        self.update_player_list()

    def switch_player(self, player_name, button):
        self.stack.set_visible_child_name(player_name)

        for btn in self.player_switch_container.center_children:
            btn.remove_style_class("active")
        button.add_style_class("active")

    def on_player_vanish(self, manager, player):
        for player_instance in self.players:
            if player_instance.get_name() == player.props.player_name:
                self.stack.remove(player_instance)
                self.players.remove(player_instance)
                for btn in self.player_switch_container.center_children:
                    if btn.get_name() == player_instance.get_name():
                        self.player_switch_container.remove_center(btn)
                self.update_player_list()
                break

        if len(self.players) == 0:
            self.stack.add_named(self.placeholder, "placeholder")

    def update_player_list(self):
        curr = self.stack.get_visible_child()
        if curr is None:
            return
        for btn in self.player_switch_container.center_children:
            print(btn.get_name())
            if btn.get_name() == curr.get_name():
                btn.add_style_class("active")
            else:
                btn.remove_style_class("active")

    def on_scroll(self, widget, event):
        match event.direction:
            case 0:
                self.switch_relative_player(forward=False)
            case 1:
                self.switch_relative_player(forward=True)

    def switch_relative_player(self, forward=True):
        if not self.players:
            return

        current_player = self.stack.get_visible_child()
        if current_player is None:
            return

        current_index = self.players.index(current_player)

        next_index = (current_index + (1 if forward else -1)) % len(self.players)
        next_player = self.players[next_index]

        for btn in self.player_switch_container.center_children:
            if btn.get_name() == next_player.get_name():
                self.switch_player(next_player.get_name(), btn)
                break

    def on_visible_child_changed(self, *args):
        curr_child = self.stack.get_visible_child()
        if curr_child is None:
            return
        curr_player = curr_child.get_name()
        self.tile_icon.set_name(curr_player)
        self.tile_icon.set_icon_name(self._get_player_icon_name(curr_player))

    def get_view(self):
        return self.tile_view
