import re
import time
from typing import List

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.stack import Stack

from fabric.utils import GLib, GObject, Gio, logger, bulk_connect, get_relative_path, os

import shared.data as data
from services.mpris import MprisPlayer, MprisPlayerManager
from utils.utils import svg_file

CACHE_DIR = f"{data.CACHE_DIR}/media"
MEDIA_CACHE = CACHE_DIR
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
if not os.path.exists(MEDIA_CACHE):
    os.makedirs(MEDIA_CACHE)

# Global shared MPRIS manager
_shared_mpris_manager = None


def get_shared_mpris_manager():
    """Get shared MPRIS manager instance to reduce memory usage."""
    global _shared_mpris_manager
    if _shared_mpris_manager is None:
        # Create MPRIS manager immediately but don't wait for DBus discovery
        _shared_mpris_manager = MprisPlayerManager()
    return _shared_mpris_manager


def cleanup_shared_mpris_manager():
    """Clean up the shared MPRIS manager to free memory."""
    global _shared_mpris_manager
    if _shared_mpris_manager is not None:
        try:
            _shared_mpris_manager.destroy()
        except Exception as e:
            logger.warning(f"Failed to destroy shared MPRIS manager: {e}")
        _shared_mpris_manager = None


def cleanup_old_cache_files():
    """Clean up old artwork cache files (older than 1 day) and limit total cache size."""
    try:
        if not os.path.exists(CACHE_DIR):
            return

        current_time = time.time()
        one_day_ago = current_time - (24 * 60 * 60)  # 24 hours
        cache_files = []

        # Collect all cache files with their modification times
        for filename in os.listdir(CACHE_DIR):
            filepath = os.path.join(CACHE_DIR, filename)
            try:
                if os.path.isfile(filepath):
                    file_mtime = os.path.getmtime(filepath)
                    file_size = os.path.getsize(filepath)
                    cache_files.append((filepath, file_mtime, file_size))
            except Exception:
                pass  # Ignore individual file errors

        # Remove files older than 1 day
        total_size = 0
        recent_files = []
        for filepath, file_mtime, file_size in cache_files:
            if file_mtime < one_day_ago:
                try:
                    os.unlink(filepath)
                except Exception:
                    pass
            else:
                recent_files.append((filepath, file_mtime, file_size))
                total_size += file_size

        # If cache is still too large (>50MB), remove oldest files
        MAX_CACHE_SIZE = 50 * 1024 * 1024  # 50MB
        if total_size > MAX_CACHE_SIZE:
            # Sort by modification time (oldest first)
            recent_files.sort(key=lambda x: x[1])
            for filepath, _, file_size in recent_files:
                if total_size <= MAX_CACHE_SIZE:
                    break
                try:
                    os.unlink(filepath)
                    total_size -= file_size
                except Exception:
                    pass

    except Exception:
        pass  # Ignore all errors in cleanup


