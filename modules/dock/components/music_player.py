import time

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.circularprogressbar import CircularProgressBar

from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.revealer import Revealer
from gi.repository import Gdk, GLib, Playerctl

import config.data as data
import utils.icons as icons
from modules.dock.components.player import PlayerContainer
from services.mpris import PlayerManager, PlayerService
from utils.wayland import WaylandWindow as Window


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

        # Create player container first
        self.player_container = PlayerContainer()

        # Get transition type based on dock position
        transition_type = self._get_revealer_transition(dock_position)

        # Create revealer with position-appropriate transition
        self.revealer = Revealer(
            transition_type=transition_type,
            transition_duration=300,
            child=self.player_container,
            reveal_child=False,
        )

        self.add(self.revealer)

        # Connect player container events to sync with dock
        if self.dock_component:
            self.player_container.connect(
                "active-player-changed", self.on_active_player_changed
            )

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
            if self.dock_component:
                self.dock_component._popup_visible = False
            self.hide_popup()
            return True
        return False

    def show_popup(self):
        """Show the music player popup"""
        self.set_visible(True)
        self.show_all()
        # Use GLib.idle_add to ensure the window is shown before revealing
        GLib.idle_add(self._reveal_popup)

    def _reveal_popup(self):
        """Reveal the popup after window is shown"""
        self.revealer.set_reveal_child(True)
        self.grab_focus()
        return False  # Don't repeat

    def _get_popup_anchor(self, dock_position):
        """Get popup anchor based on dock position"""
        anchor_map = {
            "Top": "top",
            "Bottom": "bottom",
            "Left": "top left",
            "Right": "top right",
        }
        return anchor_map.get(dock_position, "bottom")

    def _get_popup_margin(self, dock_position):
        """Get popup margin based on dock position"""
        margin_map = {
            "Top": "60px 10px 10px 10px",
            "Bottom": "10px 10px 60px 10px",
            "Left": "330px 10px 10px 60px",
            "Right": "330px 60px 10px 10px",
        }
        return margin_map.get(dock_position, "10px 10px 60px 10px")

    def _get_revealer_transition(self, dock_position):
        """Get revealer transition type based on dock position"""
        transition_map = {
            "Top": "slide-down",
            "Bottom": "slide-up",
            "Left": "slide-right",
            "Right": "slide-left",
        }
        return transition_map.get(dock_position, "slide-up")

    def on_button_press(self, widget, event):
        """Handle button press events - close popup when clicking outside"""
        if self.dock_component:
            self.dock_component._popup_visible = False
        self.hide_popup()
        return False

    def hide_popup(self):
        """Hide the music player popup"""
        self.revealer.set_reveal_child(False)
        # Hide window after transition completes and notify dock component
        GLib.timeout_add(350, self._complete_hide)

    def _complete_hide(self):
        """Complete the hide process"""
        self.set_visible(False)
        if self.dock_component:
            self.dock_component._popup_visible = False
        return False


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

        # Debouncing for player switching to prevent rapid changes
        self._last_player_switch = 0
        self._switch_debounce_time = 1.0  # 1 second minimum between switches

        # Visibility debouncing to prevent immediate hiding when player closes
        self._visibility_timeout = None
        self._hide_delay = 2.0  # 2 seconds delay before hiding when no players

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

        # Create button for the music icon with click handler
        self.music_button = Button(child=self.music_label)
        self.music_button.connect("clicked", self.on_music_button_clicked)

        # Create overlay without EventBox to fix click issues
        self.overlay = Overlay(child=self.progress_bar, overlays=self.music_button)

        # Add scroll events directly to the overlay for seeking
        self.overlay.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.overlay.connect("scroll-event", self.on_scroll)

        self.add(self.overlay)

        # Pre-create popup for immediate display on click
        self.popup = MusicPlayerPopup(dock_component=self)

        # Track popup visibility state
        self._popup_visible = False

        # Initialize players with delayed visibility check
        GLib.timeout_add(500, self._delayed_init)

        # Hide initially - will show only when media players are detected
        self.hide()

        # Set up periodic check for active player
        self.active_player_check_timeout = GLib.timeout_add_seconds(
            2, self.check_active_player
        )

        # Add recursion protection and debouncing
        self._in_player_switch = False
        self._last_player_switch_time = 0
        self._switch_debounce_ms = 500  # 500ms debounce

        # Connect to destroy signal for cleanup
        self.connect("destroy", self.on_destroy)

    def on_destroy(self, widget):
        """Clean up popup when component is destroyed"""
        try:
            # Remove timeout
            if hasattr(self, "active_player_check_timeout"):
                GLib.source_remove(self.active_player_check_timeout)

            # No hover timeout to clean up anymore

            # Remove visibility timeout
            if hasattr(self, "_visibility_timeout") and self._visibility_timeout:
                GLib.source_remove(self._visibility_timeout)
                self._visibility_timeout = None

            # Clean up current player service
            if hasattr(self, 'current_player_service') and self.current_player_service:
                try:
                    if hasattr(self.current_player_service, 'cleanup'):
                        self.current_player_service.cleanup()
                except Exception:
                    pass

            # Clean up popup
            if hasattr(self, 'popup') and self.popup:
                try:
                    self.popup.destroy()
                    self.popup = None
                except Exception:
                    pass

        except Exception:
            pass

    def on_new_player(self, manager, player):
        """Handle new player detection"""
        # If this is our first player, make it current
        if not self.current_player:
            self.set_current_player(player)
        else:
            # If the new player is playing, switch to it
            if (
                player.props.playback_status.value_name
                == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
                and self.current_player.props.playback_status.value_name
                != "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
            ):
                self.set_current_player(player)

        self.update_visibility()

    def on_player_vanish(self, manager, player):
        """Handle player disappearing"""

        # If the current player vanished, find another one
        if (
            self.current_player
            and self.current_player.props.player_name == player.props.player_name
        ):
            self.current_player = None
            self.current_player_service = None

            # Try to find another player with media content
            if hasattr(self.manager, "_manager") and hasattr(
                self.manager._manager, "props"
            ):
                for player_name in self.manager._manager.props.player_names:
                    try:
                        candidate_player = Playerctl.Player.new_from_name(player_name)

                        # Check if this player has media content
                        if hasattr(candidate_player, "props") and hasattr(
                            candidate_player.props, "metadata"
                        ):
                            metadata = candidate_player.props.metadata
                            if metadata and len(metadata.keys()) > 0:
                                keys = metadata.keys()
                                if (
                                    "xesam:title" in keys
                                    or "xesam:artist" in keys
                                    or "mpris:length" in keys
                                ):
                                    pass
                                    self.set_current_player(candidate_player)
                                    break
                    except Exception:
                        continue

        self.update_visibility()

    def get_playing_player(self):
        """Find a currently playing player from the manager"""
        try:
            if not hasattr(self.manager, "_manager") or not hasattr(self.manager._manager, "props"):
                return None

            player_names = self.manager._manager.props.player_names
            if not player_names:
                return None

            for player_name in player_names:
                try:
                    # Validate player_name before creating player
                    if not player_name or not hasattr(player_name, 'name'):
                        continue

                    player = Playerctl.Player.new_from_name(player_name)

                    # Comprehensive validation of player object
                    if not player:
                        continue

                    if not hasattr(player, "props"):
                        continue

                    if not hasattr(player.props, "playback_status"):
                        continue

                    if not hasattr(player.props, "player_name"):
                        continue

                    # Check if player is actually playing
                    try:
                        status = player.props.playback_status
                        if status and hasattr(status, 'value_name'):
                            if status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING":
                                return player
                    except Exception as e:
                        continue

                except Exception as e:
                    continue

        except Exception as e:
            print(f"[DEBUG] Error in get_playing_player: {e}")
        return None

    def check_active_player(self):
        """Periodically check for the currently playing player and switch if needed"""
        # Prevent recursion during player checking
        if self._in_player_switch:
            return True  # Continue the timeout

        try:
            current_time = time.time()

            # Debounce player switching to prevent rapid changes
            if current_time - self._last_player_switch < self._switch_debounce_time:
                return True

            # Find the currently playing player
            playing_player = self.get_playing_player()

            if playing_player:
                # If we found a playing player and it's different from current, switch to it
                should_switch = False

                if not self.current_player:
                    should_switch = True
                else:
                    try:
                        # Safely compare player names
                        if (hasattr(self.current_player, 'props') and
                            hasattr(self.current_player.props, 'player_name') and
                            hasattr(playing_player, 'props') and
                            hasattr(playing_player.props, 'player_name')):

                            if self.current_player.props.player_name != playing_player.props.player_name:
                                should_switch = True
                        else:
                            # If we can't safely compare, assume we should switch
                            should_switch = True
                    except Exception as e:
                        print(f"[DEBUG] Error comparing players: {e}")
                        should_switch = True

                if should_switch:
                    self.set_current_player(playing_player)
                    self._last_player_switch = current_time

            elif self.current_player:
                # If no player is playing, check if current player is still valid and paused
                try:
                    if (hasattr(self.current_player, 'props') and
                        hasattr(self.current_player.props, 'playback_status') and
                        hasattr(self.current_player.props.playback_status, 'value_name')):

                        if self.current_player.props.playback_status.value_name != "PLAYERCTL_PLAYBACK_STATUS_PLAYING":
                            # Current player is paused, see if there's another player available
                            self._try_switch_to_alternative_player(current_time)
                    else:
                        # Current player is invalid, try to find another
                        self._try_switch_to_alternative_player(current_time)

                except Exception as e:
                    # Current player seems invalid, try to find another
                    self._try_switch_to_alternative_player(current_time)

            # Update visibility based on current state
            self.update_visibility()

        except Exception as e:
            print(f"[DEBUG] Error in check_active_player: {e}")

        # Return True to continue the timeout
        return True

    def _delayed_init(self):
        """Initialize players after a delay to prevent showing during dock startup"""
        try:
            self.manager.init_all_players()
            self.update_visibility()
        except Exception as e:
            print(f"[DEBUG] Error in delayed music player init: {e}")
        return False  # Don't repeat this timeout

    def _try_switch_to_alternative_player(self, current_time):
        """Try to switch to an alternative player when current is paused/invalid"""
        try:
            if not hasattr(self.manager, "_manager") or not hasattr(self.manager._manager, "props"):
                return

            player_names = self.manager._manager.props.player_names
            if not player_names:
                return

            for player_name in player_names:
                try:
                    # Validate player_name
                    if not player_name or not hasattr(player_name, 'name'):
                        continue

                    player = Playerctl.Player.new_from_name(player_name)

                    # Validate player object
                    if not player or not hasattr(player, 'props') or not hasattr(player.props, 'player_name'):
                        continue

                    # Skip if this is the same as current player
                    if (self.current_player and
                        hasattr(self.current_player, 'props') and
                        hasattr(self.current_player.props, 'player_name') and
                        player.props.player_name == self.current_player.props.player_name):
                        continue

                    # Switch to a different available player
                    self.set_current_player(player)
                    self._last_player_switch = current_time
                    break

                except Exception as e:
                    continue

        except Exception as e:
            pass

    def set_current_player(self, player):
        """Set the current active player"""
        # Prevent recursion during player switching
        if self._in_player_switch:
            return

        # Add debouncing to prevent rapid switching
        import time
        current_time = time.time() * 1000  # Convert to milliseconds
        if current_time - self._last_player_switch_time < self._switch_debounce_ms:
            return

        self._in_player_switch = True
        self._last_player_switch_time = current_time
        try:
            # Validate player before proceeding
            if not player or not hasattr(player, 'props') or not hasattr(player.props, 'player_name'):
                return


            # Properly cleanup previous player service
            if self.current_player_service:
                try:
                    # Use the cleanup method if available
                    if hasattr(self.current_player_service, 'cleanup'):
                        self.current_player_service.cleanup()
                    else:
                        # Fallback: Stop any running fabricators/timers manually
                        if hasattr(self.current_player_service, 'pos_fabricator'):
                            try:
                                self.current_player_service.pos_fabricator.stop()
                            except Exception:
                                pass

                    # Disconnect signals safely - avoid bulk disconnect which can cause recursion
                    # Store signal handler IDs for proper cleanup
                    if hasattr(self.current_player_service, '_signal_handlers'):
                        try:
                            for handler_id in self.current_player_service._signal_handlers:
                                self.current_player_service.disconnect(handler_id)
                            self.current_player_service._signal_handlers.clear()
                        except Exception:
                            pass

                except Exception:
                    pass

            self.current_player = player
            self.current_player_service = None

            # Create new player service with error handling and recursion prevention
            try:
                # Validate player before creating service
                if (hasattr(player, 'props') and
                    hasattr(player.props, 'player_name') and
                    player.props.player_name):

                    self.current_player_service = PlayerService(player=player)

                    # Connect to player events with error handling and store handler IDs
                    if self.current_player_service:
                        try:
                            # Initialize signal handlers list for proper cleanup
                            self.current_player_service._signal_handlers = []

                            # Connect signals and store handler IDs
                            handler_id = self.current_player_service.connect("track-position", self.on_track_position)
                            self.current_player_service._signal_handlers.append(handler_id)

                            handler_id = self.current_player_service.connect("play", self.on_play)
                            self.current_player_service._signal_handlers.append(handler_id)

                            handler_id = self.current_player_service.connect("pause", self.on_pause)
                            self.current_player_service._signal_handlers.append(handler_id)

                            handler_id = self.current_player_service.connect("meta-change", self.on_metadata)
                            self.current_player_service._signal_handlers.append(handler_id)
                        except Exception:
                            # If signal connection fails, clean up the service
                            if hasattr(self.current_player_service, 'cleanup'):
                                self.current_player_service.cleanup()
                            self.current_player_service = None
                else:
                    pass

            except Exception:
                self.current_player_service = None

            # Always use generic music icon, not player-specific icons
            self.music_label.set_markup(icons.music)

            # Update initial state only if we have a valid service
            if self.current_player_service:
                self.update_playback_state()

        except Exception as e:
            # Reset to safe state
            self.current_player = None
            self.current_player_service = None
        finally:
            # Always reset recursion protection flag
            self._in_player_switch = False

    def on_track_position(self, service, pos, dur):
        """Handle track position updates"""
        try:
            # Validate input parameters
            if pos is None or dur is None:
                return

            # Ensure pos and dur are numeric
            try:
                pos = float(pos)
                dur = float(dur)
            except (ValueError, TypeError):
                return

            # Validate ranges
            if pos < 0 or dur < 0:
                return

            self.position = pos
            self.duration = dur

            if dur > 0:
                progress = min(pos / dur, 1.0)  # Ensure progress doesn't exceed 1.0

                # Safely update progress bar
                try:
                    self.progress_bar.value = progress
                except Exception:
                    pass


            else:
                # Duration is 0 or unknown - show position only if available
                try:
                    if pos > 0:
                        # Set progress bar to indeterminate state or small progress
                        # Use a pulsing animation or small fixed progress to show activity
                        self.progress_bar.value = 0.1  # Small progress to show activity
                    else:
                        self.progress_bar.value = 0
                except Exception:
                    pass

        except Exception:
            pass

    def on_play(self, service):
        """Handle play state"""
        self.music_label.set_markup(icons.music)
        self.progress_bar.remove_style_class("paused")

        # Trigger immediate check for active player when play state changes
        self.check_active_player()
        # Update visibility when playback state changes
        self.update_visibility()

    def on_pause(self, service):
        """Handle pause state"""
        # Always use generic music icon when paused
        self.music_label.set_markup(icons.music)
        self.progress_bar.add_style_class("paused")

        # Trigger immediate check for active player when pause state changes
        self.check_active_player()
        # Update visibility when playback state changes
        self.update_visibility()

    def on_metadata(self, service, metadata, player):
        """Handle metadata changes"""
        # Store current track info for internal use
        keys = metadata.keys()
        if "xesam:artist" in keys and "xesam:title" in keys:
            artist = (
                metadata["xesam:artist"][0]
                if metadata["xesam:artist"]
                else "Unknown Artist"
            )
            title = metadata["xesam:title"]
            self._current_track_info = f"{artist} - {title}"
        else:
            self._current_track_info = "Music Player"

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

    def on_music_button_clicked(self, button):
        """Handle music button click to toggle popup"""
        if self._popup_visible:
            # Hide popup if currently visible
            self.popup.hide_popup()
            self._popup_visible = False
        else:
            # Show popup if currently hidden
            self.popup.show_popup()
            self._popup_visible = True
        return True

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
            # First check if we have a current player that's still valid
            if self.current_player and self.current_player_service:
                try:
                    # Check if current player still exists and has media
                    if hasattr(self.current_player.props, "metadata"):
                        metadata = self.current_player.props.metadata
                        if metadata and len(metadata.keys()) > 0:
                            keys = metadata.keys()
                            if ("xesam:title" in keys or "xesam:artist" in keys or "mpris:length" in keys):
                                return True
                except Exception:
                    pass

            # Check all available players
            if not hasattr(self.manager, "_manager") or not hasattr(self.manager._manager, "props"):
                return False

            player_names = self.manager._manager.props.player_names
            if not player_names:
                return False

            for player_name in player_names:
                try:
                    # Validate player_name before creating player
                    if not player_name or not hasattr(player_name, 'name'):
                        continue

                    player = Playerctl.Player.new_from_name(player_name)

                    # Validate player object
                    if not player or not hasattr(player, "props"):
                        continue

                    # Check if player has metadata indicating actual media content
                    if hasattr(player.props, "metadata"):
                        try:
                            metadata = player.props.metadata
                            if metadata and len(metadata.keys()) > 0:
                                # Check for essential metadata that indicates real media
                                keys = metadata.keys()
                                if (
                                    "xesam:title" in keys
                                    or "xesam:artist" in keys
                                    or "mpris:length" in keys
                                ):
                                    return True
                        except Exception:
                            pass

                    # Also check if player is currently playing (even without full metadata)
                    # But be more strict - only count as "has media" if actually playing
                    if hasattr(player.props, "playback_status"):
                        try:
                            status = player.props.playback_status
                            if (status and hasattr(status, 'value_name') and
                                status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"):
                                # Double-check that this isn't just a phantom player
                                # by trying to get position or metadata
                                try:
                                    player.get_position()  # This will fail if player is dead
                                    return True
                                except Exception:
                                    pass
                        except Exception:
                            pass

                except Exception:
                    pass

        except Exception:
            pass

        return False

    def update_visibility(self):
        """Update component visibility based on players with actual media content"""
        # Check if music player is enabled in configuration
        if hasattr(data, "DOCK_COMPONENTS_VISIBILITY"):
            music_visible = data.DOCK_COMPONENTS_VISIBILITY.get("music_player", True)
            if not music_visible:
                self.set_visible(False)
                return

        # Check if there are players with actual media content
        has_media_players = self.has_running_players()

        if has_media_players:
            # Cancel any pending hide timeout
            if self._visibility_timeout:
                GLib.source_remove(self._visibility_timeout)
                self._visibility_timeout = None
            # Show immediately when media is available
            self.set_visible(True)
        else:
            # Don't hide immediately - use a delay to prevent flickering
            # when players are restarting or switching
            if not self._visibility_timeout:
                self._visibility_timeout = GLib.timeout_add_seconds(
                    int(self._hide_delay),
                    self._delayed_hide
                )

    def _delayed_hide(self):
        """Hide the component after delay if still no media players"""
        # Double-check that we still don't have media players
        if not self.has_running_players():
            self.set_visible(False)

        # Clear the timeout
        self._visibility_timeout = None
        return False  # Don't repeat the timeout