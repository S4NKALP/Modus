import weakref

from fabric.utils import (
    bulk_connect,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.scale import Scale
from fabric.widgets.stack import Stack
from fabric.widgets.wayland import WaylandWindow as Window

from services.mpris import PlayerManager, PlayerService
from utils.utils import svg_file
from window.controlcenter.player import (
    apply_player_art,
    get_shared_mpris_manager,
    PLAYER_FALLBACK_ART,
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

    def destroy(self):
        if hasattr(self, "player_content") and hasattr(self.player_content, "destroy"):
            self.player_content.destroy()
        super().destroy()


class PlayerBoxStack(Box):
    def __init__(self, mpris_manager: PlayerManager, **kwargs):
        self.player_stack = Stack(name="player-stack", transition_type="none")
        self.current_stack_pos = 0
        self.player_buttons: list[Button] = []
        self._player_widgets = weakref.WeakValueDictionary()
        self._signal_connections = []
        self.no_media_box = self._create_no_media_box()

        super().__init__(orientation="v", name="media", children=[self.player_stack])
        self.player_stack.children = [self.no_media_box]
        self.set_visible(True)
        self.mpris_manager = mpris_manager

        connections = bulk_connect(
            self.mpris_manager,
            {"new-player": self.on_new_player, "player-vanish": self.on_lost_player},
        )
        for handler_id in connections:
            self._signal_connections.append((self.mpris_manager, handler_id))

        for name, player in self.mpris_manager.get_all_services().items():
            self.on_new_player(self.mpris_manager, name, player)

    def destroy(self):
        for obj, handler_id in self._signal_connections:
            try:
                obj.disconnect(handler_id)
            except Exception:
                pass
        self._signal_connections.clear()
        super().destroy()

    def _create_no_media_box(self):
        fallback_cover_path = PLAYER_FALLBACK_ART
        album_cover = Box(style_classes="album-image-c")
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
                        Box(
                            h_align="start",
                            v_align="center",
                            name="player-image-stack",
                            children=[album_cover],
                        ),
                    ],
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

        self.set_visible(True)
        new_player_box = PlayerBox(player=player, player_stack=self)
        self.player_stack.children = [*self.player_stack.children, new_player_box]
        self.make_new_player_button(new_player_box)
        if self.player_buttons:
            self.player_buttons[self.current_stack_pos].set_style_classes(["active"])
        self._check_and_update_playing_state()
        self._update_all_player_buttons()

    def on_lost_player(self, mpris_manager, player_name):
        player_box_to_remove = None
        for player_box in self.player_stack.get_children():
            if (
                hasattr(player_box, "player")
                and player_box.player.player_name == player_name
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

    def _update_all_player_buttons(self):
        players = self.player_stack.get_children()
        for player_box in players:
            if hasattr(player_box, "update_buttons"):
                player_box.update_buttons(self.player_buttons, len(players) > 1)


class PlayerBox(Box):
    def __init__(self, player: PlayerService, player_stack=None, **kwargs):
        super().__init__(h_align="center", name="player-box", h_expand=True, **kwargs)
        self.player = player
        self.player_stack = player_stack
        self.fallback_cover_path = PLAYER_FALLBACK_ART
        self.cover_path = self.fallback_cover_path
        self.exit = False
        self._user_seeking = False
        self._signal_connections = []
        self._property_bindings = []
        self._seekbar_signal_ids = []

        self.album_cover = Box(style_classes="album-image-c")
        self.album_cover.set_style(
            f"background-image:url('{self.fallback_cover_path}')"
        )
        self.album_cover.set_size_request(70, 70)

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
            self.seek_bar.connect("button-press-event", self._on_seek_start)
        )
        self._seekbar_signal_ids.append(
            self.seek_bar.connect("button-release-event", self._on_seek_end)
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
            "player/play.svg" if initial_status == "paused" else "player/Pause.svg"
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
            child=svg_file("player/Rewind.svg", size=22),
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

        result = apply_player_art(self.album_cover, self.player)
        if result:
            self.cover_path = result

    def update_buttons(self, player_buttons, show_buttons):
        self.stack_buttons_box.children = []
        if show_buttons and len(player_buttons) > 1:
            for i, button in enumerate(player_buttons):
                dot_button = Button(
                    name="macos-player-switcher-dot",
                    style_classes=["macos-switcher-dot"],
                )
                if button.get_style_context().has_class("active"):
                    dot_button.add_style_class("active")
                dot_button.connect(
                    "clicked",
                    lambda *_, idx=i: self.player_stack.on_player_clicked_by_index(idx),
                )
                self.stack_buttons_box.children = [
                    *self.stack_buttons_box.children,
                    dot_button,
                ]
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

    def _on_metadata(self, *_):
        if self.exit or self.player is None:
            return
        self.track_title.set_label(self.player.title or "No Title")
        self.track_artist.set_label(
            ", ".join(self.player.artist) if self.player.artist else "No Artist"
        )
        self.track_album.set_label(self.player.album or "No Album")
        self.set_image()
        duration = self.player.length or 0
        if duration > 0:
            self.length_label.set_label(self.length_str(duration))
            if self.seek_bar.get_realized():
                self.seek_bar.set_range(0, min(2147483647, duration))
        else:
            self.length_label.set_label("0:00")
            if self.seek_bar.get_realized():
                self.seek_bar.set_range(0, 100)

    def suspend(self):
        pass

    def resume(self):
        pass

    def destroy(self):
        self.exit = True
        self.suspend()
        for obj, handler_id in self._signal_connections:
            try:
                obj.disconnect(handler_id)
            except Exception:
                pass
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
                "player/play.svg" if status == "paused" else "player/Pause.svg"
            )
        except Exception:
            pass

    def _on_playback_change(self, *_):
        if self.exit or self.player is None:
            return
        status = str(self.player.playback_status).lower()
        self.play_pause_icon.dynamic_file(
            "player/play.svg" if status == "paused" else "player/Pause.svg"
        )
        if self.player_stack:
            self.player_stack.on_player_playback_changed(self, status)

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
        if self.exit or self._user_seeking:
            return
        try:
            position_micros = int(pos * 1_000_000)
            duration_micros = int(dur * 1_000_000)

            self.position_label.set_label(self.length_str(position_micros))

            if duration_micros > 0:
                self.length_label.set_label(self.length_str(duration_micros))

            if self.seek_bar.get_realized() and self.seek_bar.get_adjustment():
                if (
                    duration_micros > 0
                    and self.seek_bar.get_adjustment().get_upper() <= 100
                ):
                    self.seek_bar.set_range(0, min(2147483647, duration_micros))
                if self.seek_bar.get_adjustment().get_upper() > 0:
                    self.seek_bar.set_value(min(2147483647, position_micros))
        except Exception as e:
            print(f"[_on_track_position] Error: {e}")

    def _on_seek_start(self, widget, event):
        self._user_seeking = True
        return False

    def _on_seek_end(self, widget, event):
        self._user_seeking = False
        return False

    def _on_seek_bar_realized(self, widget):
        try:
            if not self.exit and self.player:
                duration = self.player.length or 0
                self.seek_bar.set_range(
                    0, min(2147483647, duration) if duration > 0 else 100
                )
        except Exception:
            pass

    def _on_scale_value_changed(self, scale: Scale):
        if self.player and not self.exit and self._user_seeking:
            try:
                new_position = max(-2147483648, min(2147483647, int(scale.get_value())))
                self.player.position = new_position
                self.position_label.set_label(self.length_str(new_position))
            except Exception:
                pass


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

    def destroy(self):
        if hasattr(self, "child") and hasattr(self.child, "destroy"):
            self.child.destroy()
        super().destroy()

    def hide_controlcenter(self, *_):
        self.set_visible(False)
