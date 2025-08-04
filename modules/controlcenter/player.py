import re

from gi.repository import Playerctl, GLib
from fabric.core.service import Signal
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.svg import Svg
from loguru import logger

import config.data as data
from fabric.utils import get_relative_path
from services.mpris import PlayerManager, PlayerService


class Player(Box):
    def __init__(self, player, **kwargs):
        super().__init__(style_classes="player-box", **kwargs)

        self._player = PlayerService(player=player)
        self._current_thumbnail = None  # Cache for current thumbnail
        self._update_queue = []
        self._is_updating = False
        self._update_timeout_id = None

        self.duration = 0.0

        self._player.connect("meta-change", self.on_metadata)
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
            max_chars_width=22,
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
        self._player.set_position(int(pos))

    def on_metadata(self, sender, metadata, player):
        def _update_metadata():
            keys = metadata.keys()
            if "xesam:artist" in keys and "xesam:title" in keys:
                song_title = metadata["xesam:title"]
                self.song.set_label(song_title)

                artist_list = metadata["xesam:artist"]
                artist_name = artist_list[0] if artist_list else "Unknown Artist"
                self.artist.set_label(artist_name)

                self._handle_thumbnail(metadata, player)

            # Update play/pause state
            if (
                player.props.playback_status.value_name
                == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
            ):
                self._update_play_pause_icon(True)
            else:
                self._update_play_pause_icon(False)

            # Update shuffle state
            if self._is_shuffle_supported(player):
                if player.props.shuffle == True:
                    self._update_shuffle_icon(True)
                else:
                    self._update_shuffle_icon(False)
            else:
                self.shuffle_button.set_visible(False)

        self._queue_update(_update_metadata)

    def cleanup(self):
        """Clean up resources to prevent memory leaks."""
        if self._update_timeout_id:
            GLib.source_remove(self._update_timeout_id)
            self._update_timeout_id = None
        self._update_queue.clear()
        self._is_updating = False

    def _is_shuffle_supported(self, player):
        try:
            _ = player.props.shuffle
            return True
        except Exception:
            return False

    def _queue_update(self, update_func, *args, **kwargs):
        """Add an update function to the queue and process if not already running."""
        self._update_queue.append((update_func, args, kwargs))
        if not self._is_updating:
            self._process_queue()

    def _process_queue(self):
        """Process the update queue sequentially."""
        if not self._update_queue or self._is_updating:
            return

        self._is_updating = True
        update_func, args, kwargs = self._update_queue.pop(0)

        try:
            update_func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Error in queue update: {e}")
        finally:
            # Schedule next update after a short delay
            if self._update_timeout_id:
                GLib.source_remove(self._update_timeout_id)
            self._update_timeout_id = GLib.timeout_add(100, self._finish_update)

    def _finish_update(self):
        """Finish current update and process next item in queue."""
        self._is_updating = False
        self._update_timeout_id = None

        if self._update_queue:
            self._process_queue()
        return False

    def _handle_thumbnail(self, metadata, player):
        """Queue thumbnail update to prevent overlapping operations."""

        def _update_thumbnail():
            keys = metadata.keys()
            player_name = player.props.player_name

            new_thumbnail = None

            # Check for MPRIS art URL first
            if "mpris:artUrl" in keys:
                art_url = metadata["mpris:artUrl"]
                if art_url and art_url.strip():
                    new_thumbnail = art_url
                    logger.debug(f"Found MPRIS art for {player_name}: {art_url}")

            # Check for browser players and YouTube URLs
            elif (
                player_name in ["firefox", "chromium", "vivaldi", "brave"]
                and "xesam:url" in keys
            ):
                webpage_url = metadata["xesam:url"]
                if webpage_url and "youtube.com" in webpage_url:
                    # Simple YouTube thumbnail extraction
                    import re

                    match = re.search(r"(?:v=|/)([a-zA-Z0-9_-]{11})", webpage_url)
                    if match:
                        video_id = match.group(1)
                        new_thumbnail = (
                            f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                        )
                        logger.debug(
                            f"Found YouTube thumbnail for {player_name}: {
                                new_thumbnail
                            }"
                        )

            # Only update if thumbnail has changed
            if new_thumbnail and new_thumbnail != self._current_thumbnail:
                self._current_thumbnail = new_thumbnail
                self.album_cover.set_style(f"background-image:url('{new_thumbnail}')")
                logger.debug(f"Updated thumbnail for {player_name}")
            elif not new_thumbnail and self._current_thumbnail:
                # Reset to default if no thumbnail found
                self._current_thumbnail = None
                self.album_cover.set_style(
                    f"background-image:url('{data.HOME_DIR}/.current.wall')"
                )
                logger.debug(f"Reset to default wallpaper for {player_name}")

        self._queue_update(_update_thumbnail)

    def handle_next(self, player):
        def _do_next():
            try:
                self._player._player.next()
            except Exception as e:
                logger.warning(f"Failed to go to next track: {e}")

        self._queue_update(_do_next)

    def handle_prev(self, player):
        def _do_prev():
            try:
                self._player._player.previous()
            except Exception as e:
                logger.warning(f"Failed to go to previous track: {e}")

        self._queue_update(_do_prev)

    def handle_play_pause(self, player):
        def _do_play_pause():
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

        self._queue_update(_do_play_pause)

    def handle_shuffle(self, shuffle_button, player):
        def _do_shuffle():
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

        self._queue_update(_do_shuffle)


