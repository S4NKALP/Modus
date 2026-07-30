import os
import signal
import subprocess

from fabric.utils import Gdk, GLib, idle_add, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay

from services.brightness import Brightness
from services.network import NetworkClient
from shared.widgets.flat_scale import FlatScale
from shared.window.applet_window import AppletWindow
from utils.gtk_utils import svg_file
from utils.roam import audio_service, modus_service
from window.controlcenter.bluetooth import (
    BluetoothConnections,
    set_bluetooth_enabled_with_fallback,
)
from window.controlcenter.expanded_player import EmbeddedExpandedPlayer
from window.controlcenter.nightlight import create_night_light_widget
from window.controlcenter.per_app_volume import PerAppVolumeControl
from window.controlcenter.player import PlayerBoxStack, get_shared_mpris_manager
from window.controlcenter.wifi import WifiConnections

_brightness_instance: "Brightness | None" = None


def get_brightness_service() -> "Brightness":
    global _brightness_instance
    if _brightness_instance is None:
        _brightness_instance = Brightness()
    return _brightness_instance


_CAFFEINE_PID_FILE = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "modus-caffeine.pid"
)
_CAFFEINE_INHIBIT_WHY = "Modus Caffeine"


def _caffeine_is_active() -> bool:
    try:
        with open(_CAFFEINE_PID_FILE) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return False
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            data = f.read().decode(errors="ignore")
        return "systemd-inhibit" in data and _CAFFEINE_INHIBIT_WHY in data
    except OSError:
        return False


