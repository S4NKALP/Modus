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
from modules.dock.components.player import PlayerContainer


class MusicPlayerPopup(Window):
    """Popup window that shows the full music player interface"""

    def __init__(self, dock_component=None, **kwargs):
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

        self.dock_component = dock_component
        self.player_container = PlayerContainer()
        self.add(self.player_container)

        # Connect player container events to sync with dock
        if self.dock_component:
            self.player_container.connect("active-player-changed", self.on_active_player_changed)

        # Connect to escape key to close
        self.connect("key-press-event", self.on_key_press)
        self.connect("button-press-event", self.on_button_press)
        self.set_can_focus(True)

    def on_active_player_changed(self, container, player):
        """Handle active player change from player container"""
        if self.dock_component and player:
            self.dock_component.set_current_player(player)

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

        # Set up periodic check for active player
        from gi.repository import GLib
        self.active_player_check_timeout = GLib.timeout_add_seconds(2, self.check_active_player)

        # Connect to destroy signal for cleanup
        self.connect("destroy", self.on_destroy)

    def on_destroy(self, widget):
        """Clean up popup when component is destroyed"""
        if hasattr(self, 'active_player_check_timeout'):
            from gi.repository import GLib
            GLib.source_remove(self.active_player_check_timeout)
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def on_new_player(self, manager, player):
        """Handle new player detection"""
        print(f"Music dock component: New player detected - {player.props.player_name}")

        # If this is our first player, make it current
        if not self.current_player:
            self.set_current_player(player)
        else:
            # If the new player is playing, switch to it
            if (player.props.playback_status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING" and
                self.current_player.props.playback_status.value_name != "PLAYERCTL_PLAYBACK_STATUS_PLAYING"):
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

            # Try to find another player with media content
            if hasattr(self.manager, '_manager') and hasattr(self.manager._manager, 'props'):
                for player_name in self.manager._manager.props.player_names:
                    try:
                        from gi.repository import Playerctl
                        candidate_player = Playerctl.Player.new_from_name(player_name)

                        # Check if this player has media content
                        if (hasattr(candidate_player, 'props') and
                            hasattr(candidate_player.props, 'metadata')):
                            metadata = candidate_player.props.metadata
                            if metadata and len(metadata.keys()) > 0:
                                keys = metadata.keys()
                                if ("xesam:title" in keys or
                                    "xesam:artist" in keys or
                                    "mpris:length" in keys):
                                    print(f"[DEBUG] Switching to player with media: {candidate_player.props.player_name}")
                                    self.set_current_player(candidate_player)
                                    break
                    except Exception as e:
                        print(f"[DEBUG] Error checking candidate player {player_name}: {e}")
                        continue

        self.update_visibility()

    def get_playing_player(self):
        """Find a currently playing player from the manager"""
        try:
            if hasattr(self.manager, '_manager') and hasattr(self.manager._manager, 'props'):
                for player_name in self.manager._manager.props.player_names:
                    try:
                        from gi.repository import Playerctl
                        player = Playerctl.Player.new_from_name(player_name)
                        if (hasattr(player, 'props') and
                            hasattr(player.props, 'playback_status') and
                            player.props.playback_status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"):
                            print(f"[DEBUG] Found playing player: {player.props.player_name}")
                            return player
                    except Exception as e:
                        print(f"[DEBUG] Error checking player {player_name}: {e}")
                        continue
        except Exception as e:
            print(f"[DEBUG] Error in get_playing_player: {e}")
        return None

    def check_active_player(self):
        """Periodically check for the currently playing player and switch if needed"""
        try:
            # Find the currently playing player
            playing_player = self.get_playing_player()

            if playing_player:
                # If we found a playing player and it's different from current, switch to it
                if (not self.current_player or
                    self.current_player.props.player_name != playing_player.props.player_name):
                    print(f"[DEBUG] Switching to playing player: {playing_player.props.player_name}")
                    self.set_current_player(playing_player)
            elif self.current_player:
                # If no player is playing, check if current player is paused
                if (self.current_player.props.playback_status.value_name != "PLAYERCTL_PLAYBACK_STATUS_PLAYING"):
                    # Current player is paused, see if there's another player available
                    if hasattr(self.manager, '_manager') and hasattr(self.manager._manager, 'props'):
                        for player_name in self.manager._manager.props.player_names:
                            try:
                                from gi.repository import Playerctl
                                player = Playerctl.Player.new_from_name(player_name)
                                if player.props.player_name != self.current_player.props.player_name:
                                    # Switch to a different available player
                                    print(f"[DEBUG] Switching to available player: {player.props.player_name}")
                                    self.set_current_player(player)
                                    break
                            except:
                                continue

            # Update visibility based on current state
            self.update_visibility()

        except Exception as e:
            print(f"[DEBUG] Error in check_active_player: {e}")

        # Return True to continue the timeout
        return True

    def set_current_player(self, player):
        """Set the current active player"""
        print(f"[DEBUG] Setting current player to: {player.props.player_name}")

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

        # Trigger immediate check for active player when play state changes
        self.check_active_player()
        # Update visibility when playback state changes
        self.update_visibility()

    def on_pause(self, service):
        """Handle pause state"""
        # Always use generic music icon when paused
        self.music_label.set_markup(icons.music)
        self.progress_bar.add_style_class("paused")
        # Update tooltip to show paused state
        if hasattr(self, '_current_track_info'):
            self.event_box.set_tooltip_text(f"{self._current_track_info} (Paused)")

        # Trigger immediate check for active player when pause state changes
        self.check_active_player()
        # Update visibility when playback state changes
        self.update_visibility()

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

        # Update visibility when metadata changes (media content appears/disappears)
        self.update_visibility()

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
                self.popup = MusicPlayerPopup(dock_component=self)
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

    def has_running_players(self):
        """Check if there are any players that actually have media content running"""
        try:
            if hasattr(self.manager, '_manager') and hasattr(self.manager._manager, 'props'):
                for player_name in self.manager._manager.props.player_names:
                    try:
                        from gi.repository import Playerctl
                        player = Playerctl.Player.new_from_name(player_name)

                        # Check if player has metadata indicating actual media content
                        if hasattr(player, 'props') and hasattr(player.props, 'metadata'):
                            metadata = player.props.metadata
                            if metadata and len(metadata.keys()) > 0:
                                # Check for essential metadata that indicates real media
                                keys = metadata.keys()
                                if ("xesam:title" in keys or
                                    "xesam:artist" in keys or
                                    "mpris:length" in keys):
                                    print(f"[DEBUG] Found player with media content: {player.props.player_name}")
                                    return True

                        # Also check if player is currently playing (even without full metadata)
                        if (hasattr(player, 'props') and
                            hasattr(player.props, 'playback_status') and
                            player.props.playback_status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"):
                            print(f"[DEBUG] Found playing player: {player.props.player_name}")
                            return True

                    except Exception as e:
                        print(f"[DEBUG] Error checking player {player_name}: {e}")
                        continue
        except Exception as e:
            print(f"[DEBUG] Error in has_running_players: {e}")

        return False

    def update_visibility(self):
        """Update component visibility based on players with actual media content"""
        # Show component only if there are players with actual media content
        has_media_players = self.has_running_players()
        self.set_visible(has_media_players)

        # Hide in vertical mode if user preference is set
        if data.VERTICAL and hasattr(data, "DOCK_COMPONENTS_VISIBILITY"):
            music_visible = data.DOCK_COMPONENTS_VISIBILITY.get("music_player", True)
            if not music_visible:
                self.set_visible(False)
