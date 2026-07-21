from fabric.utils import bulk_connect, get_relative_path, logger, os
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.stack import Stack

import shared.data as data
from services.mpris import PlayerManager, PlayerService
from utils.gtk_utils import svg_file

CACHE_DIR = f"{data.CACHE_DIR}/media"
PLAYER_FALLBACK_ART = get_relative_path("../../assets/icons/music.svg")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

_shared_mpris_manager = None


def get_shared_mpris_manager():
    global _shared_mpris_manager
    if _shared_mpris_manager is None:
        _shared_mpris_manager = PlayerManager()
    return _shared_mpris_manager


def cleanup_shared_mpris_manager():
    global _shared_mpris_manager
    if _shared_mpris_manager is not None:
        try:
            _shared_mpris_manager.destroy()
        except Exception as e:
            logger.warning(f"Failed to destroy shared MPRIS manager: {e}")
        _shared_mpris_manager = None


def apply_player_art(album_cover_widget, player, service=None, path=None):
    """
    Single source of truth for applying album art to any player widget.

    Call patterns:
      - On init / metadata change: apply_player_art(widget, player)
      - From artwork-change signal: apply_player_art(widget, player, service_obj, local_path)

    Returns the applied path, or None if no art is available yet (backend will
    emit artwork-change when the async download completes).
    """
    # artwork-change signal emits (service_obj, local_path_str)
    if path and isinstance(path, str) and os.path.exists(path):
        album_cover_widget.set_style(f"background-image:url('{path}')")
        return path
    # Check if backend already has it cached from a previous download
    if player:
        cached = player.get_artwork()
        if cached and os.path.exists(cached):
            album_cover_widget.set_style(f"background-image:url('{cached}')")
            return cached
    # Nothing yet — backend will emit artwork-change when download finishes
    return None