class Placeholder(Box):
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
                        center_children=Label(label="Nothing Playing"),
                    )
                ],
            ),
        ]


class PlayerContainer(Box):
    @Signal
    def active_player_changed(self, player: Playerctl.Player) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(name="player-container", orientation="v", **kwargs)

        self.manager = PlayerManager()
        self.manager.connect("new-player", self.new_player)
        self.manager.connect("player-vanish", self.on_player_vanish)
        self.placeholder = Placeholder()
        self.stack = Stack(
            name="player-container",
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
        self.event_box = EventBox(
            child=Box(children=[self.stack, self.player_switch_container]),
        )
        self.children = self.event_box
        self.player = []
        self.player_objects = {}  # Map player names to player objects
        self.active_player = None  # Track the currently active player
        self.manager.init_all_players()

    def new_player(self, manager, player):
        new_player = Player(player=player)
        new_player.set_name(player.props.player_name)
        self.player.append(new_player)
        # Store the player object
        self.player_objects[player.props.player_name] = player
        self.stack.add_named(new_player, player.props.player_name)
        if len(self.player) == 1:
            self.stack.remove(self.placeholder)

        self.player_switch_container.add_center(
            Button(
                name=player.props.player_name,
                style_classes="player-button",
                on_clicked=lambda b: self.switch_player(player.props.player_name, b),
            )
        )

        # If this is the first player, make it active
        if not self.active_player:
            self.active_player = player
            self.active_player_changed(player)

        self.update_player_list()

    def switch_player(self, player_name, button):
        self.stack.set_visible_child_name(player_name)

        for btn in self.player_switch_container.center_children:
            btn.remove_style_class("active")
        button.add_style_class("active")

        # Get the player object and emit signal
        if player_name in self.player_objects:
            self.active_player = self.player_objects[player_name]
            self.active_player_changed(self.active_player)

    def on_player_vanish(self, manager, player):
        player_name = player.props.player_name

        for player_instance in self.player:
            if player_instance.get_name() == player_name:
                player_instance.cleanup()  # Clean up resources
                self.stack.remove(player_instance)
                self.player.remove(player_instance)
                for btn in self.player_switch_container.center_children:
                    if btn.get_name() == player_name:
                        self.player_switch_container.remove_center(btn)
                break

        # Clean up player objects dictionary
        if player_name in self.player_objects:
            del self.player_objects[player_name]

        # If the active player vanished, switch to another one
        if self.active_player and self.active_player.props.player_name == player_name:
            self.active_player = None
            # Try to find another player to make active
            if self.player_objects:
                first_player_name = next(iter(self.player_objects))
                self.active_player = self.player_objects[first_player_name]
                self.active_player_changed(self.active_player)

        self.update_player_list()

        if len(self.player) == 0:
            self.stack.add_named(self.placeholder, "placeholder")

    def update_player_list(self):
        curr = self.stack.get_visible_child()
        if curr:
            for btn in self.player_switch_container.center_children:
                if btn.get_name() == curr.get_name():
                    btn.add_style_class("active")
                else:
                    btn.remove_style_class("active")