class PlayerBoxStack(Box):
    """A widget that displays the current player information."""

    def __init__(
        self, mpris_manager: MprisPlayerManager = None, control_center=None, **kwargs
    ):
        # Defer cache cleanup to avoid blocking startup
        GLib.idle_add(cleanup_old_cache_files)

        # The player stack
        self.player_stack = Stack(
            # transition_type="slide-left-right",
            # transition_duration=500,
            name="player-stack",
        )
        self.current_stack_pos = 0
        self.control_center = control_center

        # List to store player buttons
        self.player_buttons: list[Button] = []

        # Track signal connections for cleanup
        self._signal_connections = []

        # Create a "No media playing" placeholder
        self.no_media_box = self._create_no_media_box()

        super().__init__(orientation="v", name="media", children=[self.player_stack])

        # Show the no media box initially
        self.player_stack.children = [self.no_media_box]
        self.set_visible(True)

        # Use shared MPRIS manager if none provided
        self.mpris_manager = mpris_manager

        # Initialize MPRIS manager if provided, otherwise defer
        if self.mpris_manager is not None:
            self._init_mpris_manager()
        else:
            # Will be initialized later via _init_mpris_manager()
            pass

        # Connect to visibility changes for cleanup
        self.connect("notify::visible", self._on_visibility_changed)

    def _on_visibility_changed(self, widget, param):
        """Monitor visibility changes to debug hiding issues."""
        is_visible = self.get_visible()
        logger.debug(f"[PlayerBoxStack] Visibility changed to: {is_visible}")

        if not is_visible:
            # Check if we should be visible
            current_children = self.player_stack.get_children()
            if len(current_children) > 0:
                logger.warning(
                    f"[PlayerBoxStack] Widget was hidden but has {len(current_children)} children - forcing visibility"
                )
                GLib.idle_add(self.set_visible, True)

    def set_visible(self, visible: bool) -> None:
        """Override set_visible to ensure the widget is never hidden when it should show content."""
        # Always ensure the widget is visible if we have content to show
        if not visible:
            current_children = self.player_stack.get_children()
            if len(current_children) > 0:
                # Don't allow hiding if we have content
                logger.debug(
                    "[PlayerBoxStack] Preventing widget from being hidden - has content"
                )
                return

        super().set_visible(visible)

    def get_visible(self) -> bool:
        """Override get_visible to ensure the widget always reports as visible when it has content."""
        # Check if we have content to show
        current_children = self.player_stack.get_children()
        if len(current_children) > 0:
            # If we have content, we should always be visible
            return True

        # Otherwise, use the parent's visibility state
        return super().get_visible()

    def _init_mpris_manager(self):
        """Initialize MPRIS manager and connect signals"""
        if self.mpris_manager is None:
            return

        try:
            # Track connections for cleanup - store (object, handler_id) tuples
            connections = bulk_connect(
                self.mpris_manager,
                {
                    "player-appeared": self.on_new_player,
                    "player-vanished": self.on_lost_player,
                },
            )
            # Store as (object, handler_id) tuples
            for handler_id in connections:
                self._signal_connections.append((self.mpris_manager, handler_id))

            # Process existing players asynchronously to avoid blocking
            def process_existing_players():
                try:
                    for player in self.mpris_manager.players.values():  # type: ignore
                        self.on_new_player(self.mpris_manager, player)
                    logger.debug("PlayerBoxStack initialized successfully")
                except Exception as e:
                    logger.error(f"Failed to process existing players: {e}")

            # Use idle_add to process players asynchronously
            GLib.idle_add(process_existing_players)

            # Also check the playing state after a short delay to ensure consistency
            GLib.timeout_add(1000, self._check_and_update_playing_state)

            # Ensure the widget is always visible
            GLib.timeout_add(500, self._ensure_visibility)

        except Exception as e:
            logger.error(f"Failed to initialize PlayerBoxStack signals: {e}")

    def destroy(self):
        """Clean up resources when the widget is destroyed."""
        # Disconnect all signal connections
        for obj, handler_id in self._signal_connections:
            try:
                obj.disconnect(handler_id)
            except Exception as e:
                logger.warning(f"Failed to disconnect signal: {e}")
        self._signal_connections.clear()

        # Clean up player buttons
        for button in self.player_buttons:
            try:
                button.destroy()
            except Exception:
                pass
        self.player_buttons.clear()

        # Clean up player boxes
        for child in self.player_stack.get_children():
            if hasattr(child, "destroy") and child != self.no_media_box:
                try:
                    child.destroy()
                except Exception:
                    pass

        # Clean up shared MPRIS manager if this is the last instance
        if (
            hasattr(self, "mpris_manager")
            and self.mpris_manager == _shared_mpris_manager
        ):
            # Only cleanup if no other widgets are using it
            cleanup_shared_mpris_manager()

        super().destroy()

    def _periodic_cleanup(self):
        """Enhanced cleanup for reuse - clean internal state and free memory"""
        try:
            # Destroy all player boxes properly to free their resources
            current_children = list(self.player_stack.get_children())
            for child in current_children:
                if hasattr(child, "destroy") and child != self.no_media_box:
                    try:
                        child.destroy()
                    except Exception as e:
                        logger.warning(f"Failed to destroy player child: {e}")

            # Reset to no media state
            self.player_stack.children = [self.no_media_box]

            # Clear player buttons
            for button in self.player_buttons:
                try:
                    button.destroy()
                except Exception:
                    pass
            self.player_buttons.clear()

            # Reset stack position
            self.current_stack_pos = 0

            # Clean up old cache files more aggressively
            cleanup_old_cache_files()

        except Exception as e:
            logger.warning(f"PlayerBoxStack enhanced cleanup failed: {e}")

    def _create_no_media_box(self):
        """Create a placeholder box for when no media is playing."""
        fallback_cover_path = get_relative_path("../../assets/icons/music.svg")

        # Album cover with fallback image
        album_cover = Box(style_classes="album-image-c")
        album_cover.set_style(f"background-image:url('{fallback_cover_path}')")

        image_stack = Box(h_align="start", v_align="center", name="player-image-stack")
        image_stack.children = [album_cover]

        # Track info showing "No media playing"
        track_title = Label(
            label="No media playing",
            name="player-title-c",
            justification="left",
            max_chars_width=25,
            ellipsization="end",
            h_align="start",
        )

        track_artist = Label(
            label="",
            name="player-artist-c",
            justification="left",
            max_chars_width=15,
            ellipsization="end",
            h_align="start",
            visible=False,  # Hide artist and album when no media
        )

        track_info = Box(
            name="track-info",
            # spacing=5,
            h_expand=True,
            orientation="v",
            v_align="start",
            h_align="start",
            children=[track_title, track_artist],
        )

        # No control buttons for no media state - just an empty box
        controls_box = Box(
            name="player-controls",
            visible=False,  # Hide controls when no media
        )

        player_info_box = Box(
            name="player-info-box-c",
            h_expand=True,
            v_align="center",
            h_align="center",
            orientation="v",
            children=[track_info, controls_box],
        )

        inner_box = CenterBox(
            name="inner-player-box",
            start_children=[
                image_stack,
            ],
            center_children=[
                player_info_box,
            ],
        )
        # resize the inner box
        outer_box = Box(
            spacing=5,
            name="outer-no-player-box-c",
            h_expand=True,
            h_align="fill",
            # children=[
            v_expand=True,
            children=inner_box,
            # inner_box,
            # player_info_box,
            # image,
            # ],
        )

        box = Box(
            name="box-c",
            orientation="h",
            v_expand=True,
            h_align="fill",
            h_expand=True,
            children=[
                outer_box,
            ],
        )
        no_media_box = Box(
            h_align="center",
            name="player-box",
            h_expand=True,
            children=[box],
        )

        return no_media_box

    def _find_playing_player_index(self):
        """Find the index of the currently playing player."""
        players: List[PlayerBox] = self.player_stack.get_children()
        for i, player_box in enumerate(players):
            if (
                hasattr(player_box, "player")
                and str(player_box.player.playback_status).lower() == "playing"
            ):
                return i
        return None

    def _switch_to_playing_player(self):
        """Switch to the currently playing player if one exists."""
        playing_index = self._find_playing_player_index()
        if playing_index is not None and playing_index != self.current_stack_pos:
            self.on_player_clicked_by_index(playing_index)

    def _check_and_update_playing_state(self):
        """Check if any players are playing and update the display accordingly."""
        players: List[PlayerBox] = self.player_stack.get_children()
        has_playing_player = False

        # Check if any player is currently playing
        for player_box in players:
            if (
                hasattr(player_box, "player")
                and str(player_box.player.playback_status).lower() == "playing"
            ):
                has_playing_player = True
                break

        # If no players are playing, show the no media box
        if not has_playing_player:
            # Check if we already have the no media box visible
            current_children = self.player_stack.get_children()
            if len(current_children) == 1 and current_children[0] == self.no_media_box:
                # Already showing no media, no need to change
                return

            # Hide all player boxes and show no media
            for player_box in players:
                if hasattr(player_box, "destroy"):
                    try:
                        player_box.destroy()
                    except Exception as e:
                        logger.warning(f"Failed to destroy player box: {e}")

            # Clear player buttons
            self.player_buttons.clear()

            # Show the no media box
            self.player_stack.children = [self.no_media_box]
            self.current_stack_pos = 0

            # Ensure the widget is visible
            self.set_visible(True)
            self.player_stack.set_visible_child(self.no_media_box)

            logger.debug(
                "[PlayerBoxStack] No players playing, showing 'No media playing'"
            )

    def _ensure_visibility(self):
        """Ensure the widget is always visible and showing appropriate content."""
        try:
            # Always ensure the widget is visible
            self.set_visible(True)

            # Check current state
            current_children = self.player_stack.get_children()

            # If no children, show no media box
            if len(current_children) == 0:
                self.player_stack.children = [self.no_media_box]
                self.current_stack_pos = 0
                logger.debug("[PlayerBoxStack] No children found, showing no media box")

            # If only no_media_box is visible, ensure it's the active child
            elif (
                len(current_children) == 1 and current_children[0] == self.no_media_box
            ):
                self.player_stack.set_visible_child(self.no_media_box)
                logger.debug("[PlayerBoxStack] Ensuring no media box is visible")

            # Force the widget to be visible and show content
            self.set_visible(True)
            self.player_stack.set_visible(True)

            # If we have the no media box, make sure it's visible
            if self.no_media_box in current_children:
                self.no_media_box.set_visible(True)

            logger.debug(
                f"[PlayerBoxStack] Current state: {len(current_children)} children, visible: {self.get_visible()}, stack_visible: {self.player_stack.get_visible()}"
            )

        except Exception as e:
            logger.error(f"[PlayerBoxStack] Error in _ensure_visibility: {e}")

    def on_player_playback_changed(self, player_box, status):
        """Called when a player's playback status changes."""
        status = str(status).lower() if isinstance(status, str) else status
        if status == "playing":
            # Find this player's index and switch to it
            players: List[PlayerBox] = self.player_stack.get_children()
            for i, pb in enumerate(players):
                if pb == player_box:
                    if i != self.current_stack_pos:
                        self.on_player_clicked_by_index(i)
                    break
        elif status in ["paused", "stopped"]:
            # Check if any other players are playing
            self._check_and_update_playing_state()

    def on_player_clicked(self, type):
        # unset active from prev active button
        if self.player_buttons and self.current_stack_pos < len(self.player_buttons):
            self.player_buttons[self.current_stack_pos].remove_style_class("active")

        if type == "next":
            self.current_stack_pos = (
                self.current_stack_pos + 1
                if self.current_stack_pos != len(self.player_stack.get_children()) - 1
                else 0
            )
        elif type == "prev":
            self.current_stack_pos = (
                self.current_stack_pos - 1
                if self.current_stack_pos != 0
                else len(self.player_stack.get_children()) - 1
            )

        # set new active button
        if self.player_buttons and self.current_stack_pos < len(self.player_buttons):
            self.player_buttons[self.current_stack_pos].add_style_class("active")
            self.player_stack.set_visible_child(
                self.player_stack.get_children()[self.current_stack_pos],
            )

    def on_player_clicked_by_index(self, index):
        """Switch to player at given index"""
        if 0 <= index < len(self.player_buttons):
            # unset active from prev active button
            if self.player_buttons and self.current_stack_pos < len(
                self.player_buttons
            ):
                self.player_buttons[self.current_stack_pos].remove_style_class("active")
            # set new position
            self.current_stack_pos = index
            # set new active button
            if self.player_buttons and self.current_stack_pos < len(
                self.player_buttons
            ):
                self.player_buttons[self.current_stack_pos].add_style_class("active")
                self.player_stack.set_visible_child(
                    self.player_stack.get_children()[self.current_stack_pos],
                )
            # Update all player boxes with new button state
            self._update_all_player_buttons()

    def on_new_player(self, mpris_manager, player):

        # if player_name in self.config.get("ignore", []):
        #     return

        # Show all players, but we'll handle their playback status in the UI
        # if player.playback_status != "playing":
        #     logger.debug(f"[PlayerBoxStack] Player {player_name} is not playing (status: {player.playback_status}), skipping display")
        #     return

        # Remove the no media box if it's the only child
        if (
            len(self.player_stack.get_children()) == 1
            and self.player_stack.get_children()[0] == self.no_media_box
        ):
            self.player_stack.children = []
            self.current_stack_pos = 0

        self.set_visible(True)

        new_player_box = PlayerBox(
            player=player,
            player_stack=self,
            control_center=self.control_center,
        )
        self.player_stack.children = [
            *self.player_stack.children,
            new_player_box,
        ]

        self.make_new_player_button(self.player_stack.get_children()[-1])
        if self.player_buttons and self.current_stack_pos < len(self.player_buttons):
            self.player_buttons[self.current_stack_pos].set_style_classes(["active"])

        # Update all player boxes with current button state
        self._update_all_player_buttons()

        # Check if this new player is playing and switch to it
        self._switch_to_playing_player()

    def on_lost_player(self, mpris_manager, bus_name):
        # the playerBox is automatically removed from mprisbox children on being removed
        players: List[PlayerBox] = self.player_stack.get_children()

        # Find and properly destroy the player box
        player_box_to_remove = None
        for player_box in players:
            if (
                hasattr(player_box, "player")
                and getattr(player_box.player, "bus_name", None) == bus_name
            ):
                player_box_to_remove = player_box
                break

        if player_box_to_remove:
            try:
                player_box_to_remove.destroy()
            except Exception as e:
                logger.warning(f"Failed to destroy player box: {e}")

        # Check if this was the last player
        remaining_players = [
            p for p in self.player_stack.get_children() if p != player_box_to_remove
        ]
        if len(remaining_players) == 0:
            # Show the no media box instead of hiding
            self.player_stack.children = [self.no_media_box]
            self.current_stack_pos = 0
            self.player_buttons = []  # Clear player buttons
            return

        # Adjust current position if needed
        if self.current_stack_pos >= len(self.player_stack.get_children()):
            self.current_stack_pos = max(0, len(self.player_stack.get_children()) - 1)

        # Set active button if we have buttons and a valid position
        if self.player_buttons and self.current_stack_pos < len(self.player_buttons):
            self.player_buttons[self.current_stack_pos].set_style_classes(["active"])
            if self.player_stack.get_children():
                self.player_stack.set_visible_child(
                    self.player_stack.get_children()[self.current_stack_pos],
                )

        # Update all player boxes with current button state
        self._update_all_player_buttons()

        # After a player is removed, check if we should switch to a playing player
        self._switch_to_playing_player()

    def make_new_player_button(self, player_box):
        new_button = Button(name="player-stack-button")

        def on_player_button_click(button: Button):
            if self.player_buttons and self.current_stack_pos < len(
                self.player_buttons
            ):
                self.player_buttons[self.current_stack_pos].remove_style_class("active")
            if button in self.player_buttons:
                self.current_stack_pos = self.player_buttons.index(button)
                button.add_style_class("active")
                self.player_stack.set_visible_child(player_box)

        new_button.connect(
            "clicked",
            on_player_button_click,
        )
        self.player_buttons.append(new_button)

        # This will automatically destroy our used button
        def cleanup_button(*_):
            try:
                if new_button in self.player_buttons:
                    self.player_buttons.remove(new_button)
                new_button.destroy()
            except Exception as e:
                logger.warning(f"Failed to cleanup button: {e}")

        player_box.connect("destroy", cleanup_button)

    def _update_all_player_buttons(self):
        """Update all player boxes with the current button state"""
        players: List[PlayerBox] = self.player_stack.get_children()

        for player_box in players:
            if hasattr(player_box, "update_buttons"):
                player_box.update_buttons(self.player_buttons, len(players) > 1)
            else:
                logger.warning(
                    "[PlayerBoxStack] PlayerBox missing update_buttons method"
                )