class PlayerBoxStack(Box):
    def __init__(
        self, mpris_manager: PlayerManager = None, control_center=None, **kwargs
    ):
        self.player_stack = Stack(name="player-stack")
        self.current_stack_pos = 0
        self.control_center = control_center
        self.player_buttons: list[Button] = []
        self._signal_connections = []
        self.no_media_box = self._create_no_media_box()

        super().__init__(orientation="v", name="media", children=[self.player_stack])
        self.player_stack.children = [self.no_media_box]
        self.set_visible(True)
        self.mpris_manager = mpris_manager or get_shared_mpris_manager()
        self.connect("map", self._on_map)

        if self.mpris_manager is not None:
            self._init_mpris_manager()

    def _init_mpris_manager(self):
        try:
            connections = bulk_connect(
                self.mpris_manager,
                {
                    "new-player": self.on_new_player,
                    "player-vanish": self.on_lost_player,
                },
            )
            for handler_id in connections:
                self._signal_connections.append((self.mpris_manager, handler_id))

            for name, player in self.mpris_manager.get_all_services().items():
                self.on_new_player(self.mpris_manager, name, player)
        except Exception as e:
            logger.error(f"Failed to initialize PlayerBoxStack signals: {e}")

    def _on_map(self, *_):
        self._check_and_update_playing_state()

    def destroy(self):
        for obj, handler_id in self._signal_connections:
            try:
                obj.disconnect(handler_id)
            except Exception as e:
                logger.error(f"An error occurred: {e}")
        self._signal_connections.clear()
        super().destroy()

    def suspend(self):
        for child in self.player_stack.get_children():
            if hasattr(child, "suspend"):
                child.suspend()

    def resume(self):
        for child in self.player_stack.get_children():
            if hasattr(child, "resume"):
                child.resume()

    def _create_no_media_box(self):
        fallback_cover_path = get_relative_path("../../assets/icons/music.svg")
        album_cover = Box(style_classes="album-image-c")
        album_cover.set_style(f"background-image:url('{fallback_cover_path}')")

        track_title = Label(
            label="No media playing",
            name="player-title-c",
            justification="left",
            max_chars_width=25,
            ellipsization="end",
            h_align="start",
        )
        track_info = Box(
            name="track-info",
            h_expand=True,
            orientation="v",
            v_align="start",
            h_align="start",
            children=[track_title],
        )

        inner_box = CenterBox(
            name="inner-player-box",
            start_children=[Box(style_classes="album-image-c", children=album_cover)],
            center_children=[
                Box(
                    name="player-info-box-c",
                    h_expand=True,
                    v_align="center",
                    h_align="center",
                    orientation="v",
                    children=[track_info],
                )
            ],
        )
        return Box(
            h_align="center",
            name="player-box",
            h_expand=True,
            children=[
                Box(
                    spacing=5,
                    name="outer-no-player-box-c",
                    h_expand=True,
                    h_align="fill",
                    v_expand=True,
                    children=inner_box,
                )
            ],
        )

    def _find_playing_player_index(self):
        players = self.player_stack.get_children()
        for i, player_box in enumerate(players):
            if (
                hasattr(player_box, "player")
                and str(player_box.player.playback_status).lower() == "playing"
            ):
                return i
        return None

    def _check_and_update_playing_state(self):
        players = [
            p for p in self.player_stack.get_children() if p != self.no_media_box
        ]
        if len(players) > 0:
            if self.no_media_box in self.player_stack.get_children():
                self.player_stack.remove(self.no_media_box)
            playing_index = self._find_playing_player_index()
            if playing_index is not None:
                self.on_player_clicked_by_index(playing_index)
            return

        if (
            len(self.player_stack.get_children()) == 1
            and self.player_stack.get_children()[0] == self.no_media_box
        ):
            return

        self.player_stack.children = [self.no_media_box]
        self.current_stack_pos = 0
        self.player_stack.set_visible_child(self.no_media_box)

    def on_player_playback_changed(self, player_box, status):
        status = str(status).lower()
        if status == "playing":
            players = self.player_stack.get_children()
            for i, pb in enumerate(players):
                if pb == player_box and i != self.current_stack_pos:
                    self.on_player_clicked_by_index(i)
                    break
        elif status in ["paused", "stopped"]:
            self._check_and_update_playing_state()

    def _update_all_player_buttons(self):
        show_buttons = len(self.player_buttons) > 1
        for child in self.player_stack.get_children():
            if hasattr(child, "update_buttons"):
                child.update_buttons(self.player_buttons, show_buttons)

    def on_player_clicked_by_index(self, index):
        if 0 <= index < len(self.player_buttons):
            if self.current_stack_pos < len(self.player_buttons):
                self.player_buttons[self.current_stack_pos].remove_style_class("active")
            self.current_stack_pos = index
            self.player_buttons[self.current_stack_pos].add_style_class("active")
            self.player_stack.set_visible_child(
                self.player_stack.get_children()[self.current_stack_pos]
            )
            self._update_all_player_buttons()

    def on_new_player(self, mpris_manager, name, player):
        if (
            len(self.player_stack.get_children()) == 1
            and self.player_stack.get_children()[0] == self.no_media_box
        ):
            self.player_stack.children = []
            self.current_stack_pos = 0

        new_player_box = PlayerBox(
            player=player, player_stack=self, control_center=self.control_center
        )
        self.player_stack.children = [*self.player_stack.children, new_player_box]
        self.make_new_player_button(new_player_box)
        if self.player_buttons:
            self.player_buttons[self.current_stack_pos].set_style_classes(["active"])
        self._check_and_update_playing_state()
        self._update_all_player_buttons()

    def on_lost_player(self, mpris_manager, bus_name):
        player_box_to_remove = None
        for player_box in self.player_stack.get_children():
            if (
                hasattr(player_box, "player")
                and getattr(player_box.player, "player_name", None) == bus_name
            ):
                player_box_to_remove = player_box
                break

        if player_box_to_remove:
            player_box_to_remove.destroy()

        remaining_players = [
            p for p in self.player_stack.get_children() if p != player_box_to_remove
        ]
        if len(remaining_players) == 0:
            self.player_stack.children = [self.no_media_box]
            self.current_stack_pos = 0
            self.player_buttons = []
            return

        if self.current_stack_pos >= len(self.player_stack.get_children()):
            self.current_stack_pos = max(0, len(self.player_stack.get_children()) - 1)

        if self.player_buttons and self.current_stack_pos < len(self.player_buttons):
            self.player_buttons[self.current_stack_pos].set_style_classes(["active"])
            self.player_stack.set_visible_child(
                self.player_stack.get_children()[self.current_stack_pos]
            )
        self._update_all_player_buttons()

    def make_new_player_button(self, player_box):
        new_button = Button(name="player-stack-button")

        def on_player_button_click(button: Button):
            if self.current_stack_pos < len(self.player_buttons):
                self.player_buttons[self.current_stack_pos].remove_style_class("active")
            if button in self.player_buttons:
                self.current_stack_pos = self.player_buttons.index(button)
                button.add_style_class("active")
                self.player_stack.set_visible_child(player_box)

        new_button.connect("clicked", on_player_button_click)
        self.player_buttons.append(new_button)
        player_box.connect(
            "destroy",
            lambda *_: (
                self.player_buttons.remove(new_button)
                if new_button in self.player_buttons
                else None
            ),
        )


