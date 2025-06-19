"""
Network plugin for the launcher.
Manage WiFi networks, connect/disconnect, and view network status.
"""

from typing import List
from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
import utils.icons as icons
from services.network import NetworkClient
from gi.repository import GLib

class NetworkPasswordEntry(Box):
    """
    Custom password entry widget for network connections.
    """

    def __init__(self, access_point, network_plugin, **kwargs):
        super().__init__(
            name="network-password-entry",
            orientation="h",
            spacing=8,
            **kwargs
        )
        self.access_point = access_point
        self.network_plugin = network_plugin

        # Password entry field
        self.password_entry = Entry(
            name="network-password-field",
            placeholder="Enter password",
            h_expand=True,
            h_align="fill",
            visibility=False 
        )

        # Connect Enter key to connect action
        self.password_entry.connect("activate", lambda *args: self.connect_to_network())

        # Auto-focus the password entry when widget is created
        GLib.timeout_add(100, self._focus_password_entry)


        # Add widgets to layout
        self.add(self.password_entry)

    def _focus_password_entry(self):
        """Focus the password entry field."""
        try:
            self.password_entry.grab_focus()
        except Exception as e:
            print(f"Could not focus password entry: {e}")
        return False  # Don't repeat

    def connect_to_network(self):
        """Connect to network with entered password."""
        password = self.password_entry.get_text()
        if password:
            self.network_plugin._connect_to_network(self.access_point, password)
            self.network_plugin.showing_password_for = None
            # Force refresh to show normal network list
            self.network_plugin._force_launcher_refresh()
        else:
            print("Please enter a password")

    def cancel_password_entry(self):
        """Cancel password entry and return to network list."""
        self.network_plugin.showing_password_for = None
        # Force refresh to show normal network list
        self.network_plugin._force_launcher_refresh()


