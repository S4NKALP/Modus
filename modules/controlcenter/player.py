import os
import re
import tempfile
import urllib.parse
import urllib.request
from typing import List
import threading
import weakref

from fabric.utils import (
    bulk_connect,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from modules.controlcenter.expanded_player import ExpandedPlayer
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.stack import Stack
from gi.repository import GLib, GObject
from loguru import logger

from services.mpris import MprisPlayer, MprisPlayerManager
import config.data as data
from widgets.mousecapture import DropDownMouseCapture

CACHE_DIR = f"{data.CACHE_DIR}/media"


def cleanup_old_cache_files():
    """Clean up old artwork cache files (older than 1 day)."""
    try:
        if not os.path.exists(CACHE_DIR):
            return

        import time

        current_time = time.time()
        one_day_ago = current_time - (24 * 60 * 60)  # 24 hours

        for filename in os.listdir(CACHE_DIR):
            filepath = os.path.join(CACHE_DIR, filename)
            try:
                if os.path.isfile(filepath):
                    file_mtime = os.path.getmtime(filepath)
                    if file_mtime < one_day_ago:
                        os.unlink(filepath)
            except Exception:
                pass  # Ignore individual file errors
    except Exception:
        pass  # Ignore all errors in cleanup


class PlayerBoxStack(Box):
    """A widget that displays the current player information."""

    def __init__(
        self, mpris_manager: MprisPlayerManager, control_center=None, **kwargs
    ):
        # Clean up old cache files on startup
        cleanup_old_cache_files()

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

        self.mpris_manager = mpris_manager

        # Track connections for cleanup
        connections = bulk_connect(
            self.mpris_manager,
            {
                "player-appeared": self.on_new_player,
                "player-vanished": self.on_lost_player,
            },
        )
        self._signal_connections.extend(connections)

        for player in self.mpris_manager.players:  # type: ignore
            logger.info(
                f"[PLAYER MANAGER] player found: {player.get_property('player-name')}",
            )
            self.on_new_player(self.mpris_manager, player)

    def destroy(self):
        """Clean up resources when the widget is destroyed."""
        # Disconnect all signal connections
        for connection in self._signal_connections:
            try:
                connection.disconnect()
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
            if hasattr(child, 'destroy') and child != self.no_media_box:
                try:
                    child.destroy()
                except Exception:
                    pass
        
        super().destroy()

    def _create_no_media_box(self):
        """Create a placeholder box for when no media is playing."""
        fallback_cover_path = f"{data.HOME_DIR}/.current.wall"

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
            max_chars_width=15,
            ellipsization="end",
            h_align="start",
        )

        track_artist = Label(
            label="",
            name="player-artist",
            justification="left",
            max_chars_width=15,
            ellipsization="end",
            h_align="start",
            visible=False,  # Hide artist and album when no media
        )

        track_album = Label(
            label="",
            name="player-album",
            justification="left",
            max_chars_width=15,
            ellipsization="end",
            h_align="start",
            visible=False,  # Hide artist and album when no media
        )

        track_info = Box(
            name="track-info",
            # spacing=5,
            orientation="v",
            v_align="start",
            h_align="start",
            children=[track_title, track_artist, track_album],
        )

        # No control buttons for no media state - just an empty box
        controls_box = Box(
            name="player-controls",
            visible=False,  # Hide controls when no media
        )

        player_info_box = Box(
            name="player-info-box",
            v_align="center",
            h_align="start",
            orientation="v",
            children=[track_info, controls_box],
        )

        inner_box = Box(
            name="inner-player-box",
            v_align="center",
            h_align="start",
        )

        outer_box = Box(
            name="outer-player-box",
            h_align="start",
        )

        overlay_box = Overlay(
            child=outer_box,
            overlays=[
                inner_box,
                player_info_box,
                image_stack,
            ],
        )

        no_media_box = Box(
            h_align="center",
            name="player-box",
            h_expand=True,
            children=[overlay_box],
        )

        return no_media_box

    def _find_playing_player_index(self):
        """Find the index of the currently playing player."""
        players: List[PlayerBox] = self.player_stack.get_children()
        for i, player_box in enumerate(players):
            if (
                hasattr(player_box, "player")
                and player_box.player.playback_status == "playing"
            ):
                return i
        return None

    def _switch_to_playing_player(self):
        """Switch to the currently playing player if one exists."""
        playing_index = self._find_playing_player_index()
        if playing_index is not None and playing_index != self.current_stack_pos:
            logger.info(
                f"[PlayerBoxStack] Auto-switching to playing player at index {playing_index}"
            )
            self.on_player_clicked_by_index(playing_index)

    def on_player_playback_changed(self, player_box, status):
        """Called when a player's playback status changes."""
        if status == "playing":
            # Find this player's index and switch to it
            players: List[PlayerBox] = self.player_stack.get_children()
            for i, pb in enumerate(players):
                if pb == player_box:
                    if i != self.current_stack_pos:
                        logger.info(
                            f"[PlayerBoxStack] Switching to playing player: {player_box.player.player_name}"
                        )
                        self.on_player_clicked_by_index(i)
                    break

    def on_player_clicked(self, type):
        # unset active from prev active button
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
        print(f"[PlayerBoxStack] Switching to player at index {self.current_stack_pos}")
        self.player_buttons[self.current_stack_pos].add_style_class("active")
        self.player_stack.set_visible_child(
            self.player_stack.get_children()[self.current_stack_pos],
        )

    def on_player_clicked_by_index(self, index):
        """Switch to player at given index"""
        if 0 <= index < len(self.player_buttons):
            # unset active from prev active button
            self.player_buttons[self.current_stack_pos].remove_style_class("active")
            # set new position
            self.current_stack_pos = index
            # set new active button
            self.player_buttons[self.current_stack_pos].add_style_class("active")
            self.player_stack.set_visible_child(
                self.player_stack.get_children()[self.current_stack_pos],
            )
            # Update all player boxes with new button state
            self._update_all_player_buttons()

    def on_new_player(self, mpris_manager, player):
        player_name = player.props.player_name

        # if player_name in self.config.get("ignore", []):
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
            player=MprisPlayer(player),
            player_stack=self,
            control_center=self.control_center,
        )
        self.player_stack.children = [
            *self.player_stack.children,
            new_player_box,
        ]

        self.make_new_player_button(self.player_stack.get_children()[-1])
        logger.info(
            f"[PLAYER MANAGER] adding new player: {player.get_property('player-name')}",
        )
        if self.player_buttons:
            self.player_buttons[self.current_stack_pos].set_style_classes(["active"])

        # Update all player boxes with current button state
        self._update_all_player_buttons()

        # Check if this new player is playing and switch to it
        self._switch_to_playing_player()

    def on_lost_player(self, mpris_manager, player_name):
        # the playerBox is automatically removed from mprisbox children on being removed
        logger.info(f"[PLAYER_MANAGER] Player Removed {player_name}")
        players: List[PlayerBox] = self.player_stack.get_children()

        # Find and properly destroy the player box
        player_box_to_remove = None
        for player_box in players:
            if hasattr(player_box, 'player') and player_box.player.player_name == player_name:
                player_box_to_remove = player_box
                break

        if player_box_to_remove:
            try:
                player_box_to_remove.destroy()
            except Exception as e:
                logger.warning(f"Failed to destroy player box: {e}")

        # Check if this was the last player
        remaining_players = [p for p in self.player_stack.get_children() if p != player_box_to_remove]
        if len(remaining_players) == 0:
            # Show the no media box instead of hiding
            self.player_stack.children = [self.no_media_box]
            self.current_stack_pos = 0
            self.player_buttons = []  # Clear player buttons
            return

        if (
            players
            and self.current_stack_pos < len(players)
            and hasattr(players[self.current_stack_pos], 'player')
            and players[self.current_stack_pos].player.player_name == player_name
        ):
            self.current_stack_pos = max(0, self.current_stack_pos - 1)
            if self.player_stack.get_children():
                self.player_stack.set_visible_child(
                    self.player_stack.get_children()[self.current_stack_pos],
                )

        if self.player_buttons and self.current_stack_pos < len(self.player_buttons):
            self.player_buttons[self.current_stack_pos].set_style_classes(["active"])

        # Update all player boxes with current button state
        self._update_all_player_buttons()

        # After a player is removed, check if we should switch to a playing player
        self._switch_to_playing_player()

    def make_new_player_button(self, player_box):
        new_button = Button(name="player-stack-button")

        def on_player_button_click(button: Button):
            self.player_buttons[self.current_stack_pos].remove_style_class("active")
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
        logger.info(
            f"[PlayerBoxStack] Updating buttons for {len(players)} players, {
                len(self.player_buttons)
            } buttons"
        )
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
        self.fallback_cover_path = f"{data.HOME_DIR}/.current.wall"

        self.expanded_player = ExpandedPlayer()
        self.ex_mousecapture = DropDownMouseCapture(
            layer="top", child_window=self.expanded_player
        )
        self.image_size = 50

        self.icon_size = 15

        # State
        self.exit = False
        self.skipped = False

        # Memory management
        self.temp_artwork_files = []  # Track temp files for cleanup
        self.current_download_thread = None  # Track current download thread
        self._download_cancelled = False  # Flag to cancel downloads
        self._signal_connections = []  # Track signal connections

        self.album_cover = Box(style_classes="album-image-c")
        self.album_cover.set_style(
            f"background-image:url('{self.fallback_cover_path}')"
        )

        self.image_stack = Box(
            h_align="start",
            v_align="center",
            name="player-image-stack",
        )
        self.image_stack.children = [*self.image_stack.children, self.album_cover]

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
            max_chars_width=15,
            ellipsization="end",
            h_align="start",
        )

        self.track_artist = Label(
            label="No Artist",
            name="player-artist-c",
            justification="left",
            max_chars_width=15,
            ellipsization="end",
            h_align="start",
            visible=True,
        )

        self.track_album = Label(
            label="No Album",
            name="player-album",
            justification="left",
            max_chars_width=15,
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
            lambda _, x: (
                re.sub(r"\r?\n", " ", x) if x != "" and x is not None else "No Artist"
            ),  # type: ignore
        )

        self.player.bind_property(
            "album",
            self.track_album,
            "label",
            GObject.BindingFlags.DEFAULT,
            lambda _, x: (
                re.sub(r"\r?\n", " ", x) if x != "" and x is not None else "No Album"
            ),  # type: ignore
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
                # self.track_album,
            ],
        )

        # Buttons
        self.button_box = Box(
            name="button-box-c",
            # h_align="end",
            # visible=False,
            h_expand=False,
            spacing=2,
        )

        self.skip_next_icon = Image(icon_name="player_fwd")
        self.skip_prev_icon = Image(icon_name="media-skip-backward")
        self.shuffle_icon = Image(icon_name="shuffle")
        self.play_pause_icon = Image(icon_name="player_pause")

        self.play_pause_button = Button(
            name="player-button",
            child=self.play_pause_icon,
            on_clicked=self.player.play_pause,
        )

        self.player.bind_property("can_pause", self.play_pause_button, "sensitive")

        self.next_button = Button(
            style_classes=["player-button"],
            child=self.skip_next_icon,
            on_clicked=self._on_player_next,
        )
        self.player.bind_property("can_go_next", self.next_button, "sensitive")

        self.prev_button = Button(
            style_classes=["player-button"],
            child=self.skip_prev_icon,
            on_clicked=self._on_prev_button_click,
        )
        self.shuffle_button = Button(
            style_classes=["player-button"],
            child=self.shuffle_icon,
            on_clicked=self.player.toggle_shuffle,
        )
        self.player.bind_property("can_shuffle", self.shuffle_button, "sensitive")

        self.button_box.children = (
            # self.shuffle_button,
            # self.prev_button,
            self.play_pause_button,
            self.next_button,
        )
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
            # style="background-color:#fff",
            on_clicked=lambda *_: (
                # Close control center if it exists
                self.control_center.hide_controlcenter(),
                self.expanded_player.set_visible(True),
                self.ex_mousecapture.toggle_mousecapture(),
            ),
            h_align="start",
            # children=[
            child=self.inner_box,
            # self.inner_box,
            # self.player_info_box,
            # self.image,
            # ],
        )

        self.box = Box(
            name="box-c",
            orientation="h",
            h_align="center",
            h_expand=True,
            children=[
                self.outer_box,
                self.button_box,
                # self.stack_buttons_box,
            ],
        )

        self.children = [
            *self.children,
            self.box,
        ]

        # Track signal connections for cleanup
        connections = bulk_connect(
            self.player,
            {
                "exit": self._on_player_exit,
                "notify::playback-status": self._on_playback_change,
                "notify::shuffle": self._on_shuffle_update,
                "notify::metadata": self._on_metadata,
            },
        )
        self._signal_connections.extend(connections)

    def destroy(self):
        """Clean up all resources when the widget is destroyed."""
        # Cancel any ongoing downloads
        self._download_cancelled = True
        
        # Disconnect all signal connections
        for connection in self._signal_connections:
            try:
                connection.disconnect()
            except Exception as e:
                logger.warning(f"Failed to disconnect signal: {e}")
        self._signal_connections.clear()
        
        # Clean up temp files
        self._cleanup_temp_files()
        
        # Clean up UI components
        try:
            if hasattr(self, 'ex_mousecapture'):
                self.ex_mousecapture.destroy()
            if hasattr(self, 'expanded_player'):
                self.expanded_player.destroy()
        except Exception as e:
            logger.warning(f"Failed to cleanup UI components: {e}")
        
        super().destroy()

    def __del__(self):
        """Ensure cleanup happens even if player exits unexpectedly."""
        try:
            self._cleanup_temp_files()
        except Exception:
            pass  # Ignore errors during cleanup in destructor

    def _on_prev_button_click(self, *_):
        """Handle prev button click: close control center then open expanded player"""
        # Close control center first
        if self.control_center and hasattr(self.control_center, "hide_controlcenter"):
            self.control_center.hide_controlcenter()

        # Then open expanded player
        self.expanded_player.set_visible(True)
        self.ex_mousecapture.toggle_mousecapture()

    def update_buttons(self, player_buttons, show_buttons):
        # """Update the stack switcher buttons in this player box"""
        pass

    def _on_metadata(self, *_):
        self._set_image()

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

    def _on_shuffle_update(self, *_):
        if self.player.shuffle is None:
            return
        if self.player.shuffle is True:
            self.shuffle_icon.style_classes = []
            self.shuffle_icon.add_style_class("shuffle-on")
        else:
            self.shuffle_icon.style_classes = []
            self.shuffle_icon.add_style_class("shuffle-off")

    def play_pause(self, player, status):
        status = player.get_property("playback-status")

        if status == "paused":
            self.play_pause_icon.set_from_icon_name("player_play")

        if status == "playing":
            self.play_pause_icon.set_from_icon_name("player_pause")
            # Notify the player stack that this player started playing
            if self.player_stack and hasattr(
                self.player_stack, "on_player_playback_changed"
            ):
                self.player_stack.on_player_playback_changed(self, status)

    def _on_playback_change(self, player, status):
        status = player.get_property("playback-status")

        if status == "paused":
            self.play_pause_icon.set_from_icon_name("player_play")

        if status == "playing":
            self.play_pause_icon.set_from_icon_name("player_pause")
            # Notify the player stack that this player started playing
            if self.player_stack and hasattr(
                self.player_stack, "on_player_playback_changed"
            ):
                self.player_stack.on_player_playback_changed(self, status)

    def _update_image(self, image_path):
        if image_path and os.path.isfile(image_path):
            self.album_cover.set_style(f"background-image:url('{image_path}')")
        else:
            self.album_cover.set_style(
                f"background-image:url('{self.fallback_cover_path}')"
            )

    def _set_image(self, *_):
        art_url = self.player.arturl

        parsed = urllib.parse.urlparse(art_url)
        if parsed.scheme == "file":
            local_arturl = urllib.parse.unquote(parsed.path)
            self._update_image(local_arturl)
        elif parsed.scheme in ("http", "https"):
            # Cancel any existing download to prevent memory buildup
            self._download_cancelled = True
            
            # Use threading.Thread instead of GLib.Thread for better control
            if self.current_download_thread and self.current_download_thread.is_alive():
                # Thread will check _download_cancelled flag and exit early
                pass
                
            self._download_cancelled = False
            self.current_download_thread = threading.Thread(
                target=self._download_and_set_artwork, 
                args=(art_url,),
                daemon=True  # Dies with main thread
            )
            self.current_download_thread.start()
        else:
            self._update_image(art_url)

    def _download_and_set_artwork(self, arturl):
        """
        Download the artwork from the given URL asynchronously and update the cover
        using GLib.idle_add to ensure UI updates occur on the main thread.
        """
        local_arturl = self.fallback_cover_path
        temp_file_path = None

        try:
            # Check if download was cancelled
            if self._download_cancelled:
                return

            # Clean up old temp files first (keep only last 2 to avoid excessive cleanup)
            if len(self.temp_artwork_files) > 2:
                old_files = self.temp_artwork_files[:-2]
                for old_file in old_files:
                    try:
                        if os.path.exists(old_file):
                            os.unlink(old_file)
                    except Exception:
                        pass
                self.temp_artwork_files = self.temp_artwork_files[-2:]

            # Check again if cancelled
            if self._download_cancelled:
                return

            # Download artwork
            parsed = urllib.parse.urlparse(arturl)
            suffix = os.path.splitext(parsed.path)[1] or ".png"

            with urllib.request.urlopen(arturl, timeout=10) as response:  # Add timeout
                if self._download_cancelled:
                    return
                data = response.read()

            # Check one more time if cancelled
            if self._download_cancelled:
                return

            # Create temp file in cache directory instead of system temp
            os.makedirs(CACHE_DIR, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, dir=CACHE_DIR
            ) as temp_file:
                temp_file.write(data)
                temp_file_path = temp_file.name
                local_arturl = temp_file_path

            # Track temp file for cleanup
            if temp_file_path and not self._download_cancelled:
                self.temp_artwork_files.append(temp_file_path)

        except Exception as e:
            if not self._download_cancelled:
                logger.warning(f"Failed to download artwork from {arturl}: {e}")
            # Clean up failed temp file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
            return

        # Only update UI if not cancelled
        if not self._download_cancelled:
            GLib.idle_add(self._update_image, local_arturl)

    def close_bluetooth(self, *args):
        """Close Bluetooth control center"""
        self.ex_mousecapture.hide_child_window()
