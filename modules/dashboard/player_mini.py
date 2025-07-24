from gi.repository import Gdk
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from fabric.widgets.eventbox import EventBox

from services.mpris import PlayerManager, PlayerService
from utils.wiggle_bar import WigglyWidget

import utils.icons as icons
import config.data as data

from loguru import logger

import gi

gi.require_version("Gtk", "3.0")


class PlayerMini(Box):
    def __init__(self, player, **kwargs):
        super().__init__(style_classes="player-mini", **kwargs)

        if not data.VERTICAL:
            self.remove_style_class(
                "vertical"
            )  # vertical class binding from unknown source

        self._player = PlayerService(player=player)

        self.duration = 0.0

        self._player.connect("pause", self.on_pause)
        self._player.connect("play", self.on_play)
        self._player.connect("meta-change", self.on_metadata)
        self._player.connect("shuffle-toggle", self.on_shuffle)
        self._player.connect("track-position", self.on_update_track_position)

        self.player_name = Label(
            name=player.props.player_name,
            style_classes=["player-icon", "mini"],
            markup=getattr(icons, player.props.player_name, icons.disc),
        )

        self.set_style(f"background-image:url('{data.HOME_DIR}/.current.wall')")

        self.song = Label(
            name="song",
            label="song",
            style_classes="mini",
            justification="left",
            h_align="start",
            ellipsization="end",
            max_chars_width=15,
        )
        self.artist = Label(
            name="artist",
            label="artist",
            style_classes="mini",
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
            child=Label(name="play-pause-label", markup=icons.play),
            style_classes="mini",
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
        self.wiggly_bar = Box(
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            children=self.wiggly,
        )

        self.album_cover = Box(style_classes="album-image")
        self.album_cover.set_style(
            f"background-image:url('{data.HOME_DIR}/.current_wall')"
        )

        self.children = [
            self.album_cover,
            Box(
                name="source",
                style_classes="mini",
                v_align="end",
                children=self.player_name,
            ),
            # CenterBox(
            #     name="progress-container",
            #     h_expand=True,
            #     v_expand=True,
            #     orientation="v",
            #     center_children=[self.wiggly_bar],
            # ),
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
                        style_classes="horizontal" if not data.VERTICAL else "vertical",
                        spacing=5,
                        h_expand=True,
                        children=[
                            CenterBox(
                                h_expand=True,
                                v_expand=True,
                                center_children=[
                                    Button(
                                        name="prev-button",
                                        child=Label(
                                            name="play-previous",
                                            style_classes="mini",
                                            markup=icons.previous_fill,
                                        ),
                                        on_clicked=lambda b, *_: self.handle_prev(
                                            player
                                        ),
                                    ),
                                    self.play_pause_button,
                                    Button(
                                        name="next-button",
                                        child=Label(
                                            name="play-next",
                                            style_classes="mini",
                                            markup=icons.next_fill,
                                        ),
                                        on_clicked=lambda b, *_: self.handle_next(
                                            player
                                        ),
                                    ),
                                    # self.shuffle_button,
                                ],
                            )
                        ],
                    ),
                ],
            ),
        ]

        self.on_metadata(self._player, metadata=player.props.metadata, player=player)

    def on_update_track_position(self, sender, pos, dur):
        if dur == 0:
            return
        self.duration = dur
        self.wiggly.update_value_from_signal(pos / dur)

    def on_seek(self, sender, ratio):
        pos = ratio * self.duration  # duration in seconds
        print(f"Seeking to {pos:.2f}s")
        self._player.set_position(int(pos))

    def skip_forward(self, seconds=10):
        self._player._player.seek(seconds * 1000000)

    def skip_backward(self, seconds=10):
        self._player._player.seek(-1 * seconds * 1000000)

    def on_metadata(self, sender, metadata, player):
        keys = metadata.keys()
        if "xesam:artist" in keys and "xesam:title" in keys:
            # _max_chars = 20 if not info.VERTICAL else 30
            song_title = metadata["xesam:title"]
            # if len(song_title) > _max_chars:
            #     song_title = song_title[: _max_chars - 1] + "…"
            self.song.set_label(song_title)

            artist_list = metadata["xesam:artist"]
            artist_name = artist_list[0] if artist_list else "Unknown Artist"
            # if len(artist_name) > _max_chars:
            #     artist_name = artist_name[: _max_chars - 1] + "…"
            self.artist.set_label(artist_name)
            if "mpris:artUrl" in keys:
                self.set_style(f"background-image:url('{metadata['mpris:artUrl']}')")
                self.album_cover.set_style(
                    f"background-image:url('{metadata['mpris:artUrl']}')"
                )

        if (
            player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        ):
            self.on_play(self._player)

        if player.props.shuffle == True:
            self.shuffle_button.get_child().set_markup(icons.disable_shuffle)
            self.shuffle_button.get_child().set_name("disable-shuffle")
        else:
            self.shuffle_button.get_child().set_markup(icons.shuffle)
            self.shuffle_button.get_child().set_name("shuffle")

    def on_pause(self, sender):
        self.play_pause_button.get_child().set_markup(icons.play)
        self.wiggly.dragging = True
        self.wiggly.update_amplitude(True)
        self.wiggly.pause = True
        # self.play_pause_button.add_style_class("pause-track")

    def on_play(self, sender):
        self.play_pause_button.get_child().set_markup(icons.pause)
        self.wiggly.pause = False
        self.wiggly.dragging = False
        self.wiggly.update_amplitude(False)
        # self.play_pause_button.remove_style_class("pause-track")

    def on_shuffle(self, sender, player, status):
        print("callback status", status)
        if status == False:
            self.shuffle_button.get_child().set_markup(icons.shuffle)
            self.shuffle_button.get_child().set_name("shuffle")
        else:
            self.shuffle_button.get_child().set_markup(icons.disable_shuffle)
            self.shuffle_button.get_child().set_name("disable-shuffle")

        self.shuffle_button.get_child().set_style("color: white")

    def handle_next(self, player):
        self._player._player.next()

    def handle_prev(self, player):
        self._player._player.previous()

    def handle_play_pause(self, player):
        is_playing = (
            self._player._player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        )

        def _set_play_ui():
            self.play_pause_button.get_child().set_markup(icons.pause)
            # self.play_pause_button.remove_style_class("pause-track")
            # self.play_pause_button.get_child().set_name("pause-label")

        def _set_pause_ui():
            self.play_pause_button.get_child().set_markup(icons.play)
            # self.play_pause_button.add_style_class("pause-track")
            # self.play_pause_button.get_child().set_name("play-label")

        if is_playing:
            _set_pause_ui()
        else:
            _set_play_ui()

        try:
            self._player._player.play_pause()
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


