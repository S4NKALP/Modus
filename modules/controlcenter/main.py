# Standard library imports
import contextlib
import gc
import weakref
from pathlib import Path
from typing import Optional, Dict, Any

# Fabric imports
from fabric.core.service import Service, Signal, Property
from fabric.widgets.window import Window
from fabric.widgets.overlay import Overlay
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.revealer import Revealer
from fabric.utils import idle_add, get_relative_path, invoke_repeater
from fabric.widgets.image import Image

# Gi imports  
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gtk, GLib, Gdk

# Local imports
from modules.controlcenter.bluetooth import BluetoothConnections
from modules.controlcenter.wifi import WifiConnections
from modules.controlcenter.player import PlayerBoxStack
from modules.controlcenter.per_app_volume import PerAppVolumeControl
from modules.controlcenter.expanded_player import EmbeddedExpandedPlayer
from services.modus import modus_service
from widgets.wayland import WaylandWindow as Window
from loguru import logger

# Memory monitoring
from debug_memory import set_memory_baseline, log_memory
from fabric.utils import idle_add
from fabric.utils.helpers import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.svg import Svg
from widgets.wayland import WaylandWindow as Window

# Local imports
from modules.controlcenter.bluetooth import BluetoothConnections
from modules.controlcenter.wifi import WifiConnections
from services.brightness import Brightness
from utils.roam import audio_service, modus_service
from modules.controlcenter.player import PlayerBoxStack
from modules.controlcenter.per_app_volume import PerAppVolumeControl
from modules.controlcenter.expanded_player import EmbeddedExpandedPlayer, get_shared_mpris_manager
from services.mpris import MprisPlayerManager

brightness_service = Brightness.get_initial()

# Memory management globals
_widget_cache = weakref.WeakValueDictionary()
_cleanup_timer_id = None


