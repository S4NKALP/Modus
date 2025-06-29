from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack

from player_service import PlayerManager, PlayerService
from wiggle_bar import WigglyWidget

import icons as icons
import info as info

from loguru import logger


class Player(Box):
    def __init__(self, player, **kwargs):
        super().__init__(style_classes="player", orientation="v", **kwargs)

        if not info.VERTICAL:
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

        self.set_style(
            f"background-image:url('{info.HOME_DIR}/.cache/walls/low_rez.png')"
        )

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
            tooltip_text="Exit",
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
                # h_expand=True,
                # v_expand=True,
                start_children=self.music,
                end_children=self.play_pause_button if not info.VERTICAL else [],
            ),
            Box(
                name="controls",
                # h_expand=True,
                # v_expand=True,
                style_classes="horizontal" if not info.VERTICAL else "vertical",
                spacing=5,
                children=[
                    Button(
                        name="prev-button",
                        child=Label(name="play-previous", markup=icons.previous),
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
                if not info.VERTICAL
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
                                            name="play-previous", markup=icons.previous
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
        self.wiggly.update_value_from_signal(pos / dur)

    def on_seek(self, sender, ratio):
        pos = ratio * self.duration  # duration in seconds
        print(f"Seeking to {pos:.2f}s")
        self._player.set_position(int(pos))

    def on_metadata(self, sender, metadata, player):
        keys = metadata.keys()
        if "xesam:artist" in keys and "xesam:title" in keys:
            _max_chars = 43 if not info.VERTICAL else 30
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
            self.shuffle_button.get_child().set_markup(icons.disable_shuffle)
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

        self.player_switch_container = CenterBox(
            name="player-switch-container",
            orientation="h",
            style_classes="horizontal-player"
            if not info.VERTICAL
            else "vertical-player",
            center_children=[],
        )
        self.children = [self.stack, self.player_switch_container]
        self.player = []
        self.manager.init_all_players()

    def new_player(self, manager, player):
        print(player.props.player_name, "new player")
        print(player)
        new_player = Player(player=player)
        new_player.gtk_wrapper.queue_draw()
        new_player.set_name(player.props.player_name)
        self.player.append(new_player)
        print("stacking dis bitvch")
        self.stack.add_named(new_player, player.props.player_name)

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
        for player_instance in self.player:
            if player_instance.get_name() == player.props.player_name:
                self.stack.remove(player_instance)
                self.player.remove(player_instance)
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
