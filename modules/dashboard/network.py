from fabric.utils import bulk_connect
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import Gtk, GLib

from modules.dashboard.tile import Tile, add_hover_cursor
from services.network import NetworkClient
import utils.icons as icons


class WifiAccessPointSlot(CenterBox):
    """A widget representing a single WiFi access point in the dashboard."""

    def __init__(self, access_point, network_service: NetworkClient, wifi_service, **kwargs):
        super().__init__(name="wifi-ap-slot", **kwargs)
        self.access_point = access_point
        self.network_service = network_service
        self.wifi_service = wifi_service

        ssid = access_point.ssid
        icon_name = access_point.icon

        self.is_active = access_point.is_active

        self.ap_icon = Image(icon_name=icon_name, size=24)
        self.ap_label = Label(
            label=ssid,
            h_expand=True,
            h_align="start",
            ellipsization="end"
        )

        self.connect_button = Button(
            name="wifi-connect-button",
            label="Connected" if self.is_active else "Connect",
            sensitive=True,  # Always clickable - can connect or disconnect
            on_clicked=self._on_connect_clicked,
            style_classes=["connected"] if self.is_active else None,
        )
        add_hover_cursor(self.connect_button)

        self.set_start_children([
            Box(spacing=8, h_expand=True, h_align="fill", children=[
                self.ap_icon,
                self.ap_label,
            ])
        ])
        self.set_end_children([self.connect_button])

    def _on_connect_clicked(self, *_):
        """Handle connect button click."""
        if self.is_active:
            # Disconnect from current network
            self.connect_button.set_label("Disconnecting...")
            self.connect_button.set_sensitive(False)
            self.wifi_service.disconnect_wifi()
        elif self.access_point.bssid:
            # Connect to this network
            self.connect_button.set_label("Connecting...")
            self.connect_button.set_sensitive(False)
            self.wifi_service.connect_to_wifi(self.access_point)


