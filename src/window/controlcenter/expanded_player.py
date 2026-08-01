import os

from fabric.utils import GLib, bulk_connect, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.scale import Scale
from fabric.widgets.stack import Stack
from fabric.widgets.wayland import WaylandWindow as Window

from services.mpris import PlayerManager, PlayerService
from shared.widgets.player_box_stack import BasePlayerBoxStack
from utils.gtk_utils import svg_file
from window.controlcenter.player import (
    PLAYER_FALLBACK_ART,
    apply_player_art,
    get_shared_mpris_manager,
    resolve_mpris_player_icon,
)


class EmbeddedExpandedPlayer(Box):
    def __init__(self, control_center, **kwargs):
        super().__init__(
            orientation="vertical",
            h_expand=True,
            name="embedded-expanded-player",
            **kwargs,
        )
        self.control_center = control_center
        self.mpris_manager = get_shared_mpris_manager()
        self.player_content = PlayerBoxStack(self.mpris_manager)
        self.children = [self.player_content]

    def refresh(self):
        pass

    def suspend(self):
        for child in self.player_content.player_stack.get_children():
            if hasattr(child, "suspend"):
                child.suspend()

    def resume(self):
        for child in self.player_content.player_stack.get_children():
            if hasattr(child, "resume"):
                child.resume()

    def _on_map(self, *_):
        self._check_and_update_playing_state()

    def destroy(self):
        if self.player_content and hasattr(self.player_content, "destroy"):
            self.player_content.destroy()
        super().destroy()


class PlayerBoxStack(BasePlayerBoxStack):
    def __init__(self, mpris_manager: PlayerManager, **kwargs):
        self.player_stack = Stack(name="player-stack", transition_type="none")
        self.current_stack_pos = 0
        self.player_buttons: list[Button] = []
        self._signal_connections = []
        self.no_media_box = self._create_no_media_box()

        super().__init__(mpris_manager, **kwargs)

    def _create_player_box_widget(self, player):
        return PlayerBox(player=player, player_stack=self)

    def _create_no_media_box(self):
        fallback_cover_path = PLAYER_FALLBACK_ART
        album_cover = Box(
            style_classes="album-image-c", h_align="start", v_align="center"
        )
        album_cover.set_style(f"background-image:url('{fallback_cover_path}')")

        track_title = Label(
            label="No media playing",
            name="player-title-no",
            justification="left",
            max_chars_width=30,
            ellipsization="end",
            h_align="start",
        )
        track_info = Box(
            name="track-info",
            spacing=5,
            orientation="v",
            v_align="start",
            h_align="start",
            children=[track_title],
        )

        return Box(
            h_align="center",
            name="player-box",
            h_expand=True,
            children=[
                Overlay(
                    child=Box(name="outer-player-box", h_align="start"),
                    overlays=[
                        Box(name="inner-player-box", v_align="center", h_align="start"),
                        Box(
                            name="player-info-box",
                            v_align="center",
                            h_align="start",
                            orientation="v",
                            h_expand=True,
                            children=[track_info],
                        ),
                        album_cover,
                    ],
                )
            ],
        )


