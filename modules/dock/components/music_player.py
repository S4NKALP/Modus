import os
import tempfile
import urllib.parse

import requests
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from gi.repository import Gdk, GdkPixbuf, GLib

import config.data as data
import utils.icons as icons
from services.mpris import MediaManager
from utils.audio_visualizer import SpectrumRender
from utils.circle_image import CircleImage


class MusicPlayer(EventBox):
    def __init__(self, **kwargs):
        super().__init__(name="music-player", events=["button-press"], **kwargs)

        orientation = "v" if data.VERTICAL else "h"

        self.main_container = Box(
            name="music-player-container",
            spacing=4,
            orientation=orientation,
        )

        self._media_manager = MediaManager()
        self._media_manager.connect("player-appeared", self._on_player_changed)
        self._media_manager.connect("player-vanished", self._on_player_changed)

        self._current_player = None
        self._manually_selected_player = None
        self._update_timeout_id = None
        self._current_player_signals = []

        self._marquee_timeout_id = None
        self._marquee_position = 0
        self._original_title = ""
        self._title_needs_marquee = False

        self._spin_timeout_id = None
        self._spin_angle = 0

        self._show_visualizer = False
        self._create_music_player_view()
        self.add(self.main_container)
        self.connect("button-press-event", self._on_music_player_clicked)

        # Set initial visibility based on configuration
        initial_visibility = data.DOCK_COMPONENTS_VISIBILITY.get("music_player", True)
        self.set_visible(initial_visibility)

        # Ensure visualizer is disabled in vertical mode
        if data.VERTICAL:
            self._show_visualizer = False

        GLib.timeout_add(100, self._delayed_initial_update)

    def _create_music_player_view(self):
        orientation = "v" if data.VERTICAL else "h"

        self.album_thumbnail = CircleImage(
            name="music-album-thumbnail",
            size=30,
            v_align="center",
            visible=True,
        )

        self.album_thumbnail.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.album_thumbnail.connect("button-press-event", self._on_thumbnail_clicked)

        # Create track label (hidden in vertical mode)
        self.track_label = Label(
            name="music-track",
            label="No Media",
            ellipsize=0,
            h_align="center",
        )

        if data.VERTICAL:
            self.track_label.set_visible(False)  # Hide label in vertical mode
            self.track_label.set_size_request(-1, -1)
        else:
            self.track_label.set_visible(True)
            self.track_label.set_size_request(100, -1)

        self.track_label.set_hexpand(False)
        self.track_label.set_vexpand(False)

        self.cavalcade = None
        self.cavalcade_box = None

        self.center_stack = Stack(
            name="music-player-stack",
            transition_type="crossfade",
            transition_duration=100,
            v_align="center",
            v_expand=False,
            children=[self.track_label],
        )
        self.center_stack.set_visible_child(self.track_label)

        self._create_controls()

        self.music_player_box = CenterBox(
            name="music-player-centerbox",
            orientation=orientation,
            h_expand=True,
            h_align="fill",
            v_align="center",
            v_expand=False,
            start_children=self.album_thumbnail,
            center_children=self.center_stack,
            end_children=self.controls_box,
        )

        # Add vertical class for CSS styling
        if data.VERTICAL:
            self.music_player_box.add_style_class("vertical")
            self.main_container.add_style_class("vertical")

        self.main_container.add(self.music_player_box)

    def _load_album_art(self, art_url):
        if hasattr(self, "_last_art_url") and self._last_art_url == art_url:
            return

        if not art_url:
            self._load_fallback_image()
            self._last_art_url = None
            return

        try:
            if art_url.startswith("file://"):
                file_path = urllib.parse.unquote(art_url[7:])
                if os.path.exists(file_path):
                    self.album_thumbnail.set_image_from_file(file_path)
                    self._show_album_art()
                    self._last_art_url = art_url
                else:
                    self._load_fallback_image()
                    self._last_art_url = None
            elif art_url.startswith(("http://", "https://")):
                response = requests.get(art_url)
                if response.status_code == 200:
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=".jpg"
                    ) as temp_file:
                        temp_file.write(response.content)
                        temp_path = temp_file.name

                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(temp_path)
                    self.album_thumbnail.set_image_from_pixbuf(pixbuf)
                    self._show_album_art()
                    self._last_art_url = art_url

                    os.unlink(temp_path)
                else:
                    self._load_fallback_image()
                    self._last_art_url = None
            else:
                self._load_fallback_image()
                self._last_art_url = None
        except Exception:
            self._load_fallback_image()
            self._last_art_url = None

    def _load_fallback_image(self):
        fallback = os.path.expanduser("~/.current.wall")

        try:
            if os.path.exists(fallback):
                self.album_thumbnail.set_image_from_file(fallback)
                self._show_album_art()
            else:
                self._hide_album_art()
        except Exception:
            self._hide_album_art()

    def _show_album_art(self):
        self.album_thumbnail.set_visible(True)
        self._start_spin_animation()

    def _hide_album_art(self):
        self.album_thumbnail.set_visible(False)

    def _start_spin_animation(self):
        if not self._spin_timeout_id:
            self._spin_timeout_id = GLib.timeout_add(
                100, self._animate_spin
            )  # 100ms to save CPU

    def _stop_spin_animation(self):
        if self._spin_timeout_id:
            GLib.source_remove(self._spin_timeout_id)
            self._spin_timeout_id = None
            self._spin_angle = 0
            self.album_thumbnail.angle = 0

    def _animate_spin(self):
        if not self._current_player or not self.album_thumbnail.get_visible():
            return False

        if self._current_player.status == "playing":
            self._spin_angle = (self._spin_angle + 5) % 360
            self.album_thumbnail.angle = self._spin_angle

        return True

    def _update_player_indicators(self):
        available_players = self._media_manager.players

        if len(available_players) <= 1:
            for child in self.player_indicators_box.get_children():
                self.player_indicators_box.remove(child)
            return

        for child in self.player_indicators_box.get_children():
            self.player_indicators_box.remove(child)

        current_player_name = (
            self._current_player.player_name if self._current_player else "None"
        )

        for player in available_players:
            player_name = player.player_name or "Unknown"
            player_icon_markup = self._get_player_icon(player_name)

            indicator_button = Button(
                name="music-player-indicator-button",
                child=Label(
                    name="music-player-indicator",
                    markup=player_icon_markup,
                ),
                can_focus=False,
            )

            is_current_player = player.player_name == current_player_name
            tooltip_text = f"Player: {player_name}"
            if is_current_player:
                tooltip_text += " (Active)"
            else:
                tooltip_text += " - Click to switch"
            indicator_button.set_tooltip_text(tooltip_text)

            if is_current_player:
                indicator_button.get_child().set_name("music-player-indicator-active")
            else:
                indicator_button.get_child().set_name("music-player-indicator")

            indicator_button.connect(
                "clicked", self._on_player_indicator_clicked, player
            )

            self.player_indicators_box.add(indicator_button)

        self.player_indicators_box.show_all()

    def _create_controls(self):
        self.controls_box = Box(
            name="music-controls",
            orientation="h" if not data.VERTICAL else "v",
            spacing=2,
        )

        self.prev_button = Button(
            name="music-prev",
            child=Label(markup=icons.prev),
            can_focus=False,
        )
        self.prev_button.connect("clicked", self._on_previous_clicked)
        self.prev_button.set_tooltip_text("Previous Track")

        self.play_pause_button = Button(
            name="music-play-pause",
            child=Label(name="play-pause-icon", markup=icons.play),
            can_focus=False,
        )
        self.play_pause_button.connect("clicked", self._on_play_pause_clicked)
        self.play_pause_button.set_tooltip_text("Play/Pause")

        self.next_button = Button(
            name="music-next",
            child=Label(markup=icons.next),
            can_focus=False,
        )
        self.next_button.connect("clicked", self._on_next_clicked)
        self.next_button.set_tooltip_text("Next Track")

        self.player_indicators_box = Box(
            name="music-player-indicators",
            orientation="h" if not data.VERTICAL else "v",
            spacing=2,
        )

        self.controls_box.add(self.prev_button)
        self.controls_box.add(self.play_pause_button)
        self.controls_box.add(self.next_button)
        self.controls_box.add(self.player_indicators_box)

    def _delayed_initial_update(self):
        self._update_display()
        return False

    def _connect_player_signals(self, player):
        if player:
            metadata_signal = player.connect(
                "metadata_changed", self._on_metadata_changed
            )
            status_signal = player.connect(
                "playback_status_changed", self._on_playback_status_changed
            )
            self._current_player_signals = [metadata_signal, status_signal]

    def _disconnect_player_signals(self):
        if self._current_player and self._current_player_signals:
            for signal_id in self._current_player_signals:
                try:
                    self._current_player.disconnect(signal_id)
                except:
                    pass  # Signal might already be disconnected
            self._current_player_signals = []

    def _on_metadata_changed(self, *_args):
        GLib.idle_add(self._update_display)

    def _on_playback_status_changed(self, *_args):
        GLib.idle_add(self._update_display)

    def _on_player_changed(self, *_args):
        GLib.idle_add(self._update_display)

    def _update_display(self):
        previous_player = self._current_player

        if self._manually_selected_player:
            manually_selected_available = next(
                (
                    p
                    for p in self._media_manager.players
                    if p.player_name == self._manually_selected_player.player_name
                ),
                None,
            )
            if manually_selected_available:
                self._current_player = manually_selected_available
                self._manually_selected_player = manually_selected_available
            else:
                self._manually_selected_player = None
                self._current_player = self._media_manager.current_player
        else:
            self._current_player = self._media_manager.current_player

        if self._current_player != previous_player:
            self._disconnect_player_signals()
            if self._current_player:
                self._connect_player_signals(self._current_player)

        if not self._current_player:
            # Only hide if the component is disabled in settings
            # If enabled in settings, show a "No Media" state instead of hiding
            if not data.DOCK_COMPONENTS_VISIBILITY.get("music_player", True):
                self.set_visible(False)
            else:
                # Show "No Media" state when enabled but no player is active
                self.set_visible(True)
                # Clear tooltips when no player is active
                self.set_tooltip_text("No media player active")
                self.album_thumbnail.set_tooltip_text("No media player active")
                if not data.VERTICAL:
                    self.track_label.set_tooltip_text("No media player active")

            if self._update_timeout_id:
                GLib.source_remove(self._update_timeout_id)
                self._update_timeout_id = None
            if self._marquee_timeout_id:
                GLib.source_remove(self._marquee_timeout_id)
                self._marquee_timeout_id = None
            self._stop_spin_animation()
            return False

        # Only show if enabled in configuration
        if data.DOCK_COMPONENTS_VISIBILITY.get("music_player", True):
            self.set_visible(True)
        else:
            self.set_visible(False)
            return False

        album_art_url = self._current_player.album_image_url
        if album_art_url:
            self._load_album_art(album_art_url)
        else:
            self._load_fallback_image()

        self._update_stack_display()
        self._update_player_indicators()

        play_pause_icon = self.play_pause_button.get_child()
        if self._current_player.status == "playing":
            play_pause_icon.set_markup(icons.pause)
        else:
            play_pause_icon.set_markup(icons.play)

        # Skip text processing in vertical mode since label is hidden
        if not data.VERTICAL:
            track_title = self._current_player.track_title or "Unknown Track"
            max_display_chars = 12

            self._original_title = track_title
            self._title_needs_marquee = len(track_title) > max_display_chars

            if self._original_title != getattr(self, "_last_original_title", ""):
                self._last_original_title = self._original_title
                self._marquee_position = 0
                self._start_marquee_animation()

            self._update_marquee_text()
        self._update_tooltips()

        self.prev_button.set_sensitive(self._current_player.can_go_previous)
        self.next_button.set_sensitive(self._current_player.can_go_next)
        self.play_pause_button.set_sensitive(self._current_player.can_pause)

        if self._update_timeout_id:
            GLib.source_remove(self._update_timeout_id)
            self._update_timeout_id = None

        return True

    def _start_marquee_animation(self):
        if self._marquee_timeout_id:
            GLib.source_remove(self._marquee_timeout_id)
            self._marquee_timeout_id = None

        if self._title_needs_marquee:
            self._marquee_timeout_id = GLib.timeout_add(250, self._animate_marquee)

    def _animate_marquee(self):
        if not self._current_player:
            return False

        self._marquee_position += 1
        title_length = len(self._original_title)
        loop_length = title_length + 3

        if self._marquee_position >= loop_length:
            self._marquee_position = 0

        self._update_marquee_text()
        return True

    def _update_marquee_text(self):
        if not self._current_player:
            return

        # Skip updating label text in vertical mode since it's hidden
        if data.VERTICAL:
            return

        # Use the same character limit as in _update_display
        max_display_chars = 12

        if self._title_needs_marquee:
            extended_text = self._original_title + "   "
            start_pos = self._marquee_position
            end_pos = start_pos + max_display_chars

            if end_pos <= len(extended_text):
                display_title = extended_text[start_pos:end_pos]
            else:
                part1 = extended_text[start_pos:]
                part2 = self._original_title[: end_pos - len(extended_text)]
                display_title = (part1 + part2)[:max_display_chars]
        else:
            display_title = self._original_title[:max_display_chars]

        self.track_label.set_label(display_title)

    def _get_player_icon(self, player_name):
        if not player_name:
            return icons.disc

        player_name_lower = player_name.lower()

        if "firefox" in player_name_lower:
            return icons.firefox
        elif "spotify" in player_name_lower:
            return icons.spotify
        elif any(
            browser in player_name_lower
            for browser in ["chromium", "chrome", "edge", "brave", "opera", "vivaldi"]
        ):
            return icons.chromium
        else:
            return icons.disc

    def _update_tooltips(self):
        if not self._current_player:
            return

        full_track_title = self._current_player.track_title or "Unknown Track"
        track_artist = self._current_player.track_artist or "Unknown Artist"
        player_name = self._current_player.player_name or "Media Player"

        tooltip_text = f"{full_track_title}\nby {track_artist}\n\nPlayer: {player_name}"

        if data.VERTICAL:
            # In vertical mode, show tooltip on the main container and album thumbnail
            self.set_tooltip_text(tooltip_text)
            self.album_thumbnail.set_tooltip_text(tooltip_text)
        else:
            # In horizontal mode, show tooltip on the track label
            self.track_label.set_tooltip_text(tooltip_text)

    def _on_play_pause_clicked(self, _button):
        if self._current_player:
            self._current_player.play_pause()

    def _on_previous_clicked(self, _button):
        if self._current_player:
            self._current_player.previous()

    def _on_next_clicked(self, _button):
        if self._current_player:
            self._current_player.next()

    def _on_player_indicator_clicked(self, _button, player):
        if player:
            self._manually_selected_player = player
            self._update_display()

    def _on_thumbnail_clicked(self, _widget, _event):
        if self._current_player and not data.VERTICAL:
            # Only toggle visualizer in horizontal mode
            self._show_visualizer = not self._show_visualizer
            self._update_stack_display()
        return True

    def _on_music_player_clicked(self, _widget, _event):
        if self._current_player and not data.VERTICAL:
            # Only toggle visualizer in horizontal mode
            self._show_visualizer = not self._show_visualizer
            self._update_stack_display()
        return True

    def _create_visualizer_if_needed(self):
        if not self.cavalcade:
            self.cavalcade = SpectrumRender()
            self.cavalcade_box = self.cavalcade.get_spectrum_box()
            self.center_stack.add(self.cavalcade_box)

    def _destroy_visualizer(self):
        if self.cavalcade_box:
            self.center_stack.remove(self.cavalcade_box)
            self.cavalcade_box = None
        if self.cavalcade and hasattr(self.cavalcade, "cava"):
            self.cavalcade.cava.close()
            self.cavalcade = None

    def _update_stack_display(self):
        # Never show visualizer in vertical mode
        if self._show_visualizer and self._current_player and not data.VERTICAL:
            self._create_visualizer_if_needed()
            if self.cavalcade_box:
                self.cavalcade_box.set_visible(True)
                self.cavalcade_box.show_all()
                self.center_stack.set_visible_child(self.cavalcade_box)
        else:
            self.center_stack.set_visible_child(self.track_label)
            self._destroy_visualizer()

    def __del__(self):
        self._disconnect_player_signals()

        if self._update_timeout_id:
            GLib.source_remove(self._update_timeout_id)
        if self._marquee_timeout_id:
            GLib.source_remove(self._marquee_timeout_id)
        if self._spin_timeout_id:
            GLib.source_remove(self._spin_timeout_id)

        self._destroy_visualizer()