class PlayerBox(Box):
    """A widget that displays the current player information."""

    def __init__(
        self, player: MprisPlayer, player_stack=None, control_center=None, **kwargs
    ):
        super().__init__(
            h_align="center",
            name="player-box",
            **kwargs,
            h_expand=True,
        )
        # Setup
        self.player: MprisPlayer = player
        self.player_stack = player_stack
        self.control_center = control_center
        self.cover_path = get_relative_path("../../assets/icons/music.svg")

        # Add controls_box attribute early for compatibility
        # Temporary placeholder
        self.controls_box = Box(name="temp-controls-box")

        self.image_size = 50
        self.icon_size = 15

        # State
        self.exit = False
        self.skipped = False
        self._signal_connections = []  # Track signal connections

        # Memory management
        self.temp_artwork_files = []  # Track temp files for cleanup
        self._download_cancelled = False  # Flag to cancel downloads

        # Album art with existing Box widget
        self.album_cover = Box(style_classes="album-image-c")
        self.album_cover.set_style(f"background-image:url('{self.cover_path}')")

        self.image_stack = Box(
            h_align="start",
            v_align="center",
            name="player-image-stack",
        )
        self.image_stack.children = [self.album_cover]

        # Connect to arturl changes
        self.player.connect("notify::arturl", self.set_image)

        self.app_icon = Box(
            children=Image(
                icon_name=self.player.player_name, name="player-app-icon", icon_size=20
            ),
            h_align="end",
            v_align="end",
            tooltip_text=self.player.player_name,  # type: ignore
        )
        self.image = Overlay(
            child=self.image_stack,
            overlays=[
                self.app_icon,
            ],
        )

        # Track Info

        self.track_title = Label(
            label="No Title",
            name="player-title-c",
            justification="left",
            max_chars_width=25,
            ellipsization="end",
            h_align="start",
        )

        self.track_artist = Label(
            label="No Artist",
            name="player-artist-c",
            justification="left",
            max_chars_width=23,
            ellipsization="end",
            h_align="start",
            visible=True,
        )

        self.player.bind_property(
            "title",
            self.track_title,
            "label",
            GObject.BindingFlags.DEFAULT,
            lambda _, x: (
                re.sub(r"\r?\n", " ", x) if x != "" and x is not None else "No Title"
            ),  # type: ignore
        )
        self.player.bind_property(
            "artist",
            self.track_artist,
            "label",
            GObject.BindingFlags.DEFAULT,
            lambda _, x: ", ".join(x) if x and isinstance(x, list) else "No Artist",  # type: ignore
        )

        self.track_info = Box(
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

        # Buttons with fixed sizing for layout stability
        self.button_box = Box(
            name="button-box-c",
            h_expand=False,
            spacing=2,
        )

        # Create SVG icons with consistent sizing
        self.skip_next_icon = svg_file("player/fwd.svg", size=22)
        self.play_pause_icon = svg_file("player/Pause.svg", size=22)

        # Fixed size buttons to prevent layout shifts
        self.play_pause_button = Button(
            name="player-button",
            child=self.play_pause_icon,
            on_clicked=self.player.play_pause,
        )
        # Set consistent button size

        self.player.bind_property("can_pause", self.play_pause_button, "sensitive")

        self.next_button = Button(
            name="player-button",
            child=self.skip_next_icon,
            on_clicked=self._on_player_next,
        )
        # Set consistent button size
        # self.next_button.set_size_request(32, 32)
        self.player.bind_property("can_go_next", self.next_button, "sensitive")

        self.button_box.children = (
            self.play_pause_button,
            self.next_button,
        )

        # Assign button_box to controls_box for compatibility
        self.controls_box = self.button_box

        self.player_info_box = Box(
            name="player-info-box-c",
            v_align="center",
            h_expand=True,
            h_align="start",
            orientation="v",
            children=[
                self.track_info,
            ],
        )

        self.inner_box = Box(
            name="inner-player-box",
            h_expand=True,
            v_align="center",
            h_align="start",
            children=[
                self.image,
                self.player_info_box,
            ],
        )
        # resize the inner box
        self.outer_box = Button(
            spacing=5,
            name="outer-player-box-c",
            h_expand=True,
            on_clicked=self._on_outer_box_clicked,
            h_align="start",
            child=self.inner_box,
        )

        self.box = CenterBox(
            name="box-c",
            orientation="h",
            h_align="center",
            start_children=[
                self.outer_box,
            ],
            end_children=[
                self.button_box,
            ],
        )
        self.box.set_size_request(352, -1)

        self.children = [
            *self.children,
            self.box,
        ]

        # Track signal connections for cleanup - store (object, handler_id) tuples
        connections = bulk_connect(
            self.player,
            {
                "closed": self._on_player_exit,
                "notify::playback-status": self._on_playback_change,
                "notify::metadata": self._on_metadata,
            },
        )
        # Store as (object, handler_id) tuples
        for handler_id in connections:
            self._signal_connections.append((self.player, handler_id))

    def destroy(self):
        """Clean up all resources when the widget is destroyed."""
        # Cancel any ongoing downloads
        self._download_cancelled = True

        # Disconnect all signal connections
        for obj, handler_id in self._signal_connections:
            try:
                obj.disconnect(handler_id)
            except Exception as e:
                logger.warning(f"Failed to disconnect signal: {e}")
        self._signal_connections.clear()

        # Clean up temp files
        self._cleanup_temp_files()

        super().destroy()

    def __del__(self):
        """Ensure cleanup happens even if player exits unexpectedly."""
        try:
            self._cleanup_temp_files()
        except Exception:
            pass  # Ignore errors during cleanup in destructor

    def _on_prev_button_click(self, *_):
        """Handle prev button click: open expanded player in control center"""
        try:
            # Open expanded player in control center instead of new window
            if self.control_center and hasattr(
                self.control_center, "open_expanded_player"
            ):
                self.control_center.open_expanded_player()
        except Exception as e:
            logger.warning(f"Failed to handle prev button click: {e}")

    def _on_outer_box_clicked(self, *_):
        """Handle outer box click with proper error handling."""
        try:
            # Open expanded player in control center instead of new window
            if self.control_center and hasattr(
                self.control_center, "open_expanded_player"
            ):
                self.control_center.open_expanded_player()
        except Exception as e:
            logger.warning(f"Failed to handle outer box click: {e}")

    def update_buttons(self, player_buttons, show_buttons):
        # """Update the stack switcher buttons in this player box"""
        pass

    def _on_metadata(self, *_):
        self.set_image()

    def _cleanup_temp_files(self):
        """Clean up temporary artwork files."""
        for temp_file in self.temp_artwork_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")
        self.temp_artwork_files.clear()

    def _on_player_exit(self, _, value):
        self.exit = value
        self._cleanup_temp_files()  # Clean up temp files before destroying
        self.destroy()

    def _on_player_next(self, *_):
        self.player.next()

    def _on_player_prev(self, *_):
        self.player.previous()

    def _on_playback_change(self, player, status):
        status = player.get_property("playback-status")
        status_l = str(status).lower() if isinstance(status, str) else status

        if status_l == "paused":
            self.play_pause_icon.dynamic_file("player/play.svg")

        if status_l == "playing":
            self.play_pause_icon.dynamic_file("player/Pause.svg")

        # Always notify the player stack about playback status changes
        if self.player_stack and hasattr(
            self.player_stack, "on_player_playback_changed"
        ):
            self.player_stack.on_player_playback_changed(self, status_l)

    def img_callback(self, source: Gio.File, result: Gio.AsyncResult):
        try:
            if os.path.isfile(self.cover_path):
                self.update_image()
        except ValueError:
            logger.error("[PLAYER] Failed to grab artUrl")

    def update_image(self):
        self.album_cover.set_style(f"background-image:url('{self.cover_path}')")

    def set_image(self, *args):
        url = self.player.arturl

        if url is None or url == "":
            return

        new_cover_path = (
            (
                MEDIA_CACHE
                + "/"
                # type: ignore
                + GLib.compute_checksum_for_string(GLib.ChecksumType.SHA1, url, -1)
            )
            if "file://" != url[0:7]
            else url[7:]
        )

        if new_cover_path == self.cover_path:
            self.update_image()
            return

        self.cover_path = new_cover_path

        if os.path.exists(self.cover_path):
            self.update_image()
            return

        Gio.File.new_for_uri(uri=url).copy_async(
            Gio.File.new_for_path(self.cover_path),
            Gio.FileCopyFlags.OVERWRITE,
            GLib.PRIORITY_DEFAULT,
            None,
            None,
            self.img_callback,
        )

    def close_bluetooth(self, *args):
        """Placeholder method for compatibility"""
        pass