class Network(Tile):
    """Network tile for the dashboard that shows WiFi status and networks."""

    def __init__(self, **kwargs):
        # Create status label
        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Disconnected",
            h_align="start",
        )
        self.state = False

        # Animation properties
        self._animation_timeout_id = None
        self._animation_step = 0
        self._animation_direction = 1

        super().__init__(
            label="Wi-Fi",
            props=self.label,
            markup=icons.wifi_3,
            menu=True,
            **kwargs,
        )

        # Initialize network client
        self.network_client = NetworkClient()
        self.network_client.connect("changed", self.handle_connection_change)
        self.network_client.connect("ready", self.handle_connection_change)
        self.network_client.connect("wifi_device_added", self._on_wifi_device_added)

        # Initialize state
        self._update_tile_state()

        # Track if content has been created to avoid showing status during init
        self._content_created = False

        # Check if WiFi device is already available
        if self.network_client.wifi_device:
            self._setup_wifi_device()

    def handle_connection_change(self, *_):
        """Handle network connection state changes."""
        self._update_tile_state()

    def _animate_searching(self):
        """Animate wifi icon when searching for networks"""
        wifi_icons = [icons.wifi_0, icons.wifi_1, icons.wifi_2, icons.wifi_3, icons.wifi_2, icons.wifi_1]

        wifi = self.network_client.wifi_device
        if not self.icon or not wifi or not wifi.wireless_enabled:
            self._stop_animation()
            return False

        if wifi.active_access_point:
            self._stop_animation()
            return False

        GLib.idle_add(self.icon.set_markup, wifi_icons[self._animation_step])

        self._animation_step = (self._animation_step + 1) % len(wifi_icons)

        return True

    def _start_animation(self):
        if self._animation_timeout_id is None:
            self._animation_step = 0
            self._animation_direction = 1
            self._animation_timeout_id = GLib.timeout_add(500, self._animate_searching)

    def _stop_animation(self):
        if self._animation_timeout_id is not None:
            GLib.source_remove(self._animation_timeout_id)
            self._animation_timeout_id = None

    def _update_tile_state(self):
        """Update tile visual state based on WiFi status."""
        connected = False
        con_label = "Disconnected"
        wifi = self.network_client.wifi_device

        if wifi and wifi.active_access_point:
            connected = True
            con_label = wifi.active_access_point.ssid
        elif wifi and not wifi.wireless_enabled:
            con_label = "Off"

        if self.state != connected:
            self.state = connected
            if self.state:
                self.remove_style_class("off")
                self.add_style_class("on")
            else:
                self.remove_style_class("on")
                self.add_style_class("off")
            print("WiFi state change:", connected)

        self.label.set_label(con_label)

        # Update tile icon based on WiFi state
        self._update_tile_icon()

    def _update_tile_icon(self):
        """Update the tile icon based on network status"""
        wifi = self.network_client.wifi_device
        ethernet = self.network_client.ethernet_device

        if wifi and not wifi.wireless_enabled:
            self._stop_animation()
            self.icon.set_markup(icons.wifi_off)
            return

        if wifi and wifi.wireless_enabled:
            if wifi.active_access_point:
                self._stop_animation()
                # Show signal strength icon
                if wifi.active_access_point.strength > 0:
                    strength = wifi.active_access_point.strength
                    if strength < 25:
                        self.icon.set_markup(icons.wifi_0)
                    elif strength < 50:
                        self.icon.set_markup(icons.wifi_1)
                    elif strength < 75:
                        self.icon.set_markup(icons.wifi_2)
                    else:
                        self.icon.set_markup(icons.wifi_3)
                else:
                    self.icon.set_markup(icons.wifi_1)
            else:
                # WiFi is enabled but not connected - start animation
                self._start_animation()

        try:
            primary_device = self.network_client.primary_device
        except AttributeError:
            primary_device = "wireless"

        if primary_device == "wired":
            self._stop_animation()
            if ethernet and ethernet.internet == "activated":
                self.icon.set_markup(icons.world)
            else:
                self.icon.set_markup(icons.world_off)
        else:
            if not wifi:
                self._stop_animation()
                self.icon.set_markup(icons.wifi_off)


    def create_content(self):
        """Create the detailed network content for the dashboard."""
        # Create status label
        self.status_label = Label(
            label="Initializing ",
            h_expand=True,
            visible=False,
            h_align="center"
        )

        # Create refresh button with icon
        self.refresh_button_icon = Label(
            name="network-refresh-label",
            markup=icons.reload
        )
        self.refresh_button = Button(
            name="network-refresh",
            child=self.refresh_button_icon,
            tooltip_text="Scan for Wi-Fi networks",
            on_clicked=self._refresh_access_points
        )
        add_hover_cursor(self.refresh_button)

        # Create back button with chevron left icon
        self.back_button_icon = Label(
            name="network-back-label",
            markup=icons.chevron_left
        )
        self.back_button = Button(
            name="network-back",
            child=self.back_button_icon,
            tooltip_text="Back to notifications",
            on_clicked=self._on_back_clicked
        )
        add_hover_cursor(self.back_button)

        # Create header
        header_box = CenterBox(
            name="network-header",
            start_children=[self.back_button],
            center_children=[Label(name="network-title", label="Wi-Fi Networks")],
            end_children=[self.refresh_button]
        )

        # Create access points list
        self.ap_list_box = Box(orientation="v", spacing=4)
        scrolled_window = ScrolledWindow(
            name="network-ap-scrolled-window",
            child=self.ap_list_box,
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False,
        )

        # Main container
        main_container = Box(
            name="network-content",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=True,
            h_align="fill",
            style_classes=["tile-content"],
            children=[
                header_box,
                self.status_label,
                scrolled_window,
            ]
        )

        # Initialize button states
        self.refresh_button.set_sensitive(False)

        # Mark content as created
        self._content_created = True

        # Now update UI state since content is ready
        if self.network_client.wifi_device:
            self._update_wifi_status_ui()

        return main_container

    def _on_wifi_device_added(self, *_):
        """Handle when WiFi device is added."""
        self._setup_wifi_device()

    def _setup_wifi_device(self):
        """Setup WiFi device connections and initial state."""
        if self.network_client.wifi_device:
            self.network_client.wifi_device.connect("changed", self._load_access_points)
            self.network_client.wifi_device.connect("notify::wireless-enabled", self._update_wifi_status_ui)
            self.network_client.wifi_device.connect("notify::active-access-point", self._update_tile_state)

            # Only update UI if content has been created
            if self._content_created and hasattr(self, 'refresh_button'):
                self._update_wifi_status_ui()

            # Update tile icon immediately
            self._update_tile_icon()
        else:
            # Only show error if content has been created
            if self._content_created and hasattr(self, 'status_label'):
                self.status_label.set_label("Wi-Fi device not available.")
                self.status_label.set_visible(True)
            if hasattr(self, 'refresh_button'):
                self.refresh_button.set_sensitive(False)

    def _update_wifi_status_ui(self, *_):
        """Update WiFi status UI elements."""
        if not hasattr(self, 'refresh_button') or not self._content_created:
            return  # Content not created yet

        if self.network_client.wifi_device:
            enabled = self.network_client.wifi_device.wireless_enabled
            self.refresh_button.set_sensitive(enabled)

            if not enabled:
                self.status_label.set_label("Wi-Fi disabled.")
                self.status_label.set_visible(True)
                self._clear_ap_list()
        else:
            self.refresh_button.set_sensitive(False)

    def _on_back_clicked(self, *_):
        """Handle back button click - return to default (notifications) view."""
        if self.dashboard_instance:
            self.dashboard_instance.reset_to_default()

    def _refresh_access_points(self, *_):
        """Refresh access points list."""
        if self.network_client.wifi_device and self.network_client.wifi_device.wireless_enabled:
            self.status_label.set_label("Scanning for Wi-Fi networks...")
            self.status_label.set_visible(True)
            self._clear_ap_list()
            self.network_client.wifi_device.scan()
        return False

    def _clear_ap_list(self):
        """Clear the access points list."""
        for child in self.ap_list_box.get_children():
            child.destroy()

    def _load_access_points(self, *_):
        """Load and display access points."""
        if not hasattr(self, 'ap_list_box'):
            return  # Content not created yet

        if not self.network_client.wifi_device or not self.network_client.wifi_device.wireless_enabled:
            self._clear_ap_list()
            self.status_label.set_label("Wi-Fi disabled.")
            self.status_label.set_visible(True)
            return

        self._clear_ap_list()

        access_points = self.network_client.wifi_device.access_points

        if not access_points:
            self.status_label.set_label("No Wi-Fi networks found.")
            self.status_label.set_visible(True)
        else:
            self.status_label.set_visible(False)
            # Sort access points by connection status (connected first) then by signal strength
            sorted_aps = sorted(access_points, key=lambda x: (not x.is_active, -x.strength))
            for access_point in sorted_aps:
                slot = WifiAccessPointSlot(
                    access_point, self.network_client, self.network_client.wifi_device
                )
                self.ap_list_box.add(slot)
        self.ap_list_box.show_all()


