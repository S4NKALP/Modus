from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from gi.repository import Gdk

import config.data as data
import utils.icons as icons
from services.mpris import PlayerManager, PlayerService
from utils.wayland import WaylandWindow as Window
from player import PlayerContainer


class MusicPlayerPopup(Window):
    """Popup window that shows the full music player interface"""

    def __init__(self, **kwargs):
        # Get dock position for proper anchoring
        dock_position = data.DOCK_POSITION
        popup_anchor = self._get_popup_anchor(dock_position)
        margin = self._get_popup_margin(dock_position)

        super().__init__(
            name="music-player-popup",
            layer="top",
            anchor=popup_anchor,
            margin=margin,
            exclusive=False,
            keyboard_mode="on-demand",
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.player_container = PlayerContainer()
        self.add(self.player_container)

        # Connect to escape key to close
        self.connect("key-press-event", self.on_key_press)
        self.connect("button-press-event", self.on_button_press)
        self.set_can_focus(True)

    def on_key_press(self, widget, event):
        """Handle key press events"""
        if event.keyval == Gdk.KEY_Escape:
            self.hide_popup()
            return True
        return False

    def show_popup(self):
        """Show the music player popup"""
        self.set_visible(True)
        self.grab_focus()

    def _get_popup_anchor(self, dock_position):
        """Get popup anchor based on dock position"""
        anchor_map = {
            "Top": "top",
            "Bottom": "bottom",
            "Left": "left",
            "Right": "right",
        }
        return anchor_map.get(dock_position, "bottom")

    def _get_popup_margin(self, dock_position):
        """Get popup margin based on dock position"""
        margin_map = {
            "Top": "60px 10px 10px 10px",
            "Bottom": "10px 10px 60px 10px",
            "Left": "10px 10px 10px 60px",
            "Right": "10px 60px 10px 10px",
        }
        return margin_map.get(dock_position, "10px 10px 60px 10px")

    def on_button_press(self, widget, event):
        """Handle button press events"""
        return False

    def hide_popup(self):
        """Hide the music player popup"""
        self.set_visible(False)


class MusicPlayer(Box):
    """Music player component for the dock with circular progress bar"""

    def __init__(self, **kwargs):
        super().__init__(name="music-player", **kwargs)

        # Initialize player manager
        self.manager = PlayerManager()
        self.manager.connect("new-player", self.on_new_player)
        self.manager.connect("player-vanish", self.on_player_vanish)

        # Current player tracking
        self.current_player = None
        self.current_player_service = None
        self.duration = 0.0
        self.position = 0.0
        self._current_track_info = "Music Player"

        # Create circular progress bar
        self.progress_bar = CircularProgressBar(
            name="player-circle",
            size=28,
            line_width=2,
            start_angle=150,
            end_angle=390,
            value=0.0,  # Initialize with 0 progress
        )

        # Create music icon label - always use generic music icon
        self.music_label = Label(name="music-label", markup=icons.music)

        # Create button for the music icon
        self.music_button = Button(
            on_clicked=self.on_music_clicked, child=self.music_label
        )

        # Create event box for scroll events (volume control)
        self.event_box = EventBox(
            events=["scroll", "smooth-scroll"],
            child=Overlay(child=self.progress_bar, overlays=self.music_button),
        )

        # Connect scroll events for seeking
        self.event_box.connect("scroll-event", self.on_scroll)
        self.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)

        self.add(self.event_box)

        # Popup window will be created on-demand
        self.popup = None

        # Initialize players
        self.manager.init_all_players()

        # Set initial visibility
        self.update_visibility()

        # Connect to destroy signal for cleanup
        self.connect("destroy", self.on_destroy)

    def on_destroy(self, widget):
        """Clean up popup when component is destroyed"""
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def on_new_player(self, manager, player):
        """Handle new player detection"""
        print(f"Music dock component: New player detected - {player.props.player_name}")

        # If this is our first player, make it current
        if not self.current_player:
            self.set_current_player(player)

        self.update_visibility()

    def on_player_vanish(self, manager, player):
        """Handle player disappearing"""
        print(f"Music dock component: Player vanished - {player.props.player_name}")

        # If the current player vanished, find another one
        if (
            self.current_player
            and self.current_player.props.player_name == player.props.player_name
        ):
            self.current_player = None
            self.current_player_service = None

            # Try to find another active player
            # This is a simple approach - in a real implementation you might want more sophisticated logic

        self.update_visibility()

    def set_current_player(self, player):
        """Set the current active player"""
        # Disconnect from previous player
        if self.current_player_service:
            try:
                self.current_player_service.disconnect_by_func(self.on_track_position)
                self.current_player_service.disconnect_by_func(self.on_play)
                self.current_player_service.disconnect_by_func(self.on_pause)
                self.current_player_service.disconnect_by_func(self.on_metadata)
            except:
                pass

        self.current_player = player
        self.current_player_service = PlayerService(player=player)

        # Connect to player events
        self.current_player_service.connect("track-position", self.on_track_position)
        self.current_player_service.connect("play", self.on_play)
        self.current_player_service.connect("pause", self.on_pause)
        self.current_player_service.connect("meta-change", self.on_metadata)

        # Always use generic music icon, not player-specific icons
        self.music_label.set_markup(icons.music)

        # Update initial state
        self.update_playback_state()

    def on_track_position(self, service, pos, dur):
        """Handle track position updates"""
        self.position = pos
        self.duration = dur

        if dur > 0:
            progress = pos / dur
            # Use value property instead of set_percentage for CircularProgressBar
            self.progress_bar.value = progress

            # Update tooltip with timestamp info
            pos_min = int(pos // 60)
            pos_sec = int(pos % 60)
            dur_min = int(dur // 60)
            dur_sec = int(dur % 60)
            timestamp_text = f"{pos_min:02d}:{pos_sec:02d} / {dur_min:02d}:{dur_sec:02d}"

            # Get current track info if available
            if hasattr(self, '_current_track_info'):
                tooltip = f"{self._current_track_info}\n{timestamp_text}"
            else:
                tooltip = f"Music Player\n{timestamp_text}"
            self.event_box.set_tooltip_text(tooltip)
        else:
            self.progress_bar.value = 0
            self.event_box.set_tooltip_text("Music Player")

    def on_play(self, service):
        """Handle play state"""
        self.music_label.set_markup(icons.music)
        self.progress_bar.remove_style_class("paused")
        # Update tooltip to show playing state
        if hasattr(self, '_current_track_info'):
            self.event_box.set_tooltip_text(f"{self._current_track_info} (Playing)")

    def on_pause(self, service):
        """Handle pause state"""
        # Always use generic music icon when paused
        self.music_label.set_markup(icons.music)
        self.progress_bar.add_style_class("paused")
        # Update tooltip to show paused state
        if hasattr(self, '_current_track_info'):
            self.event_box.set_tooltip_text(f"{self._current_track_info} (Paused)")

    def on_metadata(self, service, metadata, player):
        """Handle metadata changes"""
        # Update tooltip with current track info
        keys = metadata.keys()
        if "xesam:artist" in keys and "xesam:title" in keys:
            artist = (
                metadata["xesam:artist"][0]
                if metadata["xesam:artist"]
                else "Unknown Artist"
            )
            title = metadata["xesam:title"]
            self._current_track_info = f"{artist} - {title}"

            # If we have position info, include timestamp
            if hasattr(self, 'position') and hasattr(self, 'duration') and self.duration > 0:
                pos_min = int(self.position // 60)
                pos_sec = int(self.position % 60)
                dur_min = int(self.duration // 60)
                dur_sec = int(self.duration % 60)
                timestamp_text = f"{pos_min:02d}:{pos_sec:02d} / {dur_min:02d}:{dur_sec:02d}"
                tooltip = f"{self._current_track_info}\n{timestamp_text}"
            else:
                tooltip = self._current_track_info

            self.event_box.set_tooltip_text(tooltip)
        else:
            self._current_track_info = "Music Player"
            self.event_box.set_tooltip_text("Music Player")

    def update_playback_state(self):
        """Update the visual state based on current playback"""
        if not self.current_player:
            return

        if (
            self.current_player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        ):
            self.on_play(None)
        else:
            self.on_pause(None)

    def on_music_clicked(self, button):
        """Handle music button click - show popup"""
        if self.popup and self.popup.get_visible():
            self.popup.hide_popup()
        else:
            # Create popup on-demand if it doesn't exist
            if not self.popup:
                self.popup = MusicPlayerPopup()
            self.popup.show_popup()

    def on_scroll(self, widget, event):
        """Handle scroll events for seeking"""
        if not self.current_player or self.duration <= 0:
            return False

        # Calculate seek amount (5 seconds per scroll)
        seek_amount = 5.0

        if event.direction == Gdk.ScrollDirection.UP:
            new_position = min(self.position + seek_amount, self.duration)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            new_position = max(self.position - seek_amount, 0)
        else:
            return False

        # Seek to new position
        if self.current_player_service:
            self.current_player_service.set_position(int(new_position))

        return True

    def update_visibility(self):
        """Update component visibility based on available players"""
        # Show component only if there are active players
        has_players = self.current_player is not None
        self.set_visible(has_players)

        # Hide in vertical mode if user preference is set
        if data.VERTICAL and hasattr(data, "DOCK_COMPONENTS_VISIBILITY"):
            music_visible = data.DOCK_COMPONENTS_VISIBILITY.get("music_player", True)
            if not music_visible:
                self.set_visible(False)