class PlayerContainerMini(Box):
    def __init__(self, **kwargs):
        super().__init__(name="player-container", style_classes="mini", **kwargs)

        self.manager = PlayerManager()
        self.manager.connect("new-player", self.new_player)
        self.manager.connect("player-vanish", self.on_player_vanish)
        self.stack = Stack(
            # name="player-container",
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

        self.player_switch_container = CenterBox(
            name="player-switch-container",
            orientation="v",
            style_classes=(
                ["horizontal-player", "mini"]
                if not data.VERTICAL
                else "vertical-player"
            ),
            center_children=[],
        )
        self.mini_tile_icon = Label(
            name="disc",
            style_classes=["tile-icon"],
            style="font-size:30px; margin:0px; padding:0px;",
            markup=icons.disc,
            justification="center",
        )

        self.mini_tile_view = CenterBox(
            style_classes=["tile", "mini", "on"],
            v_expand=False,
            center_children=self.mini_tile_icon,
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
        print(player.props.player_name, "new player")
        print(player)
        new_player = PlayerMini(player=player)
        new_player.wiggly_bar.queue_draw()
        new_player.set_name(player.props.player_name)
        self.players.append(new_player)
        print("stacking dis bitvch")
        self.stack.add_named(new_player, player.props.player_name)

        self.player_switch_container.add_center(
            Button(
                name=player.props.player_name,
                style_classes=["player-button", "mini"],
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

    def update_player_list(self):
        curr = self.stack.get_visible_child()
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
        current_index = self.players.index(current_player)

        next_index = (current_index + (1 if forward else -1)) % len(self.players)
        next_player = self.players[next_index]

        for btn in self.player_switch_container.center_children:
            if btn.get_name() == next_player.get_name():
                self.switch_player(next_player.get_name(), btn)
                break

    def on_visible_child_changed(self, *args):
        curr_player = self.stack.get_visible_child().get_name()
        self.mini_tile_icon.set_name(curr_player)
        self.mini_tile_icon.set_markup(getattr(icons, curr_player, icons.disc))

    def get_mini_view(self):
        return self.mini_tile_view
