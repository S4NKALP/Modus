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
from shared.widgets.player_box_stack import BasePlayerBoxStack
from utils.gtk_utils import svg_file

CACHE_DIR = f"{data.CACHE_DIR}/media"
PLAYER_FALLBACK_ART = get_relative_path("../../assets/icons/music.svg")
MPRIS_ICON_FALLBACK = "application-x-executable-symbolic"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

_shared_mpris_manager = None


def resolve_mpris_player_icon(player_name: str) -> str:
    """Resolve MPRIS player icon from .desktop file."""
    raw = player_name or ""
    app_name = raw.removeprefix("org.mpris.MediaPlayer2.")

    search_dirs = [
        os.path.join(os.path.expanduser("~/.local/share"), "applications"),
        "/usr/share/applications",
        "/usr/local/share/applications",
    ]
    for d in os.environ.get("XDG_DATA_DIRS", "/usr/share:/usr/local/share").split(":"):
        p = os.path.join(d, "applications")
        if p not in search_dirs:
            search_dirs.append(p)

    candidates = [app_name]
    parts = app_name.split("-")
    for i in range(len(parts) - 1, 0, -1):
        shorter = "-".join(parts[:i])
        if shorter not in candidates:
            candidates.append(shorter)

    for base in search_dirs:
        for name in candidates:
            dp = os.path.join(base, name + ".desktop")
            if os.path.exists(dp):
                try:
                    with open(dp) as f:
                        for line in f:
                            if line.startswith("Icon="):
                                return line[5:].strip()
                except OSError:
                    pass

    # No desktop file found — try app_name as direct icon name
    for name in candidates:
        if name:
            return name

    return MPRIS_ICON_FALLBACK


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


class PlayerBoxStack(BasePlayerBoxStack):
    def __init__(
        self, mpris_manager: PlayerManager = None, control_center=None, **kwargs
    ):
        self.player_stack = Stack(name="player-stack")
        self.current_stack_pos = 0
        self.control_center = control_center
        self.player_buttons: list[Button] = []
        self._signal_connections = []
        self.no_media_box = self._create_no_media_box()

        super().__init__(mpris_manager or get_shared_mpris_manager(), **kwargs)

    def _create_player_box_widget(self, player):
        return PlayerBox(
            player=player, player_stack=self, control_center=self.control_center
        )

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
            start_children=[album_cover],
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

        self.album_cover = Box(
            style_classes="album-image-c", h_align="start", v_align="center"
        )
        self.album_cover.set_style(f"background-image:url('{self.cover_path}')")

        self.image = Overlay(
            child=self.album_cover,
            overlays=[
                Box(
                    children=Image(
                        icon_name=resolve_mpris_player_icon(self.player.player_name),
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
