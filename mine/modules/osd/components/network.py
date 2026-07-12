from fabric.utils import GLib
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window

from modules.osd.components.base import BaseOSDContainer
from services import NetworkClient


class NetworkOSDContainer(BaseOSDContainer):
    def __init__(self, window: Window, **kwargs):
        super().__init__(window, **kwargs)
        self.network = NetworkClient()
        self._initialized = False  # Track if initial setup is complete
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.icon = Image(icon_name="network-wired-symbolic", icon_size=26)
        self.label = Label()

        # Defer initialization to allow services to initialize
        GLib.timeout_add(100, self._initialize_state)

        self.children = self.icon, self.label

    def _connect_specific_signals(self):
        # Connect to WiFi device signals
        self.network.connect("wifi_device_added", self._on_wifi_device_added)
        self.network.connect("wifi_device_removed", self._on_wifi_device_removed)

        # Connect to Ethernet device signals
        self.network.connect("ethernet_device_added", self._on_ethernet_device_added)
        self.network.connect(
            "ethernet_device_removed", self._on_ethernet_device_removed
        )

        # Connect to network state changes
        self.network.connect("notify::state", self._on_network_state_changed)

    def _initialize_state(self):
        """Initialize the network state after component setup."""
        self._update_network_display()
        # Mark as initialized after initial state is set
        GLib.timeout_add(500, self._mark_initialized)
        return False

    def _mark_initialized(self):
        """Mark the component as fully initialized."""
        self._initialized = True
        return False

    def _on_wifi_device_added(self, *args):
        """Handle WiFi device added."""
        if self.network.wifi_device:
            # Connect to WiFi-specific signals
            self.network.wifi_device.connect(
                "notify::active-access-point", self._on_wifi_connection_changed
            )
            # Only show OSD if we're already initialized (not first setup)
            if self._initialized:
                self._on_wifi_connection_changed()

    def _on_wifi_device_removed(self, *args):
        """Handle WiFi device removed."""
        if not self._initialized:
            return
        self.update_icon("network-wired-disconnected-symbolic")
        self.update_label("WiFi Disconnected")
        self.show_network_osd()

    def _on_ethernet_device_added(self, *args):
        """Handle Ethernet device added."""
        if self.network.ethernet_device:
            # Connect to Ethernet-specific signals
            self.network.ethernet_device.connect("changed", self._on_ethernet_changed)
            # Only show OSD if we're already initialized (not first setup)
            if self._initialized:
                self._on_ethernet_changed()

    def _on_ethernet_device_removed(self, *args):
        """Handle Ethernet device removed."""
        if not self._initialized:
            return
        self.update_icon("network-wired-disconnected-symbolic")
        self.update_label("Ethernet Disconnected")
        self.show_network_osd()

    def _on_wifi_connection_changed(self, *args):
        """Handle WiFi connection changes."""
        if not self._initialized:
            return
        if not self.is_hovered():
            self._update_network_display()
            self.show_network_osd()

    def _on_ethernet_changed(self, *args):
        """Handle Ethernet state changes."""
        if not self._initialized:
            return
        if not self.is_hovered():
            self._update_network_display()
            self.show_network_osd()

    def _on_network_state_changed(self, *args):
        """Handle network state changes."""
        if not self._initialized:
            return
        if not self.is_hovered():
            self._update_network_display()
            self.show_network_osd()

    def _update_network_display(self):
        """Update display based on current network state."""
        wifi = self.network.wifi_device
        ethernet = self.network.ethernet_device

        # Priority: WiFi active > Ethernet active > Disconnected
        if wifi and wifi.active_access_point:
            # WiFi is connected
            ssid = wifi.active_access_point.ssid
            icon = wifi.active_access_point.icon
            self.update_icon(icon)
            self.update_label(f"WiFi: {ssid}")

        elif ethernet and ethernet.internet == "activated":
            # Ethernet is connected
            self.update_icon("network-wired-symbolic")
            self.update_label("Wired Connection")

        elif ethernet and ethernet.internet == "activating":
            # Ethernet is connecting
            self.update_icon("network-wired-acquiring-symbolic")
            self.update_label("Connecting...")

        else:
            # No active connection
            self.update_icon("network-wired-disconnected-symbolic")
            self.update_label("Disconnected")

    def update_icon(self, icon_name: str):
        """Update the network icon."""
        self.icon.set_from_icon_name(icon_name, 26)

    def update_label(self, text: str):
        """Update the network label."""
        self.label.set_text(text)

    def show_network_osd(self):
        """Trigger the OSD to show."""
        if self.osd:
            self.osd.show_network_osd()
        else:
            self.update()

    def update(self, *_):
        """Override to update display before showing OSD."""
        self._update_network_display()
        super().update()
