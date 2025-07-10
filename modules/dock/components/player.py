import re

from gi.repository import Playerctl
from fabric.core.service import Signal
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from loguru import logger

import config.data as data
import utils.icons as icons
from services.mpris import PlayerManager, PlayerService
from utils.wiggle_bar import WigglyWidget


class Player(Box):
    def __init__(self, player, **kwargs):
        super().__init__(style_classes="player", orientation="v", **kwargs)

        # Check if we're in vertical mode based on dock position
        vertical_mode = (
            data.DOCK_POSITION in ["Left", "Right"]
            if hasattr(data, "DOCK_POSITION")
            else False
        )

        if not vertical_mode:
            # vertical class binding from unknown source
            self.remove_style_class("vertical")

        self._player = PlayerService(player=player)

        self.duration = 0.0

        self._player.connect("pause", self.on_pause)
        self._player.connect("play", self.on_play)
        self._player.connect("meta-change", self.on_metadata)
        self._player.connect("shuffle-toggle", self.on_shuffle)
        self._player.connect("track-position", self.on_update_track_position)

        self.player_name = Label(
            name=player.props.player_name,
            style_classes="player-icon",
            markup=getattr(icons, player.props.player_name, icons.disc),
        )

        # Use a fallback background image
        self.set_style(f"background-image:url('{data.HOME_DIR}/.current.wall')")

        self.song = Label(
            name="song",
            label="song",
            justification="left",
            h_align="start",
            max_chars_width=10,
        )
        self.artist = Label(
            name="artist", label="artist", justification="left", h_align="start"
        )
        self.music = Box(
            name="music",
            orientation="v",
            h_expand=True,
            v_expand=True,
            children=[self.song, self.artist],
        )

        self.play_pause_button = Button(
            name="pause-button",
            child=Label(name="pause-label", markup=icons.play),
            style_classes="pause-track",
            tooltip_text="Play/Pause",
            on_clicked=lambda b, *_: self.handle_play_pause(player),
        )

        self.shuffle_button = Button(
            name="shuffle-button",
            child=Label(name="shuffle", markup=icons.shuffle),
            on_clicked=lambda b, *_: self.handle_shuffle(b, player),
        )

        self.wiggly = WigglyWidget()
        self.wiggly.connect("on-seek", self.on_seek)
        self.gtk_wrapper = Box(
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            children=self.wiggly,
        )

        self.children = [
            Box(name="source", h_expand=True, v_expand=True, children=self.player_name),
            CenterBox(
                name="details",
                start_children=self.music,
                end_children=self.play_pause_button if not vertical_mode else [],
            ),
            Box(
                name="controls",
                style_classes="horizontal" if not vertical_mode else "vertical",
                spacing=5,
                children=[
                    Button(
                        name="prev-button",
                        child=Label(name="play-previous", markup=icons.prev),
                        on_clicked=lambda b, *_: self.handle_prev(player),
                    ),
                    CenterBox(
                        name="progress-container",
                        h_expand=True,
                        v_expand=True,
                        orientation="v",
                        center_children=[self.gtk_wrapper],
                    ),
                    Button(
                        name="next-button",
                        child=Label(name="play-next", markup=icons.next),
                        on_clicked=lambda b, *_: self.handle_next(player),
                    ),
                    self.shuffle_button,
                ]
                if not vertical_mode
                else [
                    CenterBox(
                        orientation="v",
                        h_expand=True,
                        start_children=[
                            CenterBox(
                                h_expand=True,
                                v_expand=True,
                                v_align="end",
                                start_children=[
                                    Button(
                                        name="prev-button",
                                        child=Label(
                                            name="play-previous", markup=icons.prev
                                        ),
                                        on_clicked=lambda b, *_: self.handle_prev(
                                            player
                                        ),
                                    ),
                                    Button(
                                        name="next-button",
                                        child=Label(
                                            name="play-next", markup=icons.next
                                        ),
                                        on_clicked=lambda b, *_: self.handle_next(
                                            player
                                        ),
                                    ),
                                    self.shuffle_button,
                                ],
                                end_children=self.play_pause_button,
                            )
                        ],
                        end_children=CenterBox(
                            name="progress-container",
                            h_expand=True,
                            v_expand=True,
                            orientation="v",
                            center_children=[self.gtk_wrapper],
                        ),
                    )
                ],
            ),
        ]

        self.on_metadata(self._player, metadata=player.props.metadata, player=player)

    def on_update_track_position(self, sender, pos, dur):
        self.duration = dur
        if dur > 0:
            self.wiggly.update_value_from_signal(pos / dur)
        else:
            # Duration is 0 or unknown - show some activity but don't update progress
            # Keep the current progress or set to a small value to indicate activity
            if pos > 0:
                # Show minimal progress to indicate playback is active
                self.wiggly.update_value_from_signal(0.1)
            else:
                self.wiggly.update_value_from_signal(0.0)

    def on_seek(self, sender, ratio):
        pos = ratio * self.duration  # duration in seconds
        print(f"Seeking to {pos:.2f}s")
        self._player.set_position(int(pos))

    def on_metadata(self, sender, metadata, player):
        keys = metadata.keys()
        if "xesam:artist" in keys and "xesam:title" in keys:
            # Check if we're in vertical mode
            vertical_mode = (
                data.DOCK_POSITION in ["Left", "Right"]
                if hasattr(data, "DOCK_POSITION")
                else False
            )
            _max_chars = 43 if not vertical_mode else 30

            song_title = metadata["xesam:title"]
            if len(song_title) > _max_chars:
                song_title = song_title[: _max_chars - 1] + "…"
            self.song.set_label(song_title)

            artist_list = metadata["xesam:artist"]
            artist_name = artist_list[0] if artist_list else "Unknown Artist"
            if len(artist_name) > _max_chars:
                artist_name = artist_name[: _max_chars - 1] + "…"
            self.artist.set_label(artist_name)

            if "mpris:artUrl" in keys:
                self.set_style(f"background-image:url('{metadata['mpris:artUrl']}')")
            elif "xesam:url" in keys and "youtube.com" in metadata["xesam:url"]:
                # Simple YouTube thumbnail extraction for Firefox
                url = metadata["xesam:url"]
                match = re.search(r"(?:v=|/)([a-zA-Z0-9_-]{11})", url)
                if match:
                    video_id = match.group(1)
                    thumbnail_url = (
                        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                    )
                    self.set_style(f"background-image:url('{thumbnail_url}')")
                    print(f"Using YouTube thumbnail: {thumbnail_url}")
                else:
                    # Fallback to default wallpaper
                    self.set_style(
                        f"background-image:url('{data.HOME_DIR}/.current.wall')"
                    )
            else:
                # Fallback to default wallpaper when no artwork is available
                self.set_style(f"background-image:url('{data.HOME_DIR}/.current.wall')")

        if (
            player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        ):
            self.on_play(self._player)

        if player.props.shuffle == True:
            self.shuffle_button.get_child().set_markup(
                icons.shuffle
            )  # Use same icon for now
            self.shuffle_button.get_child().set_name("disable-shuffle")
        else:
            self.shuffle_button.get_child().set_markup(icons.shuffle)
            self.shuffle_button.get_child().set_name("shuffle")

    def on_pause(self, sender):
        self.play_pause_button.get_child().set_markup(icons.play)
        self.play_pause_button.get_child().set_name("pause-label")
        self.wiggly.dragging = True
        self.wiggly.update_amplitude(True)
        self.wiggly.pause = True
        self.play_pause_button.add_style_class("pause-track")

    def on_play(self, sender):
        self.play_pause_button.get_child().set_markup(icons.pause)
        self.play_pause_button.get_child().set_name("play-label")
        self.wiggly.pause = False
        self.wiggly.dragging = False
        self.wiggly.update_amplitude(False)
        self.play_pause_button.remove_style_class("pause-track")

    def on_shuffle(self, sender, player, status):
        print("callback status", status)
        if status == False:
            self.shuffle_button.get_child().set_markup(icons.shuffle)
            self.shuffle_button.get_child().set_name("shuffle")
        else:
            self.shuffle_button.get_child().set_markup(
                icons.shuffle
            )  # Use same icon for now
            self.shuffle_button.get_child().set_name("disable-shuffle")

        self.shuffle_button.get_child().set_style("color: white")

    def handle_next(self, player):
        player.next()

    def handle_prev(self, player):
        player.previous()

    def handle_play_pause(self, player):
        is_playing = self.play_pause_button.get_child().get_name() == "play-label"

        def _set_play_ui():
            self.play_pause_button.get_child().set_markup(icons.pause)
            self.play_pause_button.remove_style_class("pause-track")
            self.play_pause_button.get_child().set_name("pause-label")

        def _set_pause_ui():
            self.play_pause_button.get_child().set_markup(icons.play)
            self.play_pause_button.add_style_class("pause-track")
            self.play_pause_button.get_child().set_name("play-label")

        if is_playing:
            _set_pause_ui()
        else:
            _set_play_ui()

        try:
            player.play_pause()
        except Exception as e:
            # revert if signal failed
            if is_playing:
                _set_pause_ui()
            else:
                _set_play_ui()
            logger.warning("Failed to toggle playback:", e)

    def handle_shuffle(self, shuffle_button, player):
        print("shuffle", player.props.shuffle)
        if player.props.shuffle == False:
            player.set_shuffle(True)
            print("setting to true", player.props.player_name)
        else:
            player.set_shuffle(False)
        shuffle_button.get_child().set_style("color: var(--outline)")