class ModusControlCenter(Window):
    def __init__(self, **kwargs):
        super().__init__(
            layer="top",
            title="modus",
            anchor="top right",
            margin="2px 10px 0px 0px",
            exclusivity="auto",
            keyboard_mode="on-demand",
            name="control-center-menu",
            visible=False,
            **kwargs,
        )
        self.focus_mode = modus_service.dont_disturb
        self._updating_brightness = False
        self._updating_volume = False

        # Lazy loading flags
        self._music_initialized = False
        self._per_app_volume_initialized = False
        self._expanded_player_initialized = False

        # Store references for cleanup
        self._signal_connections = []
        self._music_widget_content = None
        self._per_app_volume_widget = None
        self._expanded_player_widget = None

        self.add_keybinding("Escape", self.hide_controlcenter)

        volume = 100
        wlan = modus_service.sc("wlan-changed", self.wlan_changed)
        bluetooth = modus_service.sc("bluetooth-changed", self.bluetooth_changed)
        music = modus_service.sc("music-changed", self.audio_changed)

        # Store signal connections for cleanup
        self._signal_connections.extend(
            [
                audio_service.connect("changed", self.audio_changed),
                audio_service.connect("changed", self.volume_changed),
                modus_service.connect("dont-disturb-changed", self.dnd_changed),
            ]
        )

        self.wlan_label = Label(wlan, name="wifi-widget-label", h_align="start")
        if bluetooth != "disabled":
            if bluetooth.startswith("connected:"):
                parts = bluetooth.split(":")
                bluetooth_display = parts[1] if len(parts) >= 2 else "Connected"
            else:
                bluetooth_display = "On"
        else:
            bluetooth_display = "Off"

        self.bluetooth_label = Label(
            bluetooth_display, name="bluetooth-widget-label", h_align="start"
        )
        self.volume_scale = Scale(
            value=volume,
            min_value=0,
            max_value=100,
            increments=(5, 5),
            name="volume-widget-slider",
            size=30,
            h_expand=True,
        )
        self.volume_scale.connect("change-value", self.set_volume)
        self.volume_scale.connect("scroll-event", self.on_volume_scroll)

        current_brightness = brightness_service.screen_brightness
        brightness_percentage = (
            int((current_brightness / brightness_service.max_screen) * 100)
            if brightness_service.max_screen > 0
            else 50
        )

        self.brightness_scale = Scale(
            value=brightness_percentage,
            min_value=0,
            max_value=100,
            increments=(5, 5),
            name="brightness-widget-slider",
            size=30,
            h_expand=True,
        )

        # Only connect brightness controls if brightness service is available
        if brightness_service.max_screen > 0:
            self.brightness_scale.connect("change-value", self.set_brightness)
            self.brightness_scale.connect("scroll-event", self.on_brightness_scroll)
            self._signal_connections.append(
                brightness_service.connect("screen", self.brightness_changed)
            )
        else:
            # Disable brightness scale if no backlight device available
            self.brightness_scale.set_sensitive(False)

        # Create placeholder music widget - lazy load content when needed
        self.music_widget = Box(
            name="music-widget", h_align="start", children=[]  # Empty initially
        )

        self.has_bluetooth_open = False
        self.has_wifi_open = False
        self.has_per_app_volume_open = False
        self.has_expanded_player_open = False

        self.bluetooth_svg = Svg(
            name="bluetooth-icon",
            svg_file=get_relative_path(
                "../../config/assets/icons/applets/bluetooth.svg"
                if bluetooth != "disabled"
                else "../../config/assets/icons/applets/bluetooth-off.svg"
            ),
            size=42,
        )
        self.wifi_svg = Svg(
            name="wifi-icon",
            svg_file=get_relative_path(
                "../../config/assets/icons/applets/wifi.svg"
                if wlan != "No Connection"
                else "../../config/assets/icons/applets/wifi-off.svg"
            ),
            size=46,
        )

        self.bluetooth_widget = Button(
            name="bluetooth-widget",
            child=Box(
                orientation="h",
                children=[
                    self.bluetooth_svg,
                    Box(
                        name="bluetooth-widget-info",
                        orientation="vertical",
                        children=[
                            Label(
                                name="bluetooth-widget-name",
                                label="Bluetooth",
                                style_classes="ct",
                                h_align="start",
                            ),
                            self.bluetooth_label,
                        ],
                    ),
                ],
            ),
            on_clicked=self.open_bluetooth,
        )

        self.wlan_widget = Button(
            name="wifi-widget",
            child=Box(
                orientation="h",
                children=[
                    self.wifi_svg,
                    Box(
                        name="wifi-widget-info",
                        orientation="vertical",
                        children=[
                            Label(
                                name="wifi-widget-name",
                                label="Wi-Fi",
                                style_classes="ct",
                                h_align="start",
                            ),
                            self.wlan_label,
                        ],
                    ),
                ],
            ),
            on_clicked=self.open_wifi,
        )

        self.focus_icon = Svg(
            name="focus-icon",
            svg_file=get_relative_path(
                "../../config/assets/icons/applets/dnd.svg"
                if self.focus_mode
                else "../../config/assets/icons/applets/dnd-off.svg"
            ),
            size=46,
        )

        self.focus_widget = Button(
            name="focus-widget",
            child=Box(
                orientation="h",
                children=[
                    self.focus_icon,
                    Label(label="Focus", style_classes="title ct", h_align="start"),
                ],
            ),
            on_clicked=self.set_dont_disturb,
        )

        # Create main widgets directly without XML
        self.widgets = Box(
            orientation="vertical",
            h_expand=True,
            name="control-center-widgets",
            children=[
                Box(
                    orientation="horizontal",
                    name="top-widget",
                    h_expand=True,
                    children=[
                        Box(
                            orientation="vertical",
                            name="wb-widget",
                            style_classes="menu",
                            spacing=5,
                            children=[
                                self.wlan_widget,
                                self.bluetooth_widget,
                            ],
                        ),
                        Box(
                            orientation="horizontal",
                            name="dnd-widget",
                            style_classes="menu",
                            h_expand=True,
                            children=[
                                self.focus_widget,
                            ],
                        ),
                    ],
                ),
                Box(
                    orientation="vertical",
                    name="brightness-widget",
                    style_classes="menu",
                    h_expand=True,
                    children=[
                        Label(label="Display", style_classes="title", h_align="start"),
                        self.brightness_scale,
                        Label(
                            label="󰖨 ", name="brightness-widget-icon", h_align="start"
                        ),
                    ],
                ),
                Box(
                    orientation="vertical",
                    name="volume-widget",
                    style_classes="menu",
                    h_expand=True,
                    children=[
                        Label(label="Sound", style_classes="title", h_align="start"),
                        Box(
                            orientation="horizontal",
                            spacing=8,
                            v_expand=True,
                            h_expand=True,
                            children=[
                                self.volume_scale,
                                Button(
                                    name="per-app-volume-button",
                                    child=Box(
                                        h_align="center",
                                        v_align="center",
                                        h_expand=True,
                                        size=(32, 32),
                                        v_expand=True,
                                        children=[
                                            Svg(
                                                svg_file=get_relative_path(
                                                    "../../config/assets/icons/player/audio-switcher.svg"
                                                ),
                                                size=34,
                                            )
                                        ],
                                    ),
                                    on_clicked=self.open_per_app_volume,
                                ),
                            ],
                        ),
                        Label(label=" ", name="volume-widget-icon", h_align="start"),
                    ],
                ),
                Box(
                    orientation="vertical",
                    children=[
                        self.music_widget,
                    ],
                ),
            ],
        )

        # Initialize managers directly like working version
        self.wifi_man = WifiConnections(self)
        self.bluetooth_man = BluetoothConnections(self)

        self.has_bluetooth_open = False
        self.has_wifi_open = False

        # Lazy-loaded widgets - create placeholders
        self.bluetooth_widgets = None
        self.wifi_widgets = None
        self.per_app_volume_widgets = None
        self.expanded_player_widgets = None

        self.center_box = CenterBox(start_children=[self.widgets])
        self.bluetooth_center_box = None
        self.wifi_center_box = None
        self.per_app_volume_center_box = None
        self.expanded_player_center_box = None

        self.widgets.set_size_request(300, -1)

        self.children = self.center_box

        # Set memory baseline for monitoring
        set_memory_baseline("Control Center Initialized")

        # Connect to visibility changes for cleanup
        self.connect("notify::visible", self._on_visibility_changed)

        # Periodic cleanup timer (every 5 minutes when visible)
        # Start periodic memory cleanup (every 5 minutes)
        global _cleanup_timer_id
        _cleanup_timer_id = GLib.timeout_add_seconds(300, self._periodic_cleanup)

    def _on_visibility_changed(self, widget, param):
        """Handle visibility changes for memory management"""
        if not self.get_visible():
            logger.debug("Control center hidden - starting cleanup")
            self._cleanup_when_hidden()

    def _cleanup_when_hidden(self):
        """Clean up resources when widget is hidden to reduce memory usage"""
        log_memory("🧹 BEFORE cleanup when hidden")
        logger.debug("Starting hidden cleanup - freeing widget memory")
        # Clean up music widget content properly
        if self._music_widget_content:
            try:
                # Remove from parent container first
                current_children = list(self.music_widget.children)
                if self._music_widget_content in current_children:
                    current_children.remove(self._music_widget_content)
                    self.music_widget.children = current_children
                
                # Destroy the content to free memory completely
                if hasattr(self._music_widget_content, "destroy"):
                    self._music_widget_content.destroy()
                    
                logger.debug("Destroyed music widget content to free memory")
                self._music_widget_content = None
                self._music_initialized = False
            except Exception as e:
                logger.warning(f"Failed to cleanup music widget content: {e}")

        # Clean up per-app volume widget
        if self._per_app_volume_widget and hasattr(
            self._per_app_volume_widget, "destroy"
        ):
            try:
                self._per_app_volume_widget.destroy()
                self._per_app_volume_widget = None
                self._per_app_volume_initialized = False
            except Exception:
                pass

        # Clean up expanded player widget - aggressive cleanup for reuse
        if self._expanded_player_widget:
            try:
                # Call cleanup directly on the player content (PlayerBoxStack)
                if hasattr(self._expanded_player_widget, 'player_content') and \
                   hasattr(self._expanded_player_widget.player_content, '_periodic_cleanup'):
                    self._expanded_player_widget.player_content._periodic_cleanup()
                
                # Also clean any EmbeddedExpandedPlayer specific state
                if hasattr(self._expanded_player_widget, '_periodic_cleanup'):
                    self._expanded_player_widget._periodic_cleanup()
                    
                logger.debug("Cleaned expanded player internal state (preserved for reuse)")
                # DON'T destroy or set to None - keep for reuse!
            except Exception as e:
                logger.warning(f"Failed to clean expanded player state: {e}")

        # Reset widget containers to free memory (except expanded player for reuse)
        self.bluetooth_widgets = None
        self.wifi_widgets = None
        self.per_app_volume_widgets = None
        # Keep expanded_player_widgets for reuse!
        # self.expanded_player_widgets = None

        # Reset center boxes (except expanded player for reuse)
        self.bluetooth_center_box = None
        self.wifi_center_box = None
        self.per_app_volume_center_box = None
        # Keep expanded_player_center_box for reuse!
        # self.expanded_player_center_box = None

        # Force garbage collection
        import gc

        gc.collect()
        log_memory("🧹 AFTER cleanup when hidden")

    def _periodic_cleanup(self):
        """Periodic cleanup to keep memory usage low"""
        if not self.get_visible():
            # If not visible, do aggressive cleanup
            self._cleanup_when_hidden()
            return True  # Continue timer

        # Light cleanup when visible
        import gc

        gc.collect()
        return True  # Continue timer

    def _ensure_music_widget(self):
        """Lazy load music widget content"""
        if not self._music_initialized:
            log_memory("🎼 BEFORE creating music widget content")
            logger.debug("Creating new PlayerBoxStack instance")
            self._music_widget_content = PlayerBoxStack(
                get_shared_mpris_manager(), control_center=self
            )
            log_memory("🎼 AFTER creating PlayerBoxStack")
            
            # Add to the music widget's children list
            current_children = list(self.music_widget.children)
            current_children.append(self._music_widget_content)
            self.music_widget.children = current_children
            self._music_initialized = True
            log_memory("🎼 AFTER adding to music widget container")
        else:
            logger.debug("Music widget already initialized")
            log_memory("♻️ REUSING existing music widget")

    def _ensure_bluetooth_widgets(self):
        """Lazy load bluetooth widgets"""
        if self.bluetooth_widgets is None:
            self.bluetooth_widgets = Box(
                orientation="vertical",
                h_expand=True,
                name="control-center-widgets",
                children=[
                    Box(
                        orientation="horizontal",
                        name="top-widget",
                        h_expand=True,
                        children=[
                            Box(
                                orientation="vertical",
                                name="wb-widget",
                                style_classes="menu",
                                spacing=5,
                                children=[
                                    self.bluetooth_man,
                                ],
                            ),
                        ],
                    ),
                ],
            )
            self.bluetooth_center_box = CenterBox(
                start_children=[self.bluetooth_widgets]
            )
            self.bluetooth_center_box.set_size_request(300, -1)

    def _ensure_wifi_widgets(self):
        """Lazy load wifi widgets"""
        if self.wifi_widgets is None:
            self.wifi_widgets = Box(
                orientation="vertical",
                h_expand=True,
                name="control-center-widgets",
                children=[
                    Box(
                        orientation="horizontal",
                        name="top-widget",
                        h_expand=True,
                        children=[
                            Box(
                                orientation="vertical",
                                name="wb-widget",
                                style_classes="menu",
                                spacing=5,
                                children=[
                                    self.wifi_man,
                                ],
                            ),
                        ],
                    ),
                ],
            )
            self.wifi_center_box = CenterBox(start_children=[self.wifi_widgets])
            self.wifi_center_box.set_size_request(300, -1)

    def _ensure_per_app_volume_widgets(self):
        """Lazy load per-app volume widgets"""
        if self.per_app_volume_widgets is None:
            if self._per_app_volume_widget is None:
                self._per_app_volume_widget = PerAppVolumeControl(self)

            self.per_app_volume_widgets = Box(
                orientation="vertical",
                h_expand=True,
                name="control-center-widgets",
                children=[
                    self._per_app_volume_widget,
                ],
            )
            self.per_app_volume_center_box = CenterBox(
                start_children=[self.per_app_volume_widgets]
            )
            self.per_app_volume_center_box.set_size_request(300, -1)

    def _ensure_expanded_player_widgets(self):
        """Lazy load expanded player widgets with reuse optimization"""
        if self.expanded_player_widgets is None:
            log_memory("🔧 BEFORE creating expanded player widgets")
            logger.debug("Creating new expanded player widgets")
            if self._expanded_player_widget is None:
                logger.debug("Creating new EmbeddedExpandedPlayer instance")
                self._expanded_player_widget = EmbeddedExpandedPlayer(self)
                log_memory("🔧 AFTER creating EmbeddedExpandedPlayer")
            else:
                logger.debug("Reusing existing EmbeddedExpandedPlayer instance")

            self.expanded_player_widgets = Box(
                orientation="vertical",
                h_expand=True,
                name="control-center-widgets",
                children=[
                    self._expanded_player_widget,
                ],
            )
            self.expanded_player_center_box = CenterBox(
                start_children=[self.expanded_player_widgets]
            )
            self.expanded_player_center_box.set_size_request(300, -1)
            log_memory("🔧 AFTER creating expanded player containers")
        else:
            logger.debug("Reusing existing expanded player widgets")
            log_memory("♻️ REUSING existing expanded player widgets")

    def set_dont_disturb(self, *_):
        self.focus_mode = not self.focus_mode
        modus_service.dont_disturb = self.focus_mode
        self.focus_icon.set_from_file(
            get_relative_path(
                "../../config/assets/icons/applets/dnd.svg"
                if self.focus_mode
                else "../../config/assets/icons/applets/dnd-off.svg"
            )
        )

    def set_volume(self, _, __, volume):
        self._updating_volume = True
        audio_service.speaker.volume = round(volume)
        self._updating_volume = False

    def set_brightness(self, _, __, brightness):
        self._updating_brightness = True
        brightness_value = int((brightness / 100) * brightness_service.max_screen)
        brightness_service.screen_brightness = brightness_value
        self._updating_brightness = False

    def brightness_changed(self, _, brightness_value):
        if self._updating_brightness:
            return

        if brightness_service.max_screen > 0:
            brightness_percentage = int(
                (brightness_value / brightness_service.max_screen) * 100
            )

            GLib.idle_add(
                lambda: self.brightness_scale.set_value(brightness_percentage)
            )

    def on_volume_scroll(self, widget, event):
        current_value = self.volume_scale.get_value()
        scroll_step = 5
        if event.direction == Gdk.ScrollDirection.UP:
            new_value = min(100, current_value + scroll_step)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            new_value = max(0, current_value - scroll_step)
        else:
            return False

        self.volume_scale.set_value(new_value)
        return True

    def on_brightness_scroll(self, widget, event):
        current_value = self.brightness_scale.get_value()
        scroll_step = 5
        if event.direction == Gdk.ScrollDirection.UP:
            new_value = min(100, current_value + scroll_step)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            new_value = max(0, current_value - scroll_step)
        else:
            return False

        self.brightness_scale.set_value(new_value)
        return True

    def set_children(self, children):
        self.children = children

    def open_bluetooth(self, *_):
        self._ensure_bluetooth_widgets()
        idle_add(lambda *_: self.set_children(self.bluetooth_center_box))
        self.has_bluetooth_open = True

    def open_wifi(self, *_):
        self._ensure_wifi_widgets()
        idle_add(lambda *_: self.set_children(self.wifi_center_box))
        self.has_wifi_open = True

    def close_bluetooth(self, *_):
        idle_add(lambda *_: self.set_children(self.center_box))
        self.has_bluetooth_open = False

    def close_wifi(self, *_):
        idle_add(lambda *_: self.set_children(self.center_box))
        self.has_wifi_open = False

    def open_per_app_volume(self, *_):
        self._ensure_per_app_volume_widgets()
        idle_add(lambda *_: self.set_children(self.per_app_volume_center_box))
        self.has_per_app_volume_open = True
        # Refresh the app list when opening
        if self._per_app_volume_widget:
            self._per_app_volume_widget.refresh()

    def close_per_app_volume(self, *_):
        idle_add(lambda *_: self.set_children(self.center_box))
        self.has_per_app_volume_open = False

    def open_expanded_player(self, *_):
        log_memory("🎵 BEFORE opening expanded player")
        self._ensure_expanded_player_widgets()
        idle_add(lambda *_: self.set_children(self.expanded_player_center_box))
        self.has_expanded_player_open = True
        # Refresh the player when opening
        if self._expanded_player_widget:
            self._expanded_player_widget.refresh()
        log_memory("🎵 AFTER opening expanded player")

    def close_expanded_player(self, *_):
        log_memory("🔒 BEFORE closing expanded player")
        idle_add(lambda *_: self.set_children(self.center_box))
        self.has_expanded_player_open = False
        log_memory("🔒 AFTER closing expanded player")

    def _set_mousecapture(self, visible: bool):
        if visible:
            # Lazy load music widget when becoming visible
            self._ensure_music_widget()

        self.set_visible(visible)
        if not visible:
            self.close_bluetooth()
            self.close_wifi()
            self.close_per_app_volume()
            self.close_expanded_player()

    def volume_changed(
        self,
        _,
    ):
        if self._updating_volume:
            return

        GLib.idle_add(
            lambda: self.volume_scale.set_value(int(audio_service.speaker.volume))
        )

    def wlan_changed(self, _, wlan):
        self.wifi_svg.set_from_file(
            get_relative_path(
                "../../config/assets/icons/applets/wifi.svg"
                if wlan != "No Connection"
                else "../../config/assets/icons/applets/wifi-off.svg"
            )
        )
        if wlan != "No Connection":
            if wlan.startswith("connected:"):
                parts = wlan.split(":")
                if len(parts) >= 2:
                    wifi_name = parts[1]
                    GLib.idle_add(
                        lambda: self.wlan_label.set_property("label", wifi_name)
                    )
                else:
                    GLib.idle_add(
                        lambda: self.wlan_label.set_property("label", "Connected")
                    )
            else:
                GLib.idle_add(lambda: self.wlan_label.set_property("label", wlan))
        else:
            GLib.idle_add(lambda: self.wlan_label.set_property("label", wlan))

    def bluetooth_changed(self, _, bluetooth):
        self.bluetooth_svg.set_from_file(
            get_relative_path(
                "../../config/assets/icons/applets/bluetooth.svg"
                if bluetooth != "disabled"
                else "../../config/assets/icons/applets/bluetooth-off.svg"
            )
        )
        if bluetooth != "disabled":
            if bluetooth.startswith("connected:"):
                parts = bluetooth.split(":")
                if len(parts) >= 2:
                    device_name = parts[1]
                    GLib.idle_add(
                        lambda: self.bluetooth_label.set_property("label", device_name)
                    )
                else:
                    GLib.idle_add(
                        lambda: self.bluetooth_label.set_property("label", "Connected")
                    )
            elif bluetooth == "enabled":
                GLib.idle_add(lambda: self.bluetooth_label.set_property("label", "On"))
            else:
                GLib.idle_add(lambda: self.bluetooth_label.set_property("label", "On"))
        else:
            GLib.idle_add(lambda: self.bluetooth_label.set_property("label", "Off"))

    def audio_changed(self, *_):
        pass

    def dnd_changed(self, _, dnd_state):
        self.focus_mode = dnd_state
        self.focus_icon.set_from_file(
            get_relative_path(
                "../../config/assets/icons/applets/dnd.svg"
                if self.focus_mode
                else "../../config/assets/icons/applets/dnd-off.svg"
            )
        )

    def _init_mousecapture(self, mousecapture):
        self._mousecapture_parent = mousecapture

    def hide_controlcenter(self, *_):
        self._mousecapture_parent.toggle_mousecapture()
        self.set_visible(False)

    def destroy(self):
        """Enhanced cleanup of resources when widget is destroyed."""
        try:
            # Cancel any periodic cleanup timers
            global _cleanup_timer_id
            if _cleanup_timer_id:
                GLib.source_remove(_cleanup_timer_id)
                _cleanup_timer_id = None

            # Disconnect all signal connections with better error handling
            for connection in self._signal_connections:
                try:
                    if connection and hasattr(connection, 'disconnect'):
                        connection.disconnect()
                except Exception as e:
                    logger.warning(f"Failed to disconnect signal: {e}")
            self._signal_connections.clear()

            # Clean up heavy components with memory optimization
            components_to_cleanup = [
                ('wifi_man', getattr(self, 'wifi_man', None)),
                ('bluetooth_man', getattr(self, 'bluetooth_man', None)), 
                ('_music_widget_content', self._music_widget_content),
                ('_per_app_volume_widget', self._per_app_volume_widget),
                ('_expanded_player_widget', self._expanded_player_widget)
            ]

            for attr_name, component in components_to_cleanup:
                if component and hasattr(component, 'destroy'):
                    try:
                        component.destroy()
                        setattr(self, attr_name, None)
                    except Exception as e:
                        logger.warning(f"Failed to destroy {attr_name}: {e}")

            # Clean up widget containers and references
            widget_containers = [
                'bluetooth_widgets', 'wifi_widgets', 'per_app_volume_widgets',
                'expanded_player_widgets', 'bluetooth_center_box', 'wifi_center_box',
                'per_app_volume_center_box', 'expanded_player_center_box'
            ]

            for container in widget_containers:
                if hasattr(self, container):
                    setattr(self, container, None)

            # Clear any cached widgets
            global _widget_cache
            _widget_cache.clear()

            # Force garbage collection for immediate memory cleanup
            gc.collect()

        except Exception as e:
            logger.error(f"Error during control center destruction: {e}")
        finally:
            super().destroy()
