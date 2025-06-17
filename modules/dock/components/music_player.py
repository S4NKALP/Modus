import config.data as data
import utils.icons as icons
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.eventbox import EventBox
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.stack import Stack
from gi.repository import GLib, Gdk, GdkPixbuf
from services.mpris import MediaManager
from utils.circle_image import CircleImage
from utils.audio_visualizer import SpectrumRender
import urllib.parse
import os
import requests
import tempfile


class MusicPlayer(EventBox):
    def __init__(self, **kwargs):
        super().__init__(
            name="music-player",
            events=["button-press"],
            **kwargs
        )

        orientation = "v" if data.VERTICAL else "h"

        # Create main container box
        self.main_container = Box(
            name="music-player-container",
            spacing=4,
            orientation=orientation,
        )

        # Initialize media manager
        self._media_manager = MediaManager()
        self._media_manager.connect("player-appeared", self._on_player_changed)
        self._media_manager.connect("player-vanished", self._on_player_changed)

        self._current_player = None
        self._manually_selected_player = None
        self._update_timeout_id = None
        self._current_player_signals = []  # Track signal connections for current player

        # Marquee animation variables
        self._marquee_timeout_id = None
        self._marquee_position = 0
        self._original_title = ""
        self._title_needs_marquee = False

        # Thumbnail spinning animation variables
        self._spin_timeout_id = None
        self._spin_angle = 0

        # Visualizer state
        self._show_visualizer = False

        # Create music player view with stack for visualizer/text switching
        self._create_music_player_view()

        # Set the main container as child
        self.add(self.main_container)

        # Connect click handler for the entire music player
        self.connect("button-press-event", self._on_music_player_clicked)

        # Hide initially - will show when media players become available
        self.set_visible(False)

        # Delay initial update to allow MediaManager to initialize properly
        GLib.timeout_add(100, self._delayed_initial_update)

    def _create_music_player_view(self):
        """Create the music player view with stack for visualizer/text switching like PlayerSmall"""
        orientation = "v" if data.VERTICAL else "h"

        # Create CircleImage for album art thumbnails (clickable to toggle visualizer)
        self.album_thumbnail = CircleImage(
            name="music-album-thumbnail",
            size=34,  # Appropriate size for dock
            v_align="center",
            visible=True,  # Always visible, will show default or album art
        )

        # Make album thumbnail clickable to toggle visualizer
        self.album_thumbnail.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.album_thumbnail.connect("button-press-event", self._on_thumbnail_clicked)

        # Create track info display
        self.track_label = Label(
            name="music-track",
            label="No Media",
            ellipsize=0,  # No ellipsize for marquee
            h_align="center",
        )
        # Fixed width to prevent box size changes
        self.track_label.set_size_request(100, -1)
        self.track_label.set_hexpand(False)
        self.track_label.set_vexpand(False)

        # Create spectrum visualizer lazily to save memory
        self.cavalcade = None
        self.cavalcade_box = None

        # Create stack for crossfade between visualizer and text
        self.center_stack = Stack(
            name="music-player-stack",
            transition_type="crossfade",
            transition_duration=100,
            v_align="center",
            v_expand=False,
            children=[self.track_label]  # Start with just track label
        )
        # Start with track label visible
        self.center_stack.set_visible_child(self.track_label)

        # Create control buttons
        self._create_controls()

        # Create main music player layout using CenterBox like PlayerSmall
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

        # Add to main container
        self.main_container.add(self.music_player_box)

    def _load_album_art(self, art_url):
        """Load album art from URL and set it to the CircleImage"""
        # Cache the last loaded URL to avoid reloading the same image
        if hasattr(self, '_last_art_url') and self._last_art_url == art_url:
            return

        if not art_url:
            self._hide_album_art()
            self._last_art_url = None
            return

        try:
            if art_url.startswith('file://'):
                # Handle local file URLs
                file_path = urllib.parse.unquote(art_url[7:])  # Remove 'file://' prefix
                if os.path.exists(file_path):
                    self.album_thumbnail.set_image_from_file(file_path)
                    self._show_album_art()
                    self._last_art_url = art_url
                else:
                    self._hide_album_art()
                    self._last_art_url = None
            elif art_url.startswith(('http://', 'https://')):
                # Handle remote URLs by downloading them first
                response = requests.get(art_url)
                if response.status_code == 200:
                    # Create a temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                        temp_file.write(response.content)
                        temp_path = temp_file.name

                    # Load the image from the temporary file
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(temp_path)
                    self.album_thumbnail.set_image_from_pixbuf(pixbuf)
                    self._show_album_art()
                    self._last_art_url = art_url

                    # Clean up the temporary file
                    os.unlink(temp_path)
                else:
                    self._hide_album_art()
                    self._last_art_url = None
            else:
                self._hide_album_art()
                self._last_art_url = None
        except Exception:
            self._hide_album_art()
            self._last_art_url = None

    def _show_album_art(self):
        """Show album art thumbnail"""
        self.album_thumbnail.set_visible(True)
        # Start spinning animation when showing album art
        self._start_spin_animation()

    def _hide_album_art(self):
        """Hide album art thumbnail"""
        self.album_thumbnail.set_visible(False)
        # Stop spinning animation when hiding album art
        self._stop_spin_animation()

    def _start_spin_animation(self):
        """Start the thumbnail spinning animation"""
        if not self._spin_timeout_id:
            self._spin_timeout_id = GLib.timeout_add(100, self._animate_spin)  # 100ms to save CPU

    def _stop_spin_animation(self):
        """Stop the thumbnail spinning animation"""
        if self._spin_timeout_id:
            GLib.source_remove(self._spin_timeout_id)
            self._spin_timeout_id = None
            # Reset angle to 0
            self._spin_angle = 0
            self.album_thumbnail.angle = 0

    def _animate_spin(self):
        """Animate the thumbnail spinning"""
        if not self._current_player or not self.album_thumbnail.get_visible():
            return False

        # Only spin when music is playing
        if self._current_player.status == "playing":
            self._spin_angle = (self._spin_angle + 5) % 360  # Rotate 2 degrees per frame
            self.album_thumbnail.angle = self._spin_angle

        return True  # Continue animation

    def _update_player_indicators(self):
        """Update the player indicators to show all available players"""
        # Get all available players
        available_players = self._media_manager.players

        # Only show indicators if there are multiple players to save memory
        if len(available_players) <= 1:
            # Clear indicators if only one or no players
            for child in self.player_indicators_box.get_children():
                self.player_indicators_box.remove(child)
            return

        # Clear existing indicators
        for child in self.player_indicators_box.get_children():
            self.player_indicators_box.remove(child)

        current_player_name = self._current_player.player_name if self._current_player else "None"

        # Create indicators for each player (only when multiple players exist)
        for player in available_players:
            player_name = player.player_name or "Unknown"
            player_icon_markup = self._get_player_icon(player_name)

            # Create clickable button with indicator label
            indicator_button = Button(
                name="music-player-indicator-button",
                child=Label(
                    name="music-player-indicator",
                    markup=player_icon_markup,
                ),
                can_focus=False,
            )

            # Set tooltip with player info
            is_current_player = (player.player_name == current_player_name)
            tooltip_text = f"Player: {player_name}"
            if is_current_player:
                tooltip_text += " (Active)"
            else:
                tooltip_text += " - Click to switch"
            indicator_button.set_tooltip_text(tooltip_text)

            # Add visual distinction for active player (you can style this with CSS)
            if is_current_player:
                indicator_button.get_child().set_name("music-player-indicator-active")
            else:
                indicator_button.get_child().set_name("music-player-indicator")

            # Connect click handler with player reference
            indicator_button.connect("clicked", self._on_player_indicator_clicked, player)

            self.player_indicators_box.add(indicator_button)

        # Force refresh the indicators container
        self.player_indicators_box.show_all()

    def _create_controls(self):
        """Create the media control buttons"""
        self.controls_box = Box(
            name="music-controls",
            orientation="h" if not data.VERTICAL else "v",
            spacing=2,
        )

        # Previous button
        self.prev_button = Button(
            name="music-prev",
            child=Label(markup=icons.prev),
            can_focus=False,
        )
        self.prev_button.connect("clicked", self._on_previous_clicked)
        self.prev_button.set_tooltip_text("Previous Track")

        # Play/Pause button
        self.play_pause_button = Button(
            name="music-play-pause",
            child=Label(name="play-pause-icon", markup=icons.play),
            can_focus=False,
        )
        self.play_pause_button.connect("clicked", self._on_play_pause_clicked)
        self.play_pause_button.set_tooltip_text("Play/Pause")

        # Next button
        self.next_button = Button(
            name="music-next",
            child=Label(markup=icons.next),
            can_focus=False,
        )
        self.next_button.connect("clicked", self._on_next_clicked)
        self.next_button.set_tooltip_text("Next Track")

        # Player indicators container
        self.player_indicators_box = Box(
            name="music-player-indicators",
            orientation="h" if not data.VERTICAL else "v",
            spacing=2,
        )

        # Add buttons and indicators to controls
        self.controls_box.add(self.prev_button)
        self.controls_box.add(self.play_pause_button)
        self.controls_box.add(self.next_button)
        self.controls_box.add(self.player_indicators_box)

    def _delayed_initial_update(self):
        """Delayed initial update to allow MediaManager to initialize"""
        self._update_display()
        return False  # Don't repeat this timeout

    def _connect_player_signals(self, player):
        """Connect to player signals for immediate updates"""
        if player:
            # Connect to metadata changes for immediate track/thumbnail updates
            metadata_signal = player.connect("metadata_changed", self._on_metadata_changed)
            status_signal = player.connect("playback_status_changed", self._on_playback_status_changed)
            self._current_player_signals = [metadata_signal, status_signal]

    def _disconnect_player_signals(self):
        """Disconnect from current player signals"""
        if self._current_player and self._current_player_signals:
            for signal_id in self._current_player_signals:
                try:
                    self._current_player.disconnect(signal_id)
                except:
                    pass  # Signal might already be disconnected
            self._current_player_signals = []

    def _on_metadata_changed(self, *_args):
        """Handle immediate metadata changes (track, artist, album art)"""
        GLib.idle_add(self._update_display)

    def _on_playback_status_changed(self, *_args):
        """Handle immediate playback status changes"""
        GLib.idle_add(self._update_display)

    def _on_player_changed(self, *_args):
        """Handle player appearance/disappearance"""
        GLib.idle_add(self._update_display)

    def _update_display(self):
        """Update the display based on current player state"""

        # Store previous player to detect changes
        previous_player = self._current_player

        # Determine current player (manual selection takes priority)
        if self._manually_selected_player:
            # Check if manually selected player is still available
            manually_selected_available = next(
                (p for p in self._media_manager.players
                 if p.player_name == self._manually_selected_player.player_name),
                None
            )
            if manually_selected_available:
                self._current_player = manually_selected_available
                self._manually_selected_player = manually_selected_available
            else:
                # Manual player no longer available, clear selection
                self._manually_selected_player = None
                self._current_player = self._media_manager.current_player
        else:
            self._current_player = self._media_manager.current_player

        # Connect to new player signals if player changed
        if self._current_player != previous_player:
            self._disconnect_player_signals()
            if self._current_player:
                self._connect_player_signals(self._current_player)


        if not self._current_player:
            # No players available, hide the component
            self.set_visible(False)
            if self._update_timeout_id:
                GLib.source_remove(self._update_timeout_id)
                self._update_timeout_id = None
            if self._marquee_timeout_id:
                GLib.source_remove(self._marquee_timeout_id)
                self._marquee_timeout_id = None
            # Stop spinning animation when no player
            self._stop_spin_animation()
            return False

        self.set_visible(True)

        # Try to load album art, hide if not available
        album_art_url = self._current_player.album_image_url
        if album_art_url:
            self._load_album_art(album_art_url)
        else:
            # No album art available, hide thumbnails
            self._hide_album_art()

        # Update stack display (text vs visualizer)
        self._update_stack_display()

        # Update player indicators to show all available players
        self._update_player_indicators()

        # Update play/pause button
        play_pause_icon = self.play_pause_button.get_child()
        if self._current_player.status == "playing":
            play_pause_icon.set_markup(icons.pause)
        else:
            play_pause_icon.set_markup(icons.play)

        # Update track info with marquee animation
        track_title = self._current_player.track_title or "Unknown Track"
        max_display_chars = 12

        self._original_title = track_title
        self._title_needs_marquee = len(track_title) > max_display_chars

        # Reset marquee if title changed
        if self._original_title != getattr(self, '_last_original_title', ''):
            self._last_original_title = self._original_title
            self._marquee_position = 0
            self._start_marquee_animation()

        self._update_marquee_text()
        self._update_tooltips()

        # Update button sensitivity
        self.prev_button.set_sensitive(self._current_player.can_go_previous)
        self.next_button.set_sensitive(self._current_player.can_go_next)
        self.play_pause_button.set_sensitive(self._current_player.can_pause)

        # Remove all polling - rely entirely on signals for updates
        if self._update_timeout_id:
            GLib.source_remove(self._update_timeout_id)
            self._update_timeout_id = None

        return True

    def _start_marquee_animation(self):
        """Start or restart the marquee animation"""
        # Stop existing marquee animation
        if self._marquee_timeout_id:
            GLib.source_remove(self._marquee_timeout_id)
            self._marquee_timeout_id = None

        if self._title_needs_marquee:
            self._marquee_timeout_id = GLib.timeout_add(250, self._animate_marquee)

    def _animate_marquee(self):
        """Animate the marquee scrolling"""
        if not self._current_player:
            return False

        self._marquee_position += 1
        title_length = len(self._original_title)
        loop_length = title_length + 3  # Add spacing between loops

        if self._marquee_position >= loop_length:
            self._marquee_position = 0

        self._update_marquee_text()
        return True

    def _update_marquee_text(self):
        """Update the displayed text based on marquee position"""
        if not self._current_player:
            return

        max_display_chars = 12

        if self._title_needs_marquee:
            extended_text = self._original_title + "   "
            start_pos = self._marquee_position
            end_pos = start_pos + max_display_chars

            if end_pos <= len(extended_text):
                display_title = extended_text[start_pos:end_pos]
            else:
                part1 = extended_text[start_pos:]
                part2 = self._original_title[:end_pos - len(extended_text)]
                display_title = (part1 + part2)[:max_display_chars]
        else:
            display_title = self._original_title[:max_display_chars]

        self.track_label.set_label(display_title)

    def _get_player_icon(self, player_name):
        """Get the appropriate icon for a player based on its name"""
        if not player_name:
            return icons.disc

        player_name_lower = player_name.lower()

        if "firefox" in player_name_lower:
            return icons.firefox
        elif "spotify" in player_name_lower:
            return icons.spotify
        elif any(browser in player_name_lower for browser in [
            "chromium", "chrome", "edge", "brave", "opera", "vivaldi"
        ]):
            return icons.chromium
        else:
            return icons.disc

    def _update_tooltips(self):
        """Update tooltips with full track information"""
        if not self._current_player:
            return

        # Get full track information for tooltip
        full_track_title = self._current_player.track_title or "Unknown Track"
        track_artist = self._current_player.track_artist or "Unknown Artist"
        player_name = self._current_player.player_name or "Media Player"

        # Create tooltip text with full information
        tooltip_text = f"{full_track_title}\nby {track_artist}\n\nPlayer: {player_name}"
        self.track_label.set_tooltip_text(tooltip_text)

    def _on_play_pause_clicked(self, _button):
        """Handle play/pause button click"""
        if self._current_player:
            self._current_player.play_pause()
            # No need for manual update - signal will trigger it

    def _on_previous_clicked(self, _button):
        """Handle previous button click"""
        if self._current_player:
            self._current_player.previous()
            # No need for manual update - signal will trigger it

    def _on_next_clicked(self, _button):
        """Handle next button click"""
        if self._current_player:
            self._current_player.next()
            # No need for manual update - signal will trigger it

    def _on_player_indicator_clicked(self, _button, player):
        """Handle player indicator click to switch players"""
        if player:
            self._manually_selected_player = player
            self._update_display()

    def _on_thumbnail_clicked(self, _widget, _event):
        """Handle thumbnail click to toggle visualizer"""
        if self._current_player:
            self._show_visualizer = not self._show_visualizer
            self._update_stack_display()
        return True  # Stop event propagation

    def _on_music_player_clicked(self, _widget, _event):
        """Handle music player click to toggle between text and visualizer view"""
        if self._current_player:
            self._show_visualizer = not self._show_visualizer
            self._update_stack_display()
        return True

    def _create_visualizer_if_needed(self):
        """Create visualizer lazily to save memory"""
        if not self.cavalcade:
            self.cavalcade = SpectrumRender()
            self.cavalcade_box = self.cavalcade.get_spectrum_box()
            self.center_stack.add(self.cavalcade_box)

    def _destroy_visualizer(self):
        """Destroy visualizer to free memory when not needed"""
        if self.cavalcade_box:
            self.center_stack.remove(self.cavalcade_box)
            self.cavalcade_box = None
        if self.cavalcade and hasattr(self.cavalcade, 'cava'):
            self.cavalcade.cava.close()
            self.cavalcade = None

    def _update_stack_display(self):
        """Update stack to show either text or visualizer"""
        if self._show_visualizer and self._current_player:
            # Create visualizer only when needed
            self._create_visualizer_if_needed()
            if self.cavalcade_box:
                self.cavalcade_box.set_visible(True)
                self.cavalcade_box.show_all()
                self.center_stack.set_visible_child(self.cavalcade_box)
        else:
            # Show text label in stack
            self.center_stack.set_visible_child(self.track_label)
            # Destroy visualizer to save memory when not in use
            self._destroy_visualizer()

    def __del__(self):
        """Cleanup when component is destroyed"""
        # Disconnect player signals
        self._disconnect_player_signals()

        # Clean up all timeouts
        if self._update_timeout_id:
            GLib.source_remove(self._update_timeout_id)
        if self._marquee_timeout_id:
            GLib.source_remove(self._marquee_timeout_id)
        if self._spin_timeout_id:
            GLib.source_remove(self._spin_timeout_id)

        # Clean up visualizer
        self._destroy_visualizer()