class NetworkPlugin(PluginBase):
    """
    Network management plugin for the launcher.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Network"
        self.description = "Manage WiFi networks and connections"

        # Track if we're ready
        self._ready = False

        # Track which network is showing password entry
        self.showing_password_for = None

        # Initialize network client safely
        try:
            self.network_client = NetworkClient()

            # Connect to network client signals
            self.network_client.connect("ready", self._on_network_ready)
            self.network_client.connect("changed", self._on_network_changed)

            if self.network_client.is_ready:
                self._setup_network_signals()
        except Exception as e:
            print(f"Warning: Failed to initialize NetworkClient: {e}")
            self.network_client = None

    def initialize(self):
        """Initialize the network plugin."""
        self.set_triggers(["net"])

    def cleanup(self):
        """Cleanup the network plugin."""
        pass

    def _on_network_ready(self, *args):
        """Called when network client is ready."""
        self._ready = True
        self._setup_network_signals()

    def _on_network_changed(self, *args):
        """Called when network state changes."""
        pass

    def _setup_network_signals(self):
        """Setup signals for WiFi and Ethernet devices."""
        if self.network_client and self.network_client.wifi_device:
            self.network_client.wifi_device.connect("changed", self._on_wifi_changed)
            self.network_client.wifi_device.connect("ap-added", self._on_wifi_changed)
            self.network_client.wifi_device.connect("ap-removed", self._on_wifi_changed)

    def _on_wifi_changed(self, *args):
        """Called when WiFi state changes."""
        pass

    def _get_wifi_icon(self, strength: int) -> str:
        """Get WiFi icon based on signal strength."""
        if strength >= 75:
            return icons.wifi_3
        elif strength >= 50:
            return icons.wifi_2
        elif strength >= 25:
            return icons.wifi_1
        else:
            return icons.wifi_0

    def _get_connection_status_icon(self) -> str:
        """Get icon representing current connection status."""
        if not self._ready or not self.network_client:
            return icons.loader

        # Check ethernet first
        if (self.network_client.ethernet_device and
            self.network_client.ethernet_device.state == "activated"):
            return icons.world

        # Check WiFi
        if not self.network_client.wifi_device:
            return icons.cloud_off
        elif not self.network_client.wifi_device.wireless_enabled:
            return icons.wifi_off
        else:
            active_ap = self.network_client.wifi_device.active_access_point
            if active_ap:
                return self._get_wifi_icon(active_ap.strength)
            else:
                return icons.world_off

    def _format_connection_status(self) -> tuple[str, str]:
        """Get formatted connection status title and subtitle."""
        if not self._ready or not self.network_client:
            return "Network Loading...", "Initializing network client"

        # Check ethernet first
        if (self.network_client.ethernet_device and
            self.network_client.ethernet_device.state == "activated"):
            speed = self.network_client.ethernet_device.speed
            return "Connected via Ethernet", f"Speed: {speed}"

        # Check WiFi
        if not self.network_client.wifi_device:
            return "No WiFi Device", "WiFi hardware not found"
        elif not self.network_client.wifi_device.wireless_enabled:
            return "WiFi Disabled", "Click to enable WiFi"
        else:
            active_ap = self.network_client.wifi_device.active_access_point
            if active_ap:
                return f"Connected to {active_ap.ssid}", f"Signal: {active_ap.strength}%"
            else:
                return "WiFi Disconnected", "No active connection"

    def _toggle_wifi(self):
        """Toggle WiFi on/off and keep launcher open."""
        if self.network_client and self.network_client.wifi_device:
            self.network_client.wifi_device.toggle_wifi()
        return None  # Keep launcher open to show new state

    def _disconnect_wifi(self):
        """Disconnect from current WiFi network and keep launcher open."""
        if (self.network_client and self.network_client.wifi_device and
            self.network_client.wifi_device.active_access_point):
            self.network_client.wifi_device.disconnect_wifi()
        return None  # Keep launcher open to show disconnected state

    def _scan_networks(self):
        """Scan for available networks and keep launcher open."""
        if self.network_client and self.network_client.wifi_device:
            self.network_client.wifi_device.scan()
        # Return None to keep launcher open
        return None

    def _connect_to_network(self, access_point, password: str = None):
        """Connect to a WiFi network with improved error handling."""
        try:
            if not self.network_client:
                return None

            if not self.network_client.wifi_device:
                return None

            # Validate access point
            if not access_point or not hasattr(access_point, 'ssid'):
                return None

            # Validate password for secured networks
            if access_point.requires_password and not password:
                return None


            # Use our own safer connection method to avoid NetworkManager errors
            self._safe_connect_to_wifi(access_point, password)

        except Exception as e:
            print(f"Error connecting to network {access_point.ssid}: {e}")
        return None  # Keep launcher open to show connection progress

    def _safe_connect_to_wifi(self, access_point, password: str = None):
        """Safer WiFi connection method to avoid NetworkManager assertion errors."""
        try:
            from gi.repository import NM, GLib

            ssid = access_point.ssid
            client = self.network_client._client
            device = self.network_client.wifi_device._device

            if not client or not device:
                print("NetworkManager client or device not available")
                return False


            # Check for existing connections first
            existing_connection = None
            for connection in client.get_connections():
                wifi_setting = connection.get_setting_wireless()
                if wifi_setting:
                    conn_ssid = NM.utils_ssid_to_utf8(wifi_setting.get_ssid().get_data())
                    if conn_ssid == ssid:
                        existing_connection = connection
                        break

            if existing_connection:
                # Use existing connection
                def activate_existing():
                    try:
                        client.activate_connection_async(
                            existing_connection, device, None, None,
                            self._on_connection_result
                        )
                    except Exception as e:
                        print(f"Error activating existing connection: {e}")
                    return False

                GLib.timeout_add(200, activate_existing)
            else:
                # Create new connection with delay to prevent assertion errors
                def create_new_connection():
                    try:
                        self._create_and_activate_connection(ssid, password, client, device)
                    except Exception as e:
                        print(f"Error creating new connection: {e}")
                    return False

                GLib.timeout_add(200, create_new_connection)

        except Exception as e:
            print(f"Error in safe WiFi connection: {e}")
            return False

    def _create_and_activate_connection(self, ssid, password, client, device):
        """Create and activate a new WiFi connection."""
        try:
            from gi.repository import NM, GLib

            # Create connection
            connection = NM.SimpleConnection.new()

            # Connection settings
            s_con = NM.SettingConnection.new()
            s_con.set_property(NM.SETTING_CONNECTION_ID, ssid)
            s_con.set_property(NM.SETTING_CONNECTION_TYPE, "802-11-wireless")
            s_con.set_property(NM.SETTING_CONNECTION_INTERFACE_NAME, device.get_iface())
            connection.add_setting(s_con)

            # Wireless settings
            s_wifi = NM.SettingWireless.new()
            s_wifi.set_property(NM.SETTING_WIRELESS_SSID, GLib.Bytes.new(ssid.encode()))
            s_wifi.set_property(NM.SETTING_WIRELESS_MODE, "infrastructure")
            connection.add_setting(s_wifi)

            # Security settings if password provided
            if password:
                s_sec = NM.SettingWirelessSecurity.new()
                s_sec.set_property(NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, "wpa-psk")
                s_sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
                connection.add_setting(s_sec)

            # IP settings
            s_ipv4 = NM.SettingIP4Config.new()
            s_ipv4.set_property("method", "auto")
            connection.add_setting(s_ipv4)

            s_ipv6 = NM.SettingIP6Config.new()
            s_ipv6.set_property("method", "auto")
            connection.add_setting(s_ipv6)

            # Add connection and activate
            def on_connection_added(client_obj, result):
                try:
                    new_connection = client_obj.add_connection_finish(result)
                    if new_connection:
                        # Activate with delay
                        def activate_new():
                            try:
                                client_obj.activate_connection_async(
                                    new_connection, device, None, None,
                                    self._on_connection_result
                                )
                            except Exception as e:
                                print(f"Error activating new connection: {e}")
                            return False
                        GLib.timeout_add(100, activate_new)
                    else:
                        print(f"✗ Failed to create connection profile for {ssid}")
                except Exception as e:
                    print(f"Error in connection callback: {e}")

            client.add_connection_async(connection, True, None, on_connection_added)

        except Exception as e:
            print(f"Error creating connection: {e}")

    def _on_connection_result(self, client, result):
        """Handle connection activation result."""
        try:
            active_connection = client.activate_connection_finish(result)
            if active_connection:
                print("✓ WiFi connection successful")
            else:
                print("✗ WiFi connection failed")
        except Exception as e:
            print(f"Connection result error: {e}")

    def _show_password_entry_for_network(self, access_point):
        """Show password entry for a network that requires password."""
        # Set which network is showing password entry
        self.showing_password_for = access_point.ssid

        # Force launcher refresh by triggering a search
        self._force_launcher_refresh()

        return None  # Keep launcher open

    def _force_launcher_refresh(self):
        """Force the launcher to refresh and show the password entry."""
        try:
            from gi.repository import GLib

            # Use a small delay to ensure the action completes first
            def trigger_refresh():
                try:
                    # Try to access the launcher through the fabric Application
                    from fabric import Application
                    app = Application.get_default()

                    if app and hasattr(app, 'launcher'):
                        launcher = app.launcher
                        if launcher and hasattr(launcher, '_perform_search'):
                            # Get current query and trigger a search
                            current_query = launcher.query if hasattr(launcher, 'query') else ""
                            if not current_query:
                                # If no query, use the trigger to force refresh
                                current_query = "net list"

                            # Force a search which will refresh the results
                            launcher._perform_search(current_query)
                            return False

                    # Fallback: try to find launcher instance through other means
                    import gc
                    for obj in gc.get_objects():
                        if hasattr(obj, '__class__') and obj.__class__.__name__ == 'Launcher':
                            if hasattr(obj, '_perform_search') and hasattr(obj, 'query'):
                                current_query = obj.query if obj.query else "net list"
                                obj._perform_search(current_query)
                                return False


                except Exception as e:
                    print(f"Error forcing launcher refresh: {e}")

                return False  # Don't repeat

            # Use a small delay to ensure the action completes first
            GLib.timeout_add(50, trigger_refresh)

        except Exception as e:
            print(f"Could not trigger refresh: {e}")

    def _cancel_password_entry(self):
        """Cancel password entry and return to network list."""
        self.showing_password_for = None
        return None  # Keep launcher open



    def query(self, query_string: str) -> List[Result]:
        """Process network queries."""
        results = []
        query = query_string.strip()
        query_lower = query.lower()

        # No more text-based password handling - using custom widgets instead

        if not query_lower:
            # Check if network client is available
            if not self.network_client:
                results.append(
                    Result(
                        title="Network Service Unavailable",
                        subtitle="NetworkManager service is not available",
                        icon_markup=icons.cloud_off,
                        action=lambda: None,
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "error"},
                    )
                )
                return results

            # Show current connection status
            title, subtitle = self._format_connection_status()
            status_icon = self._get_connection_status_icon()

            results.append(
                Result(
                    title=title,
                    subtitle=subtitle,
                    icon_markup=status_icon,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "status"},
                )
            )

            # Show available actions
            if not self._ready:
                return results

            # WiFi toggle option
            if self.network_client.wifi_device:
                if self.network_client.wifi_device.wireless_enabled:
                    results.append(
                        Result(
                            title="Disable WiFi",
                            subtitle="Turn off wireless networking",
                            icon_markup=icons.wifi_off,
                            action=lambda: self._toggle_wifi(),
                            relevance=0.9,
                            plugin_name=self.display_name,
                            data={"type": "toggle_wifi", "keep_launcher_open": True},
                        )
                    )

                    # Disconnect option if connected
                    if self.network_client.wifi_device.active_access_point:
                        results.append(
                            Result(
                                title="Disconnect WiFi",
                                subtitle=f"Disconnect from {self.network_client.wifi_device.active_access_point.ssid}",
                                icon_markup=icons.world_off,
                                action=lambda: self._disconnect_wifi(),
                                relevance=0.8,
                                plugin_name=self.display_name,
                                data={"type": "disconnect", "keep_launcher_open": True},
                            )
                        )

                else:
                    results.append(
                        Result(
                            title="Enable WiFi",
                            subtitle="Turn on wireless networking",
                            icon_markup=icons.wifi_3,
                            action=lambda: self._toggle_wifi(),
                            relevance=0.9,
                            plugin_name=self.display_name,
                            data={"type": "toggle_wifi", "keep_launcher_open": True},
                        )
                    )

            return results

        # Handle specific commands
        if query_lower in ["scan", "refresh"]:
            # Trigger scan immediately
            self._scan_networks()

            results.append(
                Result(
                    title="Scanning for Networks...",
                    subtitle="Refreshing available WiFi networks",
                    icon_markup=icons.radar,
                    action=lambda: None,  # Keep launcher open
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "scanning", "keep_launcher_open": True},
                )
            )

            # Show current networks if any
            if (self._ready and self.network_client.wifi_device and
                self.network_client.wifi_device.wireless_enabled):
                access_points = self.network_client.wifi_device.access_points
                if access_points:
                    results.append(
                        Result(
                            title=f"Found {len(access_points)} Networks",
                            subtitle="Scan complete - networks updated",
                            icon_markup=icons.wifi_3,
                            action=lambda: None,
                            relevance=0.9,
                            plugin_name=self.display_name,
                            data={"type": "scan_complete", "keep_launcher_open": True},
                        )
                    )

            return results

        if query_lower in ["disconnect", "off"]:
            if (self.network_client.wifi_device and
                self.network_client.wifi_device.active_access_point):
                ap = self.network_client.wifi_device.active_access_point
                results.append(
                    Result(
                        title=f"Disconnect from {ap.ssid}",
                        subtitle=f"Currently connected with {ap.strength}% signal",
                        icon_markup=icons.world_off,
                        action=lambda: self._disconnect_wifi(),
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "disconnect", "keep_launcher_open": True},
                    )
                )
            else:
                results.append(
                    Result(
                        title="Not Connected",
                        subtitle="No active WiFi connection to disconnect",
                        icon_markup=icons.world_off,
                        action=lambda: None,
                        relevance=0.5,
                        plugin_name=self.display_name,
                        data={"type": "info"},
                    )
                )
            return results

        if query_lower in ["toggle"]:
            if self.network_client.wifi_device:
                if self.network_client.wifi_device.wireless_enabled:
                    action_text = "Disable WiFi"
                    icon = icons.wifi_off
                else:
                    action_text = "Enable WiFi"
                    icon = icons.wifi_3

                results.append(
                    Result(
                        title=action_text,
                        subtitle="Toggle wireless networking",
                        icon_markup=icon,
                        action=lambda: self._toggle_wifi(),
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "toggle_wifi", "keep_launcher_open": True},
                    )
                )
            return results

        # Search for specific networks or show available networks
        if (self._ready and self.network_client.wifi_device and
            self.network_client.wifi_device.wireless_enabled):

            access_points = self.network_client.wifi_device.access_points

            if query_lower in ["list"]:
                # Automatically scan when listing networks
                self._scan_networks()

                # Show all available networks
                if not access_points:
                    results.append(
                        Result(
                            title="Scanning for Networks...",
                            subtitle="Please wait while scanning for WiFi networks",
                            icon_markup=icons.radar,
                            action=lambda: None,  # Don't close launcher
                            relevance=1.0,
                            plugin_name=self.display_name,
                            data={"type": "scanning", "keep_launcher_open": True},
                        )
                    )
                else:
                    for ap in access_points[:10]:  # Limit to 10 networks
                        # Add lock icon for secured networks
                        if ap.requires_password:
                            title = f"🔒 {ap.ssid}"
                        else:
                            title = ap.ssid

                        # Check if this network should show password entry instead
                        if ap.requires_password and self.showing_password_for == ap.ssid:
                            # REPLACE network with password entry Result using our own Entry widget
                            password_widget = NetworkPasswordEntry(
                                access_point=ap,
                                network_plugin=self
                            )

                            results.append(
                                Result(
                                    title=f"🔑 Enter password for {ap.ssid}",
                                    subtitle="Type password and click connect • Click cancel to go back",
                                    icon_markup=icons.lock,
                                    action=lambda: None,  # Widget handles the action
                                    relevance=1.0,  # High relevance to appear at top
                                    plugin_name=self.display_name,
                                    custom_widget=password_widget,  # Use our custom Entry widget
                                    data={
                                        "type": "password_entry",
                                        "ssid": ap.ssid,
                                        "keep_launcher_open": True
                                    },
                                )
                            )
                        else:
                            # Show normal network Result
                            if ap.is_active:
                                subtitle = f"Connected • {ap.strength}% signal"
                                action = lambda: self._disconnect_wifi()
                            else:
                                if ap.requires_password:
                                    subtitle = f"{ap.strength}% signal • Click to enter password"
                                    action = lambda current_ap=ap: self._show_password_entry_for_network(current_ap)
                                else:
                                    subtitle = f"{ap.strength}% signal • Click to connect"
                                    action = lambda current_ap=ap: self._connect_to_network(current_ap)

                            results.append(
                                Result(
                                    title=title,
                                    subtitle=subtitle,
                                    icon_markup=self._get_wifi_icon(ap.strength),
                                    action=action,
                                    relevance=0.9 if ap.is_active else 0.8,
                                    plugin_name=self.display_name,
                                    data={
                                        "type": "network",
                                        "ssid": ap.ssid,
                                        "requires_password": ap.requires_password,
                                        "keep_launcher_open": True
                                    },
                                )
                            )



                return results

            else:
                # Search for networks matching the query
                matching_networks = [
                    ap for ap in access_points
                    if query.lower() in ap.ssid.lower()
                ]

                if matching_networks:
                    for ap in matching_networks[:5]:  # Limit to 5 matches
                        if ap.requires_password:
                            title = f"🔒 {ap.ssid}"
                        else:
                            title = ap.ssid

                        # Check if this network should show password entry instead
                        if ap.requires_password and self.showing_password_for == ap.ssid:
                            # REPLACE network with password entry Result using our own Entry widget
                            password_widget = NetworkPasswordEntry(
                                access_point=ap,
                                network_plugin=self
                            )

                            results.append(
                                Result(
                                    title=f"🔑 Enter password for {ap.ssid}",
                                    subtitle="Type password and click connect • Click cancel to go back",
                                    icon_markup=icons.lock,
                                    action=lambda: None,  # Widget handles the action
                                    relevance=1.0,  # High relevance to appear at top
                                    plugin_name=self.display_name,
                                    custom_widget=password_widget,  # Use our custom Entry widget
                                    data={
                                        "type": "password_entry",
                                        "ssid": ap.ssid,
                                        "keep_launcher_open": True
                                    },
                                )
                            )
                        else:
                            # Show normal network Result
                            if ap.is_active:
                                subtitle = f"Connected • {ap.strength}% signal"
                                action = lambda: self._disconnect_wifi()
                            else:
                                if ap.requires_password:
                                    subtitle = f"{ap.strength}% signal • Click to enter password"
                                    action = lambda current_ap=ap: self._show_password_entry_for_network(current_ap)
                                else:
                                    subtitle = f"{ap.strength}% signal • Click to connect"
                                    action = lambda current_ap=ap: self._connect_to_network(current_ap)

                            results.append(
                                Result(
                                    title=title,
                                    subtitle=subtitle,
                                    icon_markup=self._get_wifi_icon(ap.strength),
                                    action=action,
                                    relevance=1.0 if ap.is_active else 0.9,
                                    plugin_name=self.display_name,
                                    data={
                                        "type": "network",
                                        "ssid": ap.ssid,
                                        "requires_password": ap.requires_password,
                                        "keep_launcher_open": True
                                    },
                                )
                            )



                    return results
                else:
                    # No matching networks found
                    results.append(
                        Result(
                            title=f"No networks matching '{query}'",
                            subtitle="Try scanning for more networks",
                            icon_markup=icons.radar,
                            action=lambda: self._scan_networks(),
                            relevance=0.5,
                            plugin_name=self.display_name,
                            data={"type": "scan", "keep_launcher_open": True},
                        )
                    )
                    return results

        # Fallback for when WiFi is disabled or not available
        results.append(
            Result(
                title="WiFi Not Available",
                subtitle="Enable WiFi to search for networks",
                icon_markup=icons.wifi_off,
                action=lambda: self._toggle_wifi() if self.network_client.wifi_device else None,
                relevance=0.5,
                plugin_name=self.display_name,
                data={"type": "info"},
            )
        )

        return results