class PlayerBox(Box):
    def __init__(
        self, player: PlayerService, player_stack=None, control_center=None, **kwargs
    ):
        super().__init__(h_align="center", name="player-box", h_expand=True, **kwargs)
        self.player = player
        self.player_stack = player_stack
        self.control_center = control_center
        self.cover_path = PLAYER_FALLBACK_ART
        self.exit = False
        self._signal_connections = []

        self.album_cover = Box(style_classes="album-image-c")
        self.album_cover.set_style(f"background-image:url('{self.cover_path}')")

        self.image = Overlay(
            child=Box(
                h_align="start",
                v_align="center",
                name="player-image-stack",
                children=[self.album_cover],
            ),
            overlays=[
                Box(
                    children=Image(
                        icon_name=self.player.player_name,
                        name="player-app-icon",
                        icon_size=20,
                    ),
                    h_align="end",
                    v_align="end",
                )
            ],
        )

        self.track_title = Label(
            label=self.player.title or "No Title",
            name="player-title-c",
            max_chars_width=25,
            ellipsization="end",
            h_align="start",
        )
        self.track_artist = Label(
            label=", ".join(self.player.artist) if self.player.artist else "No Artist",
            name="player-artist-c",
            max_chars_width=23,
            ellipsization="end",
            h_align="start",
        )

        initial_status = str(self.player.playback_status).lower()
        icon_file = (
            "player/play.svg" if initial_status == "paused" else "player/pause.svg"
        )
        self.play_pause_icon = svg_file(icon_file, size=22)
        self.play_pause_button = Button(
            name="player-button",
            child=self.play_pause_icon,
            on_clicked=self.player.play_pause,
        )
        self.next_button = Button(
            name="player-button",
            child=svg_file("player/fwd.svg", size=22),
            on_clicked=self.player.next,
        )

        self.stack_buttons_box = Box(
            h_expand=False,
            v_expand=False,
            name="macos-stack-buttons-box",
            spacing=4,
            orientation="h",
            h_align="center",
            v_align="end",
        )
        self.stack_buttons_box.hide()

        self.children = [
            Box(
                orientation="v",
                children=[
                    CenterBox(
                        name="box-c",
                        orientation="h",
                        h_align="center",
                        start_children=[
                            Button(
                                spacing=5,
                                name="outer-player-box-c",
                                h_expand=True,
                                on_clicked=self._on_outer_box_clicked,
                                h_align="start",
                                child=Box(
                                    name="inner-player-box",
                                    h_expand=True,
                                    v_align="center",
                                    h_align="start",
                                    children=[
                                        self.image,
                                        Box(
                                            name="player-info-box-c",
                                            v_align="center",
                                            h_expand=True,
                                            h_align="start",
                                            orientation="v",
                                            children=[
                                                Box(
                                                    name="track-info",
                                                    spacing=5,
                                                    orientation="v",
                                                    v_align="start",
                                                    h_align="start",
                                                    children=[
                                                        self.track_title,
                                                        self.track_artist,
                                                    ],
                                                )
                                            ],
                                        ),
                                    ],
                                ),
                            )
                        ],
                        end_children=[
                            Box(
                                name="button-box-c",
                                h_expand=False,
                                spacing=2,
                                children=[self.play_pause_button, self.next_button],
                            )
                        ],
                    ),
                    self.stack_buttons_box,
                ],
            )
        ]
        self.get_children()[0].set_size_request(352, -1)

        connections = bulk_connect(
            self.player,
            {
                "play": self._on_playback_change,
                "pause": self._on_playback_change,
                "meta-change": self._on_metadata,
                "artwork-change": self.set_image,
            },
        )
        for handler_id in connections:
            self._signal_connections.append((self.player, handler_id))

        result = apply_player_art(self.album_cover, self.player)
        if result:
            self.cover_path = result

        try:
            metadata = self.player.metadata
            if metadata:
                keys = metadata.keys()
                self.track_title.set_label(
                    metadata["xesam:title"] if "xesam:title" in keys else "No Title"
                )
                self.track_artist.set_label(
                    ", ".join(metadata["xesam:artist"])
                    if "xesam:artist" in keys and metadata["xesam:artist"]
                    else "No Artist"
                )
        except Exception as e:
            logger.warning(f"[player] metadata = self.player.metadata failed: {e}")

    def update_buttons(self, player_buttons, show_buttons):
        if show_buttons and len(player_buttons) > 1:
            if len(self.stack_buttons_box.get_children()) != len(player_buttons):
                self.stack_buttons_box.children = []
                for i, button in enumerate(player_buttons):
                    dot_button = Button(
                        name="macos-player-switcher-dot",
                        style_classes=["macos-switcher-dot"],
                    )
                    dot_button.connect(
                        "clicked",
                        lambda *_, idx=i: self.player_stack.on_player_clicked_by_index(
                            idx
                        ),
                    )
                    self.stack_buttons_box.children = [
                        *self.stack_buttons_box.children,
                        dot_button,
                    ]

            for i, dot_button in enumerate(self.stack_buttons_box.get_children()):
                if player_buttons[i].get_style_context().has_class("active"):
                    dot_button.add_style_class("active")
                else:
                    dot_button.remove_style_class("active")

            self.stack_buttons_box.show_all()
        else:
            self.stack_buttons_box.hide()

    def _on_outer_box_clicked(self, *_):
        if self.control_center and hasattr(self.control_center, "open_expanded_player"):
            self.control_center.open_expanded_player()

    def _on_metadata(self, *args):
        if self.exit or self.player is None:
            return
        metadata = args[1] if len(args) >= 2 else None
        if metadata is not None:
            keys = metadata.keys()
            self.track_title.set_label(
                metadata["xesam:title"] if "xesam:title" in keys else "No Title"
            )
            self.track_artist.set_label(
                ", ".join(metadata["xesam:artist"])
                if "xesam:artist" in keys and metadata["xesam:artist"]
                else "No Artist"
            )
        else:
            self.track_title.set_label(self.player.title or "No Title")
            self.track_artist.set_label(
                ", ".join(self.player.artist) if self.player.artist else "No Artist"
            )
        self.set_image()

    def refresh_icon(self):
        """Poll-based icon refresh - works even when browser doesn't fire signals."""
        if self.player is None:
            return
        try:
            status = str(self.player.playback_status).lower()
            self.play_pause_icon.dynamic_file(
                "player/play.svg" if status == "paused" else "player/pause.svg"
            )
        except Exception as e:
            logger.error(f"An error occurred: {e}")

    def _on_playback_change(self, service, *args):
        if self.exit or self.player is None:
            return

        current_status = str(self.player.playback_status).lower()
        if getattr(self, "_last_notified_status", None) == current_status:
            return
        self._last_notified_status = current_status

        self.play_pause_icon.dynamic_file(
            "player/play.svg" if current_status == "paused" else "player/pause.svg"
        )
        if self.player_stack:
            self.player_stack.on_player_playback_changed(self, current_status)

    def set_image(self, service=None, path=None, *_):
        if self.exit or self.player is None:
            return
        result = apply_player_art(self.album_cover, self.player, service, path)
        if result:
            self.cover_path = result

    def suspend(self):
        self.exit = True

    def resume(self):
        self.exit = False
        if self.player is not None:
            current_status = str(self.player.playback_status).lower()
            self._last_notified_status = current_status
            self.play_pause_icon.dynamic_file(
                "player/play.svg" if current_status == "paused" else "player/pause.svg"
            )
            self._on_metadata(self.player, self.player.metadata)
            self.set_image()

    def _on_map(self, *_):
        self._check_and_update_playing_state()

    def destroy(self):
        self.exit = True
        for obj, handler_id in self._signal_connections:
            try:
                obj.disconnect(handler_id)
            except Exception as e:
                logger.error(f"An error occurred: {e}")
        super().destroy()