class PlayerBox(Box):
    def __init__(self, player: PlayerService, player_stack=None, **kwargs):
        super().__init__(h_align="center", name="player-box", h_expand=True, **kwargs)
        self.player = player
        self.player_stack = player_stack
        self.fallback_cover_path = PLAYER_FALLBACK_ART
        self.cover_path = self.fallback_cover_path
        self.exit = False
        self._user_seeking = False
        self._seek_timeout = None
        self._debounce_seek = None
        self._signal_connections = []
        self._property_bindings = []
        self._seekbar_signal_ids = []
        self._cached_duration = 0

        self.album_cover = Box(
            style_classes="album-image-c",
            h_align="start",
            v_align="center",
        )
        self.album_cover.set_style(
            f"background-image:url('{self.fallback_cover_path}')"
        )
        self.album_cover.set_size_request(70, 70)

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

        self.seek_bar = Scale(
            value=0,
            min_value=0,
            max_value=100,
            increments=(1, 1),
            name="expanded-seek-bar",
            size=1,
            h_expand=True,
        )
        self._seekbar_signal_ids.append(
            self.seek_bar.connect("value-changed", self._on_scale_value_changed)
        )
        self._seekbar_signal_ids.append(
            self.seek_bar.connect("change-value", self._on_change_value)
        )
        self._property_bindings.append(
            self.player.bind_property("can_seek", self.seek_bar, "sensitive")
        )

        self.position_label = Label(
            label="0:00",
            name="macos-position-label",
            justification="left",
            h_align="start",
        )
        self.length_label = Label(
            label="0:00",
            name="macos-length-label",
            justification="right",
            h_align="end",
        )
        self.seek_box = Box(
            name="macos-seek-box",
            orientation="v",
            spacing=2,
            children=[
                self.seek_bar,
                Box(
                    name="macos-labels-box",
                    orientation="h",
                    children=[
                        self.position_label,
                        Box(h_expand=True),
                        self.length_label,
                    ],
                ),
            ],
        )

        self.track_title = Label(
            label=self.player.title or "No Title",
            name="macos-player-title",
            justification="left",
            max_chars_width=24,
            ellipsization="end",
            h_align="start",
            h_expand=True,
        )
        self.track_artist = Label(
            label=", ".join(self.player.artist) if self.player.artist else "No Artist",
            name="macos-player-artist",
            justification="left",
            max_chars_width=24,
            ellipsization="end",
            h_align="start",
            h_expand=True,
            visible=True,
        )
        self.track_album = Label(
            label=self.player.album or "No Album",
            name="macos-player-album",
            justification="left",
            max_chars_width=24,
            ellipsization="end",
            h_align="start",
            visible=True,
        )

        self.track_info = Box(
            name="macos-track-info",
            spacing=4,
            orientation="v",
            v_align="start",
            h_align="fill",
            h_expand=True,
            v_expand=True,
            children=[self.track_title, self.track_artist, self.track_album],
        )

        self.stack_buttons_box = Box(
            h_expand=False,
            v_expand=True,
            name="macos-stack-buttons-box",
            spacing=4,
            orientation="h",
            h_align="center",
            v_align="end",
        )
        self.stack_buttons_box.hide()

        initial_status = str(self.player.playback_status).lower()
        icon_file = (
            "player/play.svg" if initial_status == "paused" else "player/pause.svg"
        )
        self.play_pause_icon = svg_file(icon_file, size=22)
        self.play_pause_button = Button(
            style_classes=["control-buttons"],
            name="macos-play-button",
            child=self.play_pause_icon,
            on_clicked=self.player.play_pause,
        )
        self.next_button = Button(
            style_classes=["control-buttons"],
            name="macos-control-button",
            child=svg_file("player/fwd.svg", size=22),
            on_clicked=self._on_player_next,
        )
        self.prev_button = Button(
            name="macos-control-button",
            child=svg_file("player/rewind.svg", size=22),
            style_classes=["control-buttons"],
            on_clicked=self._on_player_prev,
        )

        self.button_box = Box(
            name="macos-button-box",
            h_align="center",
            h_expand=True,
            spacing=10,
            children=[self.prev_button, self.play_pause_button, self.next_button],
        )
        self.controls_box = Box(
            name="macos-player-controls",
            orientation="v",
            h_expand=True,
            spacing=6,
            h_align="center",
            children=[self.button_box],
        )

        self.children = [
            Box(
                name="macos-outer-player-box",
                orientation="v",
                spacing=10,
                h_expand=True,
                v_expand=True,
                v_align="center",
                h_align="fill",
                children=[
                    Box(
                        orientation="v",
                        h_expand=False,
                        h_align="center",
                        children=[
                            Box(
                                orientation="horizontal",
                                children=[self.image, self.track_info],
                            ),
                            self.seek_box,
                            self.controls_box,
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
                "track-position": self._on_track_position,
                "artwork-change": self._on_artwork_change,
            },
        )
        for handler_id in connections:
            self._signal_connections.append((self.player, handler_id))

        self.seek_bar.connect("realize", self._on_seek_bar_realized)
        if self.seek_bar.get_realized():
            self._on_seek_bar_realized(self.seek_bar)

        result = apply_player_art(self.album_cover, self.player)
        if result:
            self.cover_path = result

        self._load_initial_metadata()

    def _load_initial_metadata(self):
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
                self.track_album.set_label(
                    metadata["xesam:album"] if "xesam:album" in keys else "No Album"
                )
                self._update_duration_from_metadata()
                self.position_label.set_label(
                    self.length_str(self.player.position or 0)
                )
        except Exception as e:
            logger.warning(
                f"[expanded_player] metadata = self.player.metadata failed: {e}"
            )

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

    def length_str(self, length):
        if length is None or length <= 0:
            return "0:00"
        length_seconds = length / 1000000
        hours = int(length_seconds // 3600)
        minutes = int((length_seconds % 3600) // 60)
        seconds = int(length_seconds % 60)
        return (
            f"{hours}:{minutes:02d}:{seconds:02d}"
            if hours > 0
            else f"{minutes}:{seconds:02d}"
        )

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
            self.track_album.set_label(
                metadata["xesam:album"] if "xesam:album" in keys else "No Album"
            )
            if "mpris:length" in keys:
                duration = int(metadata["mpris:length"])
                self.length_label.set_label(self.length_str(duration))
                self.seek_bar.set_range(0, duration / 1_000_000)
            self.position_label.set_label(self.length_str(self.player.position or 0))
        else:
            self.track_title.set_label(self.player.title or "No Title")
            self.track_artist.set_label(
                ", ".join(self.player.artist) if self.player.artist else "No Artist"
            )
            self.track_album.set_label(self.player.album or "No Album")
        self.set_image()

    def suspend(self):
        pass

    def resume(self):
        pass

    def _on_map(self, *_):
        self._check_and_update_playing_state()

    def destroy(self):
        self.exit = True
        self.suspend()
        if self._seek_timeout:
            GLib.source_remove(self._seek_timeout)
            self._seek_timeout = None
        if self._debounce_seek:
            GLib.source_remove(self._debounce_seek)
            self._debounce_seek = None
        for obj, handler_id in self._signal_connections:
            try:
                obj.disconnect(handler_id)
            except Exception as e:
                logger.error(f"An error occurred: {e}")
        super().destroy()

    def _on_player_next(self, *_):
        if self.player:
            self.player.next()

    def _on_player_prev(self, *_):
        if self.player:
            self.player.previous()

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
        if not self.exit:
            current_status = str(self.player.playback_status).lower()
            if getattr(self, "_last_notified_status", None) == current_status:
                return
            self._last_notified_status = current_status

            icon_file = (
                "player/play.svg" if current_status == "paused" else "player/pause.svg"
            )
            if self.play_pause_icon:
                self.play_pause_icon.dynamic_file(icon_file)
            else:
                # Fallback if play_pause_icon isn't available
                from utils.gtk_utils import get_relative_path

                self.play_pause_button.get_child().set_from_file(
                    os.path.join(get_relative_path("assets/icons/"), icon_file)
                )

            self.player_stack.on_player_playback_changed(self, current_status)

    def _on_artwork_change(self, service, local_path, *_):
        if self.exit:
            return
        result = apply_player_art(self.album_cover, self.player, service, local_path)
        if result:
            self.cover_path = result

    def set_image(self, service=None, path=None, *_):
        if self.exit or self.player is None:
            return
        result = apply_player_art(self.album_cover, self.player, service, path)
        if result:
            self.cover_path = result

    def _on_track_position(self, service, pos: float, dur: float):
        if self.exit:
            return
        try:
            position_micros = int(pos * 1_000_000)
            duration_micros = int(dur * 1_000_000)
            if duration_micros <= 0:
                duration_micros = self.player.length or 0

            if duration_micros > 0:
                self._cached_duration = duration_micros
                self.length_label.set_label(self.length_str(duration_micros))

            self.position_label.set_label(self.length_str(position_micros))

            if self.seek_bar.get_realized() and self.seek_bar.get_adjustment():
                adj = self.seek_bar.get_adjustment()
                if duration_micros > 0:
                    self.seek_bar.set_range(0, duration_micros / 1_000_000)
                if not self._user_seeking and adj.get_upper() > 0:
                    self.seek_bar.set_value(position_micros / 1_000_000)
        except Exception as e:
            logger.error(f"[_on_track_position] Error: {e}")

    def _clear_seeking(self):
        self._user_seeking = False
        return False

    def _do_seek(self, value):
        self._debounce_seek = None
        if self.player and not self.exit:
            try:
                self.player.seek_position(value)
            except Exception as e:
                logger.warning(
                    f"[expanded_player] self.player.seek_position(value) failed: {e}"
                )
        if self._seek_timeout:
            GLib.source_remove(self._seek_timeout)

        self._seek_timeout = GLib.timeout_add(1000, self._clear_seeking)
        return False

    def _on_change_value(self, scale, _scroll, value):
        if not self.player or self.exit:
            return False
        self._user_seeking = True
        value = max(0.0, value)
        self.position_label.set_label(self.length_str(int(value * 1_000_000)))

        if self._debounce_seek:
            GLib.source_remove(self._debounce_seek)

        self._debounce_seek = GLib.timeout_add(100, self._do_seek, value)
        return False

    def _update_duration_from_metadata(self):
        try:
            duration = self._cached_duration or self.player.length or 0
            if duration <= 0 and self.seek_bar.get_realized():
                adj = self.seek_bar.get_adjustment()
                if adj.get_upper() > 1:
                    duration = int(adj.get_upper() * 1_000_000)
            if duration > 0:
                self.seek_bar.set_range(0, duration / 1_000_000)
                self.length_label.set_label(self.length_str(duration))
                return True
        except Exception as e:
            logger.warning(
                f"[expanded_player] duration = self._cached_duration or self.player.length or 0 failed: {e}"
            )
        return False

    def _on_seek_bar_realized(self, widget):
        try:
            if not self.exit and self.player:
                self._update_duration_from_metadata()
                self.position_label.set_label(
                    self.length_str(self.player.position or 0)
                )
        except Exception as e:
            logger.error(f"An error occurred: {e}")

    def _on_scale_value_changed(self, scale: Scale):
        if not self.player or self.exit:
            return
        try:
            value = max(0.0, scale.get_value())
            self.position_label.set_label(self.length_str(int(value * 1_000_000)))
        except Exception as e:
            logger.error(f"An error occurred: {e}")


class ExpandedPlayer(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="expanded-player",
            title="modus",
            anchor="top right",
            layer="top",
            exclusivity="auto",
            child=PlayerBoxStack(get_shared_mpris_manager()),
            visible=False,
        )
        self.add_keybinding("Escape", lambda *_: self.set_visible(False))

    def _on_map(self, *_):
        self._check_and_update_playing_state()

    def destroy(self):
        if self.child and hasattr(self.child, "destroy"):
            self.child.destroy()
        super().destroy()

    def hide_controlcenter(self, *_):
        self.set_visible(False)