class PlayerContainer(Box):
    @Signal
    def active_player_changed(self, player: Playerctl.Player) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(name="player-container", orientation="v", **kwargs)

        self.manager = PlayerManager()
        self.manager.connect("new-player", self.new_player)
        self.manager.connect("player-vanish", self.on_player_vanish)
        self.stack = Stack(
            name="player-container",
            transition_type="crossfade",
            transition_duration=100,
            children=[],
        )

        self.player_stack = Stack(
            name="player-stack",
            transition_type="crossfade",
            transition_duration=100,
            children=[],
        )

        # Check if we're in vertical mode
        vertical_mode = (
            data.DOCK_POSITION in ["Left", "Right"]
            if hasattr(data, "DOCK_POSITION")
            else False
        )

        self.player_switch_container = CenterBox(
            name="player-switch-container",
            orientation="h",
            style_classes="horizontal-player"
            if not vertical_mode
            else "vertical-player",
            center_children=[],
        )
        self.children = [self.stack, self.player_switch_container]
        self.player = []
        self.player_objects = {}  # Map player names to player objects
        self.active_player = None  # Track the currently active player
        self.manager.init_all_players()

    def new_player(self, manager, player):
        print(player.props.player_name, "new player")
        print(player)
        new_player = Player(player=player)
        new_player.gtk_wrapper.queue_draw()
        new_player.set_name(player.props.player_name)
        self.player.append(new_player)
        # Store the player object
        self.player_objects[player.props.player_name] = player
        print("stacking player")
        self.stack.add_named(new_player, player.props.player_name)

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

    def update_player_list(self):
        curr = self.stack.get_visible_child()
        if curr:
            for btn in self.player_switch_container.center_children:
                print(btn.get_name())
                if btn.get_name() == curr.get_name():
                    btn.add_style_class("active")
                else:
                    btn.remove_style_class("active")