class ModusControlCenter(AppletWindow):
    def __init__(self, parent=None, pointing_to=None, **kwargs):
        super().__init__(
            parent=parent,
            pointing_to=pointing_to,
            layer="top",
            title="modus-controlcenter",
            anchor="top right",
            margin="2px 10px 0px 0px",
            exclusivity="auto",
            edge_margin=5,
            name="control-center-menu",
            visible=False,
            **kwargs,
        )
        self.focus_mode = modus_service.dont_disturb
        self._updating_brightness = False
        self._updating_volume = False

        # Flight mode and caffeine states
        self.flight_mode = False
        self.caffeine_mode = False
        # Loading flags - music and expanded player are no longer lazy loaded
        self._per_app_volume_initialized = False
        self._signals_connected = False  # Track if signals are connected
        self._resources_initialized = False  # Track if resources are initialized

        # Store references for cleanup - initialize all as None
        self._signal_connections = []
        self._music_widget_content = None
        self._per_app_volume_widget = None
        self._expanded_player_widget = None
        self._mpris_manager = None  # Shared MPRIS manager instance

        # Initialize network service for WiFi toggle - lazy load
        self.network_service = None
        self.wifi_service = None
        self._network_ready_fired = False

        # Initialize flight mode and caffeine states - lazy load
        self.caffeine_mode = False
        self.flight_mode = False

        # Add keybinding immediately (this is fast)
        self.add_keybinding("Escape", self.hide_controlcenter)

        volume = 100
        # Get initial values and connect signals - store connection IDs for cleanup
        wlan = modus_service.wlan if modus_service.wlan else "No Connection"
        bluetooth = modus_service.bluetooth if modus_service.bluetooth else "Off"

        if wlan.startswith("connected:"):
            parts = wlan.split(":")
            wlan_display = parts[1] if len(parts) >= 2 else "Connected"
        else:
            wlan_display = wlan

        self.wlan_label = Label(
            label=wlan_display,
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
        self.volume_scale = FlatScale(
            value=volume,
            min_value=0,
            max_value=100,
            step=5,
            name="volume-widget-slider",
            size=30,
            h_expand=True,
        )

        current_brightness = get_brightness_service().screen_brightness
        brightness_percentage = (
            int((current_brightness / get_brightness_service().max_screen) * 100)
            if get_brightness_service().max_screen > 0
            else 50
        )

        self.brightness_scale = FlatScale(
            value=brightness_percentage,
            min_value=0,
            max_value=100,
            step=5,
            name="brightness-widget-slider",
            size=30,
            h_expand=True,
        )

        # Disable brightness scale if no backlight device is available
        if get_brightness_service().max_screen <= 0:
            self.brightness_scale.set_sensitive(False)

        self._mpris_manager = get_shared_mpris_manager()
        self.music_widget = PlayerBoxStack(self._mpris_manager, control_center=self)

        self.has_bluetooth_open = False
        self.has_wifi_open = False
        self.has_per_app_volume_open = False
        self.has_expanded_player_open = False

        self.bluetooth_svg = svg_file(
            (
                "applets/bluetooth.svg"
                if bluetooth != "disabled"
                else "applets/bluetooth-off.svg"
            ),
            size=42,
        )
        self.wifi_svg = svg_file(
            "applets/wifi.svg" if wlan != "No Connection" else "applets/wifi-off.svg",
            size=42,
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

        self.focus_icon = svg_file(
            "applets/dnd.svg" if self.focus_mode else "applets/dnd-off.svg",
            size=42,
        )

        self.focus_status_label = Label(
            label="On" if self.focus_mode else "Off",
            style_classes="status-label",
            h_align="start",
        )

        self.focus_widget = Button(
            name="focus-widget",
            child=Box(
                spacing=4,
                orientation="h",
                children=[
                    self.focus_icon,
                    Box(
                        v_expand=True,
                        h_expand=True,
                        v_align="center",
                        orientation="v",
                        h_align="start",
                        children=[
                            Label(
                                label="Focus",
                                style_classes="title-widget",
                                h_align="start",
                            ),
                            self.focus_status_label,
                        ],
                    ),
                ],
            ),
            on_clicked=self.set_dont_disturb,
        )

        self.flight_icon = svg_file(
            "applets/flight-on.svg" if self.flight_mode else "applets/flight-off.svg",
            size=42,
        )

        self.flight_widget = Button(
            name="flight-widget",
            child=Box(
                orientation="v",
                h_expand=True,
                v_expand=True,
                spacing=8,
                h_align="center",
                v_align="center",
                children=[
                    self.flight_icon,
                    Label(
                        label="Flight",
                        style_classes="title-widget",
                        h_align="center",
                    ),
                ],
            ),
            on_clicked=self.toggle_flight_mode,
        )

        self.caffeine_icon = svg_file(
            (
                "applets/caffeine-on.svg"
                if self.caffeine_mode
                else "applets/caffeine-off.svg"
            ),
            size=42,
        )

        self.caffeine_status_label = Label(
            label="On" if self.caffeine_mode else "Off",
            style_classes="status-label",
            h_align="start",
        )

        self.caffeine_widget = Button(
            name="caffeine-widget",
            child=Box(
                orientation="v",
                spacing=8,
                h_expand=True,
                v_expand=True,
                h_align="center",
                v_align="center",
                children=[
                    self.caffeine_icon,
                    Label(
                        label="Caffeine",
                        style_classes="title-widget",
                        h_align="center",
                    ),
                ],
            ),
            on_clicked=self.toggle_caffeine,
        )

        # Create night light widget
        self.night_light_widget = create_night_light_widget(self)

        # Create main widgets directly without XML - defer heavy operations
        self.widgets = Box(
            orientation="vertical",
            h_expand=True,
            name="control-center-widgets",
            children=[
                # Top section: Wi-Fi + Bluetooth on left, DND + Flight Mode + Caffeine on right
                Box(
                    orientation="horizontal",
                    h_expand=True,
                    name="top-widget",
                    children=[
                        # Left side: Wi-Fi and Bluetooth
                        Box(
                            orientation="vertical",
                            name="wb-widget",
                            style_classes="menu",
                            spacing=5,
                            children=[
                                self.wlan_widget,
                                self.bluetooth_widget,
                                self.night_light_widget,
                            ],
                        ),
                        # Right side: DND, Flight Mode, and Caffeine
                        Box(
                            orientation="vertical",
                            h_expand=True,
                            name="right-side-widget",
                            children=[
                                # DND widget
                                Box(
                                    orientation="vertical",
                                    name="dnd-widget",
                                    style_classes="menu",
                                    children=[
                                        self.focus_widget,
                                    ],
                                ),
                                # Flight Mode and Caffeine row
                                Box(
                                    orientation="horizontal",
                                    name="flight-caffeine-row",
                                    children=[
                                        Box(
                                            orientation="vertical",
                                            name="flight-widget-container",
                                            style_classes="menu",
                                            h_expand=True,
                                            v_expand=True,
                                            children=[
                                                self.flight_widget,
                                            ],
                                        ),
                                        Box(
                                            orientation="vertical",
                                            name="caffeine-widget-container",
                                            h_expand=True,
                                            v_expand=True,
                                            style_classes="menu",
                                            children=[
                                                self.caffeine_widget,
                                            ],
                                        ),
                                    ],
                                ),
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
                        Overlay(
                            h_expand=True,
                            child=self.brightness_scale,
                            overlays=[
                                svg_file(
                                    "brightness/brightness.svg",
                                    name="brightness-widget-icon",
                                    size=28,
                                    h_align="start",
                                    v_align="center",
                                )
                            ],
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
                            name="vol-box",
                            orientation="horizontal",
                            spacing=12,
                            v_expand=True,
                            children=[
                                Box(
                                    name="vol-slider-box",
                                    h_expand=True,
                                    v_align="center",
                                    v_expand=False,
                                    children=[
                                        Overlay(
                                            h_expand=True,
                                            child=self.volume_scale,
                                            overlays=[
                                                svg_file(
                                                    "volume/audio-volume.svg",
                                                    name="volume-widget-icon",
                                                    size=28,
                                                    h_align="start",
                                                    v_align="center",
                                                )
                                            ],
                                        ),
                                    ],
                                ),
                                Button(
                                    name="per-app-volume-button",
                                    size=(36, 36),
                                    child=svg_file(
                                        "player/audio-switcher.svg",
                                        name="per-app-volume-icon",
                                        size=32,
                                    ),
                                    on_clicked=self.open_per_app_volume,
                                ),
                            ],
                        ),
                    ],
                ),
                self.music_widget,
            ],
        )

        # Initialize network service upfront so WifiConnections can use it
        self.network_service = NetworkClient()
        self.wifi_man = WifiConnections(self, network_service=self.network_service)
        self.bluetooth_man = BluetoothConnections(self)

        self.has_bluetooth_open = False
        self.has_wifi_open = False

        # Create expanded player widgets immediately (no lazy loading)
        self._expanded_player_widget = EmbeddedExpandedPlayer(self)
        self.expanded_player_widgets = Box(
            orientation="vertical",
            h_expand=True,
            name="control-center-widgets",
            children=[
                self._expanded_player_widget,
            ],
        )

        # Lazy-loaded widgets - create placeholders for others
        self.bluetooth_widgets = None
        self.wifi_widgets = None
        self.per_app_volume_widgets = None

        # Create main content boxes
        self.center_box = CenterBox(start_children=[self.widgets])
        self.bluetooth_center_box = None
        self.wifi_center_box = None
        self.per_app_volume_center_box = None
        # Create expanded player center box immediately
        self.expanded_player_center_box = CenterBox(
            start_children=[self.expanded_player_widgets]
        )
        self.expanded_player_center_box.set_size_request(300, -1)

        # Create revealers for crossfade transitions

        self.widgets.set_size_request(300, -1)

        self.children = self.center_box

        # Track current state for smooth transitions
        self.current_view = "main"  # main, expanded_player

        # Connect to visibility changes for cleanup
        self.connect("notify::visible", self._on_visibility_changed)

    def _on_visibility_changed(self, widget, _param):
        """Handle visibility changes for resource management"""
        if not self.get_visible():
            # Suspend player updates
            if self.music_widget and hasattr(self.music_widget, "suspend"):
                self.music_widget.suspend()
            if self._expanded_player_widget and hasattr(
                self._expanded_player_widget, "suspend"
            ):
                self._expanded_player_widget.suspend()

            # Just disconnect signals and reset state flags - don't destroy widgets
            self._disconnect_signals_when_hidden()
        else:
            self._initialize_resources()

            # Resume player updates
            if self.music_widget and hasattr(self.music_widget, "resume"):
                self.music_widget.resume()
            if self._expanded_player_widget and hasattr(
                self._expanded_player_widget, "resume"
            ):
                self._expanded_player_widget.resume()

    def _initialize_resources(self):
        """Initialize resources and connect signals when the control center becomes visible."""
        if self._resources_initialized:
            return

        try:
            logger.debug("Initializing control center resources...")

            # Connect network signal (service created earlier in __init__)
            self.network_service.connect("device-ready", self.on_network_ready)

            # Check initial states lazily (only when needed)
            self._check_initial_states()

            # Store signal connections as (obj, handler_id) tuples for proper cleanup
            self._signal_connections.extend(
                [
                    (
                        audio_service,
                        audio_service.connect("changed", self.audio_changed),
                    ),
                    (
                        audio_service,
                        audio_service.connect("changed", self.volume_changed),
                    ),
                    (
                        modus_service,
                        modus_service.connect("wlan-changed", self.wlan_changed),
                    ),
                    (
                        modus_service,
                        modus_service.connect(
                            "bluetooth-changed", self.bluetooth_changed
                        ),
                    ),
                    (
                        modus_service,
                        modus_service.connect("dont-disturb-changed", self.dnd_changed),
                    ),
                ]
            )

            # Connect brightness controls if brightness service is available
            if get_brightness_service().max_screen > 0:
                self.brightness_scale.connect("value-changed", self.set_brightness)
                self.brightness_scale.connect("scroll-event", self.on_brightness_scroll)
                self._signal_connections.append(
                    (
                        get_brightness_service(),
                        get_brightness_service().connect(
                            "screen", self.brightness_changed
                        ),
                    )
                )

            # Connect volume scale signals
            self.volume_scale.connect("value-changed", self.set_volume)
            self.volume_scale.connect("scroll-event", self.on_volume_scroll)

            # Mark signals as connected
            self._signals_connected = True
            self._resources_initialized = True

            logger.debug("Control center resources initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize control center resources: {e}")
            # Reset flags on failure
            self._signals_connected = False
            self._resources_initialized = False

    def _disconnect_signals_when_hidden(self):
        """Disconnect signals when hidden to reduce resource usage, but keep widgets intact"""
        try:
            # Actually disconnect the signals we tracked
            for obj, handler_id in self._signal_connections:
                try:
                    obj.disconnect(handler_id)
                except Exception as e:
                    logger.warning(f"Failed to disconnect signal: {e}")
            self._signal_connections.clear()

            # Disconnect direct scale signals (connected in _initialize_resources)
            if self.volume_scale:
                try:
                    self.volume_scale.disconnect_by_func(self.set_volume)
                    self.volume_scale.disconnect_by_func(self.on_volume_scroll)
                except Exception:
                    pass
            if self.brightness_scale:
                try:
                    self.brightness_scale.disconnect_by_func(self.set_brightness)
                    self.brightness_scale.disconnect_by_func(self.on_brightness_scroll)
                except Exception:
                    pass

            self._signals_connected = False
            self._resources_initialized = False

            # Reset state flags
            self.has_bluetooth_open = False
            self.has_wifi_open = False
            self.has_per_app_volume_open = False
            self.has_expanded_player_open = False

            # Instantly reset the view
            self._delayed_reset_view()

            logger.debug("Control center signals disconnected while hidden")

        except Exception as e:
            logger.warning(f"Control center signal disconnection failed: {e}")

    def _delayed_reset_view(self):
        if not self.get_visible():
            self.has_bluetooth_open = False
            self.has_wifi_open = False
            self.has_per_app_volume_open = False
            self.has_expanded_player_open = False
            self.current_view = "main"
            self.set_children(self.center_box)
        return False

    def _ensure_bluetooth_widgets(self):
        """Lazy load bluetooth widgets"""
        if self.bluetooth_widgets is None:
            inner_box = Box(
                orientation="vertical",
                h_expand=True,
                v_expand=True,
                children=[self.bluetooth_man],
            )
            self.bluetooth_widgets = EventBox(
                events="button-press-mask",
                on_button_press_event=lambda *_: True,
                child=inner_box,
            )
            self.bluetooth_center_box = Box(
                h_expand=True, v_expand=True, children=[self.bluetooth_widgets]
            )
            self.bluetooth_center_box.set_size_request(350, -1)

    def _ensure_wifi_widgets(self):
        """Lazy load wifi widgets"""
        if self.wifi_widgets is None:
            inner_box = Box(
                orientation="vertical",
                h_expand=True,
                v_expand=True,
                children=[
                    self.wifi_man,
                ],
            )
            self.wifi_widgets = EventBox(
                events="button-press-mask",
                on_button_press_event=lambda *_: True,
                child=inner_box,
            )
            self.wifi_center_box = Box(
                h_expand=True, v_expand=True, children=[self.wifi_widgets]
            )
            self.wifi_center_box.set_size_request(350, -1)

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

    def _check_initial_states(self):
        self.caffeine_mode = _caffeine_is_active()
        self.caffeine_icon.dynamic_file(
            "applets/caffeine-on.svg"
            if self.caffeine_mode
            else "applets/caffeine-off.svg"
        )
        self.caffeine_status_label.set_label("On" if self.caffeine_mode else "Off")
        self.flight_mode = False

    def set_dont_disturb(self, *_):
        self.focus_mode = not self.focus_mode
        modus_service.dont_disturb = self.focus_mode
        self.focus_icon.dynamic_file(
            "applets/dnd.svg" if self.focus_mode else "applets/dnd-off.svg"
        )
        self.focus_status_label.set_label("On" if self.focus_mode else "Off")

    def toggle_flight_mode(self, *_):
        try:
            self.flight_mode = not self.flight_mode
            self.network_service.set_airplane_mode(self.flight_mode)

            # Update icon
            self.flight_icon.dynamic_file(
                "applets/flight-on.svg"
                if self.flight_mode
                else "applets/flight-off.svg"
            )

        except Exception as e:
            logger.warning(f"Failed to toggle flight mode: {e}")

    def toggle_caffeine(self, *_):
        try:
            if _caffeine_is_active():
                try:
                    with open(_CAFFEINE_PID_FILE) as f:
                        pid = int(f.read().strip())
                    with open(f"/proc/{pid}/cmdline", "rb") as f:
                        data = f.read().decode(errors="ignore")
                    if "systemd-inhibit" in data and _CAFFEINE_INHIBIT_WHY in data:
                        os.kill(pid, signal.SIGTERM)
                except (OSError, ValueError):
                    pass
                try:
                    os.unlink(_CAFFEINE_PID_FILE)
                except OSError:
                    pass
                self.caffeine_mode = False
            else:
                cmd = [
                    "systemd-inhibit",
                    "--what=idle:sleep",
                    f"--why={_CAFFEINE_INHIBIT_WHY}",
                    "--mode=block",
                    "sleep",
                    str(100_000_000),
                ]
                proc = subprocess.Popen(cmd)
                try:
                    with open(_CAFFEINE_PID_FILE, "w") as f:
                        f.write(str(proc.pid))
                except OSError as e:
                    logger.warning(
                        f"[controlcenter] Failed to write caffeine PID file: {e}"
                    )
                self.caffeine_mode = True
            self.caffeine_icon.dynamic_file(
                "applets/caffeine-on.svg"
                if self.caffeine_mode
                else "applets/caffeine-off.svg"
            )
            self.caffeine_status_label.set_label("On" if self.caffeine_mode else "Off")
        except Exception as e:
            logger.warning(f"Failed to toggle caffeine: {e}")

    def set_volume(self, _, volume):
        if not self._signals_connected:
            return
        self._updating_volume = True
        audio_service.speaker.volume = round(volume)
        self._updating_volume = False

    def set_brightness(self, _, brightness):
        if not self._signals_connected:
            return
        self._updating_brightness = True
        brightness_value = int((brightness / 100) * get_brightness_service().max_screen)
        get_brightness_service().screen_brightness = brightness_value
        self._updating_brightness = False

    def brightness_changed(self, _, brightness_percentage):
        if not self._signals_connected or self._updating_brightness:
            return

        GLib.idle_add(lambda: self.brightness_scale.set_value(brightness_percentage))

    def on_volume_scroll(self, widget, event):
        if not self._signals_connected:
            return False
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
        if not self._signals_connected:
            return False
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
        if not self._resources_initialized:
            return
        try:
            if self.bluetooth_man and hasattr(self.bluetooth_man, "client"):
                client = self.bluetooth_man.client
                target = not client.enabled
                set_bluetooth_enabled_with_fallback(client, target)
                client.notify("enabled")
                self.bluetooth_svg.dynamic_file(
                    "applets/bluetooth.svg" if target else "applets/bluetooth-off.svg"
                )
                self.bluetooth_label.set_label("On" if target else "Off")
            else:
                logger.warning("Bluetooth client not available for toggling")
        except Exception as e:
            logger.warning(f"Failed to toggle bluetooth: {e}")

    def on_network_ready(self, *_):
        if self._network_ready_fired and self.wifi_service:
            return
        wifi = self.network_service.wifi_device
        if not wifi:
            return
        self._network_ready_fired = True
        self.wifi_service = wifi
        self._signal_connections.append(
            (
                self.wifi_service,
                self.wifi_service.connect("notify::enabled", self.update_wifi_icon),
            )
        )

    def update_wifi_icon(self, *_):
        try:
            if self.wifi_service and self.wifi_svg:
                is_enabled = self.wifi_service.enabled
                self.wifi_svg.dynamic_file(
                    "applets/wifi.svg" if is_enabled else "applets/wifi-off.svg"
                )
        except Exception as e:
            logger.warning(f"Failed to update WiFi icon: {e}")

    def toggle_wifi(self, *_):
        if not self._resources_initialized:
            return
        try:
            if self.wifi_service:
                target = not self.wifi_service.enabled
                self.wifi_service.enabled = target
            else:
                logger.warning("WiFi device not available for toggling")
        except Exception as e:
            logger.warning(f"Failed to toggle wifi: {e}")

    def set_children(self, children):
        self.children = children

    def open_bluetooth(self, *_):
        if not self._resources_initialized:
            return
        self._ensure_bluetooth_widgets()
        idle_add(lambda *_: self.set_children(self.bluetooth_center_box))
        self.has_bluetooth_open = True

    def open_wifi(self, *_):
        if not self._resources_initialized:
            return
        self._ensure_wifi_widgets()
        idle_add(lambda *_: self.set_children(self.wifi_center_box))
        self.has_wifi_open = True

    def close_bluetooth(self, *_):
        try:
            self.bluetooth_man.close_bluetooth()
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        if self.current_view == "expanded_player":
            self._crossfade_to_view("main")
        else:
            idle_add(lambda *_: self.set_children(self.center_box))
        self.has_bluetooth_open = False

    def close_wifi(self, *_):
        try:
            self.wifi_man.close_wifi()
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        if self.current_view == "expanded_player":
            self._crossfade_to_view("main")
        else:
            idle_add(lambda *_: self.set_children(self.center_box))
        self.has_wifi_open = False

    def open_per_app_volume(self, *_):
        if not self._resources_initialized:
            return
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
        if not self._resources_initialized:
            return
        self._crossfade_to_view("expanded_player")
        self.has_expanded_player_open = True
        if self._expanded_player_widget:
            self._expanded_player_widget.refresh()

    def close_expanded_player(self, *_):
        # Just hide the expanded player widget, don't destroy it
        self._crossfade_to_view("main")
        self.has_expanded_player_open = False

    def _crossfade_to_view(self, view_name):
        """Handle transitions between views"""
        if view_name == "expanded_player":
            idle_add(lambda *_: self.set_children(self.expanded_player_center_box))
            self.current_view = "expanded_player"
        elif view_name == "main":
            idle_add(lambda *_: self.set_children(self.center_box))
            self.current_view = "main"

    def _set_mousecapture(self, visible: bool):
        if visible:
            GLib.idle_add(self._initialize_resources)

        self.set_visible(visible)
        if not visible:
            # Simply reset views without multiple overlapping set_children calls
            self.has_bluetooth_open = False
            self.has_wifi_open = False
            self.has_per_app_volume_open = False
            self.has_expanded_player_open = False
            self.current_view = "main"
            self.set_children(self.center_box)

    def volume_changed(
        self,
        _,
    ):
        if not self._signals_connected or self._updating_volume:
            return

        GLib.idle_add(
            lambda: self.volume_scale.set_value(int(audio_service.speaker.volume))
        )

    def wlan_changed(self, _, wlan):
        if not self._signals_connected:
            return
        self.wifi_svg.dynamic_file(
            "applets/wifi.svg" if wlan != "No Connection" else "applets/wifi-off.svg"
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
        if not self._signals_connected:
            return
        self.bluetooth_svg.dynamic_file(
            "applets/bluetooth.svg"
            if bluetooth != "disabled"
            else "applets/bluetooth-off.svg"
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
        if not self._signals_connected:
            return

    def dnd_changed(self, _, dnd_state):
        if not self._signals_connected:
            return
        self.focus_mode = dnd_state
        self.focus_icon.dynamic_file(
            "applets/dnd.svg" if self.focus_mode else "applets/dnd-off.svg"
        )
        self.focus_status_label.set_label("On" if self.focus_mode else "Off")

    def _disconnect_all_signals(self):
        """Disconnect all signal connections to prevent memory leaks"""
        try:
            # _signal_connections stores (obj, handler_id) tuples
            for obj, handler_id in self._signal_connections:
                try:
                    obj.disconnect(handler_id)
                except Exception as e:
                    logger.warning(f"Failed to disconnect signal: {e}")
            self._signal_connections.clear()

            # Disconnect scale widget signals (connected directly, not tracked)
            if self.volume_scale:
                try:
                    self.volume_scale.disconnect_by_func(self.set_volume)
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                try:
                    self.volume_scale.disconnect_by_func(self.on_volume_scroll)
                except Exception as e:
                    logger.error(f"An error occurred: {e}")

            if self.brightness_scale:
                try:
                    self.brightness_scale.disconnect_by_func(self.set_brightness)
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                try:
                    self.brightness_scale.disconnect_by_func(self.on_brightness_scroll)
                except Exception as e:
                    logger.error(f"An error occurred: {e}")

            # Disconnect the visibility change signal on self
            try:
                self.disconnect_by_func(self._on_visibility_changed)
            except Exception as e:
                logger.error(f"An error occurred: {e}")

            self._signals_connected = False
            logger.debug("All signals disconnected successfully")

        except Exception as e:
            logger.warning(f"Signal disconnection failed: {e}")

    def _cleanup_managers(self):
        """Clean up all manager instances"""
        try:
            if self.wifi_man:
                try:
                    self.wifi_man.destroy()
                except Exception as e:
                    logger.warning(f"Failed to destroy WiFi manager: {e}")
                self.wifi_man = None

            if self.bluetooth_man:
                try:
                    self.bluetooth_man.destroy()
                except Exception as e:
                    logger.warning(f"Failed to destroy Bluetooth manager: {e}")
                self.bluetooth_man = None

            if self.network_service:
                try:
                    self.network_service.destroy()
                except Exception as e:
                    logger.warning(f"Failed to destroy network service: {e}")
                self.network_service = None

            if self.wifi_service:
                try:
                    self.wifi_service.disconnect_by_func(self.update_wifi_icon)
                except Exception as e:
                    logger.warning(f"Failed to disconnect WiFi service: {e}")
                self.wifi_service = None

            self._resources_initialized = False

            logger.debug("All managers cleaned up successfully")

        except Exception as e:
            logger.warning(f"Manager cleanup failed: {e}")

    def _cleanup_widgets(self):
        try:
            # Clean up main widgets
            if self.widgets:
                try:
                    self.widgets.destroy()
                except Exception as e:
                    logger.warning(f"Failed to destroy main widgets: {e}")
                self.widgets = None

            # Clean up center box
            if self.center_box:
                try:
                    self.center_box.destroy()
                except Exception as e:
                    logger.warning(f"Failed to destroy center box: {e}")
                self.center_box = None

            # Clean up individual widgets
            widget_attrs = [
                "wlan_widget",
                "bluetooth_widget",
                "focus_widget",
                "flight_widget",
                "caffeine_widget",
                "night_light_widget",
                "volume_scale",
                "brightness_scale",
                "wlan_label",
                "bluetooth_label",
                "focus_status_label",
                "caffeine_status_label",
                "wifi_svg",
                "bluetooth_svg",
                "focus_icon",
                "flight_icon",
                "caffeine_icon",
            ]

            for attr in widget_attrs:
                if getattr(self, attr, None):
                    try:
                        widget = getattr(self, attr)
                        if hasattr(widget, "destroy"):
                            widget.destroy()
                    except Exception as e:
                        logger.warning(f"Failed to destroy {attr}: {e}")
                    setattr(self, attr, None)

            logger.debug("All widgets cleaned up successfully")

        except Exception as e:
            logger.warning(f"Widget cleanup failed: {e}")

    def _cleanup_processes(self):
        logger.debug("All processes cleaned up successfully")

    def _complete_cleanup(self):
        """Perform complete cleanup of all resources"""
        try:
            logger.debug("Starting complete cleanup...")
            self._disconnect_all_signals()
            self._cleanup_managers()
            self._cleanup_widgets()
            self._cleanup_processes()
            self._disconnect_signals_when_hidden()

            logger.debug("Complete cleanup finished successfully")

        except Exception as e:
            logger.error(f"Complete cleanup failed: {e}")

    def hide_controlcenter(self, *_):
        try:
            # Just disconnect signals when hiding, don't destroy widgets
            self._disconnect_signals_when_hidden()

            # Hide the control center
            self.set_visible(False)
            self.set_visible(False)

        except Exception as e:
            logger.error(f"Failed to hide control center: {e}")
            # Still try to hide even if cleanup fails
            self.set_visible(False)

    def destroy(self):
        try:
            self._complete_cleanup()
            super().destroy()
            logger.debug("Control center destroyed successfully")
        except Exception as e:
            logger.error(f"Failed to destroy control center: {e}")
            try:
                super().destroy()
            except Exception as e:
                logger.error(f"An error occurred: {e}")
