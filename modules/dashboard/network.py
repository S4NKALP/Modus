from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import Gtk

from modules.dashboard.tile import Tile
from services.network import NetworkClient

import utils.icons as icons


class Network(Tile):
    def __init__(self, **kwargs):
        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Disconnected",
            h_align="start",
        )
        self.state = False

        super().__init__(
            label="Wi-Fi",
            props=self.label,
            markup=icons.wifi,
            menu=True,
            **kwargs,
        )
        self.nm = NetworkClient()
        self.nm.connect("changed", self.handle_connection_change)
        self.nm.connect("ready", self.handle_connection_change)

    def handle_connection_change(self, *_):
        # Get current network state from NetworkClient properties
        connected = False
        con_label = "Disconnected"

        if self.nm.wifi_device and self.nm.wifi_device.active_access_point:
            connected = True
            con_label = self.nm.wifi_device.active_access_point.ssid
        elif not self.nm.wireless_enabled:
            con_label = "Off"

        if self.state != connected:
            self.state = connected
            if self.state:
                self.remove_style_class("off")
                self.add_style_class("on")
            else:
                self.remove_style_class("on")
                self.add_style_class("off")
            print("State change:", connected)

        self.label.set_label(con_label)


    def create_content(self):
        """Create the detailed network content for the dashboard"""
        content_box = Box(
            name="network-content",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=True,
            h_align="fill",
            style_classes=["tile-content"],
        )

        # Header with WiFi toggle
        header_box = Box(
            orientation="h",
            spacing=12,
            h_expand=True,
            h_align="fill",
        )

        wifi_label = Label(
            markup="<b>Wi-Fi</b>",
            h_align="start",
            h_expand=True,
        )

        self.wifi_switch = Gtk.Switch(
            name="wifi-switch",
            active=self.nm.wireless_enabled if self.nm.wifi_device else False,
        )
        self.wifi_switch.connect("notify::active", self._on_wifi_toggle)

        header_box.children = [wifi_label, self.wifi_switch]
        content_box.add(header_box)

        # Networks list
        self.networks_container = Box(
            orientation="v",
            spacing=4,
            h_expand=True,
        )

        # Scrolled window for networks
        networks_scroll = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
            child=self.networks_container,
        )
        networks_scroll.set_size_request(-1, 200)

        content_box.add(networks_scroll)

        # Scan button
        scan_button = Button(
            label="Scan for Networks",
            h_align="center",
            on_clicked=self._on_scan_clicked,
        )
        content_box.add(scan_button)

        # Populate networks initially
        self._refresh_networks()

        return content_box

    def _on_wifi_toggle(self, *_):
        """Handle WiFi toggle"""
        if self.nm.wifi_device:
            self.nm.wifi_device.toggle_wifi()
            self._refresh_networks()

    def _on_scan_clicked(self, *_):
        """Handle scan button click"""
        if self.nm.wifi_device:
            self.nm.wifi_device.scan()
            self._refresh_networks()

    def _refresh_networks(self):
        """Refresh the networks list"""
        # Clear existing networks
        for child in self.networks_container.get_children():
            self.networks_container.remove(child)

        if not self.nm.wifi_device or not self.nm.wifi_device.wireless_enabled:
            no_wifi_label = Label(
                label="WiFi is disabled",
                h_align="center",
                style_classes=["dim-label"],
            )
            self.networks_container.add(no_wifi_label)
            return

        access_points = self.nm.wifi_device.access_points
        if not access_points:
            no_networks_label = Label(
                label="No networks found\nClick 'Scan for Networks' to refresh",
                h_align="center",
                style_classes=["dim-label"],
            )
            self.networks_container.add(no_networks_label)
            return

        # Sort access points by signal strength (connected first, then by strength)
        sorted_aps = sorted(
            access_points, key=lambda ap: (not ap.is_active, -ap.strength)
        )

        for ap in sorted_aps:
            self._create_network_item(ap)

        self.networks_container.show_all()

    def _create_network_item(self, ap):
        """Create a network item widget"""
        network_box = Box(
            orientation="h",
            spacing=8,
            h_expand=True,
            style_classes=["network-item"],
        )

        # Signal strength icon
        signal_strength = min(100, max(0, ap.strength))
        if signal_strength >= 75:
            signal_icon = icons.wifi_3
        elif signal_strength >= 50:
            signal_icon = icons.wifi_2
        elif signal_strength >= 25:
            signal_icon = icons.wifi_1
        else:
            signal_icon = icons.wifi_0

        signal_label = Label(
            markup=signal_icon,
            style_classes=["network-signal"],
        )
        network_box.add(signal_label)

        # Network name and status
        info_box = Box(
            orientation="v",
            h_expand=True,
            h_align="start",
        )

        if ap.is_active:
            name_markup = f"<b>{ap.ssid}</b>"
            status_label = Label(
                label="Connected",
                h_align="start",
                style_classes=["network-status", "connected"],
            )
            info_box.add(Label(markup=name_markup, h_align="start"))
            info_box.add(status_label)
        else:
            name_label = Label(
                label=ap.ssid,
                h_align="start",
                style_classes=["network-name"],
            )
            info_box.add(name_label)

        network_box.add(info_box)

        # Lock icon for secured networks
        if ap.requires_password:
            lock_label = Label(
                markup=icons.lock,
                style_classes=["network-lock"],
            )
            network_box.add(lock_label)

        # Make the whole item clickable
        network_button = Button(
            child=network_box,
            style_classes=["network-button"],
            on_clicked=lambda *_: self._on_network_clicked(ap),
        )

        self.networks_container.add(network_button)

    def _on_network_clicked(self, ap):
        """Handle network item click"""
        if ap.is_active:
            # Disconnect from current network
            if self.nm.wifi_device:
                self.nm.wifi_device.disconnect_wifi()
        else:
            # Connect to network (simplified - would need password handling for secured networks)
            if self.nm.wifi_device:
                try:
                    self.nm.wifi_device.connect_to_access_point(ap)
                except Exception as e:
                    print(f"Failed to connect to {ap.ssid}: {e}")

        # Refresh networks after action
        self._refresh_networks()
