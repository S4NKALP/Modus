from gi.repository import Gdk, GLib

from fabric.utils import idle_add
from fabric.utils.helpers import (
    get_relative_path,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from loguru import logger
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.svg import Svg
from fabric.widgets.revealer import Revealer
from modules.controlcenter.bluetooth import BluetoothConnections
from modules.controlcenter.wifi import WifiConnections
from services.brightness import Brightness
from utils.roam import audio_service, modus_service
from widgets.wayland import WaylandWindow as Window
from modules.controlcenter.player import PlayerBoxStack
from modules.controlcenter.per_app_volume import PerAppVolumeControl
from modules.controlcenter.expanded_player import EmbeddedExpandedPlayer
from services.mpris import MprisPlayerManager
from services.network import NetworkClient
from fabric.widgets.svg import Svg
from fabric.utils.helpers import get_relative_path

brightness_service = Brightness.get_initial()

# FIX: Icon not showing up in control center
# TODO: Add Player


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

        # Store references for cleanup - initialize all as None
        self._signal_connections = []
        self._music_widget_content = None
        self._per_app_volume_widget = None
        self._expanded_player_widget = None
        self._mpris_manager = None  # Shared MPRIS manager instance

        # Initialize network service for WiFi toggle
        self.network_service = NetworkClient()
        self.wifi_service = None

        # Wait for network service to be ready

        self.add_keybinding("Escape", self.hide_controlcenter)

        volume = 100
        wlan = modus_service.sc("wlan-changed", self.wlan_changed)
        bluetooth = modus_service.sc("bluetooth-changed", self.bluetooth_changed)
        music = modus_service.sc("music-changed", self.audio_changed)

        self.network_service.connect("wifi-device-added", self.on_network_ready)
        # Store signal connections for cleanup
        self._signal_connections.extend(
            [
                audio_service.connect("changed", self.audio_changed),
                audio_service.connect("changed", self.volume_changed),
                modus_service.connect("dont-disturb-changed", self.dnd_changed),
            ]
        )

        print(wlan)
        self.wlan_label = Label(
            label=wlan,
            name="wifi-widget-label",
            max_chars_width=15,
            h_align="start",
            ellipsization="end",
        )
        if bluetooth != "disabled":
            if bluetooth.startswith("connected:"):
                parts = bluetooth.split(":")
                bluetooth_display = parts[1] if len(parts) >= 2 else "Connected"
            else:
                bluetooth_display = "On"
        else:
            bluetooth_display = "Off"

        self.bluetooth_label = Label(
            label=bluetooth_display,
            name="bluetooth-widget-label",
            max_chars_width=15,
            ellipsization="end",
            h_align="start",
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

        self.bluetooth_widget = Box(
            name="bluetooth-widget",
            orientation="h",
            children=[
                Button(
                    name="bluetooth-icon-button",
                    child=self.bluetooth_svg,
                    on_clicked=self.toggle_bluetooth,
                ),
                Button(
                    name="bluetooth-info-button",
                    child=Box(
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
                    on_clicked=self.open_bluetooth,
                ),
            ],
        )

        self.wlan_widget = Box(
            name="wifi-widget",
            orientation="h",
            children=[
                Button(
                    name="wifi-icon-button",
                    child=self.wifi_svg,
                    on_clicked=self.toggle_wifi,
                ),
                Button(
                    name="wifi-info-button",
                    child=Box(
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
                    on_clicked=self.open_wifi,
                ),
            ],
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
                            v_expand=False,
                            children=[
                                self.volume_scale,
                                Button(
                                    name="per-app-volume-button",
                                    child=Svg(
                                        svg_file=get_relative_path(
                                            "../../config/assets/icons/player/audio-switcher.svg"
                                        ),
                                        name="per-app-volume-icon",
                                    ),
                                    on_clicked=self.open_per_app_volume,
                                ),
                            ],
                        ),
                        Label(label=" ", name="volume-widget-icon", h_align="start"),
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

        # Create main content boxes
        self.center_box = CenterBox(start_children=[self.widgets])
        self.bluetooth_center_box = None
        self.wifi_center_box = None
        self.per_app_volume_center_box = None
        self.expanded_player_center_box = None

        # Create revealers for crossfade transitions

        self.widgets.set_size_request(300, -1)

        self.children = self.center_box

        # Track current state for smooth transitions
        self.current_view = "main"  # main, expanded_player

        # Connect to visibility changes for cleanup
        self.connect("notify::visible", self._on_visibility_changed)

    def _on_visibility_changed(self, widget, param):
        """Handle visibility changes for memory management"""
        if not self.get_visible():
            self._cleanup_when_hidden()

    def _cleanup_when_hidden(self):
        """Aggressively clean up resources when widget is hidden to reduce memory usage"""
        try:
            # Clean up music widget content if it exists
            if self._music_widget_content:
                # Remove from the parent container
                current_children = list(self.music_widget.children)
                if self._music_widget_content in current_children:
                    current_children.remove(self._music_widget_content)
                    self.music_widget.children = current_children

                # Trigger periodic cleanup before destroying
                if hasattr(self._music_widget_content, "_periodic_cleanup"):
                    self._music_widget_content._periodic_cleanup()

                # Properly destroy the music widget content
                try:
                    self._music_widget_content.destroy()
                except Exception as e:
                    logger.warning(f"Failed to destroy music widget content: {e}")
                self._music_widget_content = None

            # Clean up shared MPRIS manager when hidden to free memory
            if self._mpris_manager:
                try:
                    self._mpris_manager.destroy()
                except Exception as e:
                    logger.warning(
                        f"Failed to destroy MPRIS manager during cleanup: {e}"
                    )
                self._mpris_manager = None

            # Reset initialization flags to force recreation next time
            self._music_initialized = False

            # Force garbage collection
            import gc

            gc.collect()

            logger.debug("Control center aggressive cleanup completed")

        except Exception as e:
            logger.warning(f"Control center cleanup failed: {e}")

    def _ensure_music_widget(self):
        """Lazy load music widget content - reuse MPRIS manager"""
        if not self._music_initialized:
            # Create shared MPRIS manager if it doesn't exist
            if self._mpris_manager is None:
                self._mpris_manager = MprisPlayerManager()

            self._music_widget_content = PlayerBoxStack(
                self._mpris_manager, control_center=self
            )
            # Add to the music widget's children list
            current_children = list(self.music_widget.children)
            current_children.append(self._music_widget_content)
            self.music_widget.children = current_children
            self._music_initialized = True

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
                    self.wifi_man,
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
        """Lazy load expanded player widgets"""
        if self.expanded_player_widgets is None:
            if self._expanded_player_widget is None:
                self._expanded_player_widget = EmbeddedExpandedPlayer(self)

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

    def toggle_bluetooth(self, *_):
        """Toggle bluetooth on/off"""
        try:
            # Access the bluetooth client from the bluetooth manager
            if hasattr(self, "bluetooth_man") and hasattr(self.bluetooth_man, "client"):
                current_state = self.bluetooth_man.client.enabled
                self.bluetooth_man.client.set_enabled(not current_state)
            else:
                logger.warning("Bluetooth client not available for toggling")
        except Exception as e:
            logger.warning(f"Failed to toggle bluetooth: {e}")

    def on_network_ready(self, *_):
        """Called when network service is ready"""
        self.wifi_service = self.network_service.wifi_device
        if self.wifi_service:
            # Connect to WiFi state changes to update icon
            self.wifi_service.connect("notify::wireless-enabled", self.update_wifi_icon)

    def update_wifi_icon(self, *_):
        """Update WiFi icon based on current state"""
        try:
            if self.wifi_service and hasattr(self, "wifi_svg"):
                is_enabled = self.wifi_service.wireless_enabled
                icon_file = (
                    "../../config/assets/icons/applets/wifi.svg"
                    if is_enabled
                    else "../../config/assets/icons/applets/wifi-off.svg"
                )
                self.wifi_svg.set_from_file(get_relative_path(icon_file))
        except Exception as e:
            logger.warning(f"Failed to update WiFi icon: {e}")

    def toggle_wifi(self, *_):
        """Toggle wifi on/off"""
        try:
            if self.wifi_service:
                self.wifi_service.toggle_wifi()
                # Update icon immediately after toggle
                GLib.timeout_add(100, self.update_wifi_icon)
            else:
                logger.warning("WiFi device not available for toggling")
        except Exception as e:
            logger.warning(f"Failed to toggle wifi: {e}")

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
        if self.current_view == "expanded_player":
            self._crossfade_to_view("main")
        else:
            idle_add(lambda *_: self.set_children(self.center_box))
        self.has_bluetooth_open = False

    def close_wifi(self, *_):
        if self.current_view == "expanded_player":
            self._crossfade_to_view("main")
        else:
            idle_add(lambda *_: self.set_children(self.center_box))
        self.has_wifi_open = False

    def open_per_app_volume(self, *_):
        self._ensure_per_app_volume_widgets()
        if self.current_view == "expanded_player":
            # If coming from expanded player, use crossfade
            self._crossfade_to_view("main")
            GLib.timeout_add(
                250,
                lambda: idle_add(
                    lambda *_: self.set_children(self.per_app_volume_center_box)
                ),
            )
        else:
            idle_add(lambda *_: self.set_children(self.per_app_volume_center_box))
        self.has_per_app_volume_open = True
        # Refresh the app list when opening
        if self._per_app_volume_widget:
            self._per_app_volume_widget.refresh()

    def close_per_app_volume(self, *_):
        if self.current_view == "expanded_player":
            self._crossfade_to_view("main")
        else:
            idle_add(lambda *_: self.set_children(self.center_box))
        self.has_per_app_volume_open = False

    def open_expanded_player(self, *_):
        self._ensure_expanded_player_widgets()
        self._crossfade_to_view("expanded_player")
        self.has_expanded_player_open = True
        # Refresh the player when opening
        if self._expanded_player_widget:
            self._expanded_player_widget.refresh()

    def close_expanded_player(self, *_):
        self._crossfade_to_view("main")
        self.has_expanded_player_open = False

    def _crossfade_to_view(self, view_name):
        """Handle transitions between views"""
        if view_name == "expanded_player":
            # Show expanded player
            self._ensure_expanded_player_widgets()
            idle_add(lambda *_: self.set_children(self.expanded_player_center_box))
            self.current_view = "expanded_player"
        elif view_name == "main":
            # Show main view
            idle_add(lambda *_: self.set_children(self.center_box))
            self.current_view = "main"

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
                    GLib.idle_add(lambda: self.bluetooth_label.set_label(device_name))
                else:
                    GLib.idle_add(lambda: self.bluetooth_label.set_label("Connected"))
            elif bluetooth == "enabled":
                GLib.idle_add(lambda: self.bluetooth_label.set_label("On"))
            else:
                GLib.idle_add(lambda: self.bluetooth_label.set_label("On"))
        else:
            GLib.idle_add(lambda: self.bluetooth_label.set_label("Off"))

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
        """Clean up resources when widget is destroyed"""
        # Disconnect all signal connections
        for connection in self._signal_connections:
            try:
                connection.disconnect()
            except:
                pass

        # Clean up heavy components
        if hasattr(self, "wifi_man") and self.wifi_man:
            self.wifi_man.destroy()
        if hasattr(self, "bluetooth_man") and self.bluetooth_man:
            self.bluetooth_man.destroy()
        if self._music_widget_content:
            self._music_widget_content.destroy()
        if self._per_app_volume_widget:
            self._per_app_volume_widget.destroy()
        if self._expanded_player_widget:
            self._expanded_player_widget.destroy()

        # Clean up shared MPRIS manager
        if self._mpris_manager:
            try:
                self._mpris_manager.destroy()
            except Exception as e:
                logger.warning(f"Failed to destroy MPRIS manager: {e}")
            self._mpris_manager = None

        super().destroy()
