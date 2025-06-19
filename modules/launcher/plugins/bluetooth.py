"""
Bluetooth plugin for the launcher.
Manage Bluetooth devices, connections, and adapter settings.
"""

from typing import List
from fabric.bluetooth import BluetoothClient, BluetoothDevice
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
import utils.icons as icons


class BluetoothPlugin(PluginBase):
    """
    Bluetooth management plugin for the launcher.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Bluetooth"
        self.description = "Manage Bluetooth devices and connections"

        # Initialize bluetooth client with timeout protection
        self.bluetooth_client = None
        self._bluetooth_available = False
        self._last_query_time = 0  # Track when plugin was last used
        self._scan_timeout_id = None  # Track auto-stop scan timeout
        self._init_bluetooth_client()

    def initialize(self):
        """Initialize the bluetooth plugin."""
        self.set_triggers(["bluetooth", "bt", "blue"])

    def cleanup(self):
        """Cleanup the bluetooth plugin."""
        # Stop any ongoing scanning when plugin is cleaned up
        if self.bluetooth_client and self.bluetooth_client.scanning:
            self.bluetooth_client.scanning = False

        # Cancel any pending scan timeout
        if self._scan_timeout_id:
            try:
                from gi.repository import GLib
                GLib.source_remove(self._scan_timeout_id)
                self._scan_timeout_id = None
            except Exception:
                pass

    def _init_bluetooth_client(self):
        """Initialize bluetooth client with proper error handling."""
        try:
            # Set up timeout for bluetooth client creation
            import signal

            def timeout_handler(_signum, _frame):
                raise TimeoutError("Bluetooth client initialization timeout")

            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(3)  # 3 second timeout

            try:
                self.bluetooth_client = BluetoothClient()
                self.bluetooth_client.connect("changed", self._on_bluetooth_changed)
                self.bluetooth_client.connect("device-added", self._on_device_changed)
                self.bluetooth_client.connect("device-removed", self._on_device_changed)
                self._bluetooth_available = True
                print("✓ Bluetooth client initialized successfully")
            except TimeoutError:
                print("Warning: Bluetooth client initialization timed out")
                self.bluetooth_client = None
            except Exception as e:
                print(f"Warning: Failed to initialize BluetoothClient: {e}")
                self.bluetooth_client = None
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        except Exception as e:
            print(f"Warning: Bluetooth initialization failed: {e}")
            self.bluetooth_client = None

    def _on_bluetooth_changed(self, *_args):
        """Called when bluetooth state changes."""
        pass

    def _on_device_changed(self, *_args):
        """Called when devices are added or removed."""
        pass

    def _get_bluetooth_status_icon(self) -> str:
        """Get icon representing current bluetooth status."""
        if not self.bluetooth_client:
            return icons.bluetooth_off

        if not self.bluetooth_client.enabled:
            return icons.bluetooth_off
        elif self.bluetooth_client.connected_devices:
            return icons.bluetooth_connected
        elif self.bluetooth_client.scanning:
            return icons.loader
        else:
            return icons.bluetooth

    def _format_bluetooth_status(self) -> tuple[str, str]:
        """Get formatted bluetooth status title and subtitle."""
        if not self.bluetooth_client:
            return "Bluetooth Unavailable", "Bluetooth service not available"

        if not self.bluetooth_client.enabled:
            return "Bluetooth Disabled", "Click to enable Bluetooth"

        connected_devices = self.bluetooth_client.connected_devices
        if connected_devices:
            if len(connected_devices) == 1:
                device = connected_devices[0]
                battery_info = ""
                if device.battery_percentage > 0:
                    battery_info = f" ({device.battery_percentage:.0f}%)"
                return f"Connected to {device.alias}", f"Device: {device.type}{battery_info}"
            else:
                return f"Connected to {len(connected_devices)} devices", "Multiple devices connected"
        elif self.bluetooth_client.scanning:
            return "Scanning for devices...", "Looking for nearby Bluetooth devices"
        else:
            return "Bluetooth Enabled", "No devices connected"

    def _get_device_icon(self, device: BluetoothDevice) -> str:
        """Get appropriate icon for a bluetooth device based on its type."""
        device_type = device.type.lower()

        if "audio" in device_type or "headphone" in device_type or "headset" in device_type:
            return icons.headphones
        elif "mouse" in device_type or "keyboard" in device_type:
            return icons.keyboard
        elif "phone" in device_type:
            return icons.bluetooth
        else:
            return icons.bluetooth

    def _toggle_bluetooth(self):
        """Toggle Bluetooth on/off and keep launcher open."""
        if self.bluetooth_client:
            self.bluetooth_client.toggle_power()
            # Force launcher refresh to show updated status
            self._force_launcher_refresh()
        return None  # Keep launcher open

    def _scan_devices(self):
        """Scan for available devices and keep launcher open (like network plugin)."""
        if self.bluetooth_client:
            # Start scanning
            self.bluetooth_client.scan()

            # Cancel any existing auto-stop timeout
            if self._scan_timeout_id:
                try:
                    from gi.repository import GLib
                    GLib.source_remove(self._scan_timeout_id)
                    self._scan_timeout_id = None
                except Exception:
                    pass

            # Auto-stop scanning after 30 seconds to prevent continuous scanning
            try:
                from gi.repository import GLib

                def auto_stop_scan():
                    if self.bluetooth_client and self.bluetooth_client.scanning:
                        print("Auto-stopping bluetooth scan after 30 seconds...")
                        self.bluetooth_client.scanning = False
                    self._scan_timeout_id = None
                    return False  # Don't repeat

                # Schedule auto-stop after 30 seconds
                self._scan_timeout_id = GLib.timeout_add_seconds(30, auto_stop_scan)

            except Exception as e:
                print(f"Could not schedule auto-stop scan: {e}")

        return None  # Keep launcher open

    def _stop_scanning(self):
        """Stop bluetooth scanning."""
        if self.bluetooth_client and self.bluetooth_client.scanning:
            print("Stopping bluetooth scanning...")
            self.bluetooth_client.scanning = False

        # Cancel any pending auto-stop timeout
        if self._scan_timeout_id:
            try:
                from gi.repository import GLib
                GLib.source_remove(self._scan_timeout_id)
                self._scan_timeout_id = None
            except Exception:
                pass

        return None  # Keep launcher open

    def _check_and_stop_inactive_scanning(self):
        """Check if plugin is inactive and stop scanning if needed."""
        if not self.bluetooth_client or not self.bluetooth_client.scanning:
            return

        # Stop scanning if plugin hasn't been used for 10 seconds
        import time
        current_time = time.time()
        if current_time - self._last_query_time > 10:
            print("Stopping bluetooth scan due to inactivity...")
            self._stop_scanning()

    def _connect_device(self, device: BluetoothDevice):
        """Connect to a bluetooth device."""
        if device and not device.connected:
            print(f"Connecting to {device.alias}...")
            device.connected = True  # This will trigger the connection
            # Force launcher refresh to show updated status
            self._force_launcher_refresh()
        return None  # Keep launcher open

    def _disconnect_device(self, device: BluetoothDevice):
        """Disconnect from a bluetooth device."""
        if device and device.connected:
            print(f"Disconnecting from {device.alias}...")
            device.connected = False  # This will trigger the disconnection
            # Force launcher refresh to show updated status
            self._force_launcher_refresh()
        return None  # Keep launcher open

    def _create_connect_action(self, device: BluetoothDevice):
        """Create a connect action function with proper closure."""
        def connect_action():
            return self._connect_device(device)
        return connect_action

    def _create_disconnect_action(self, device: BluetoothDevice):
        """Create a disconnect action function with proper closure."""
        def disconnect_action():
            return self._disconnect_device(device)
        return disconnect_action

    def _force_launcher_refresh(self):
        """Force the launcher to refresh and show updated bluetooth status."""
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
                                current_query = "bt list"

                            # Force a search which will refresh the results
                            launcher._perform_search(current_query)
                            return False

                    # Fallback: try to find launcher instance through other means
                    import gc
                    for obj in gc.get_objects():
                        if hasattr(obj, '__class__') and obj.__class__.__name__ == 'Launcher':
                            if hasattr(obj, '_perform_search') and hasattr(obj, 'query'):
                                current_query = obj.query if obj.query else "bt list"
                                obj._perform_search(current_query)
                                return False

                except Exception as e:
                    print(f"Error forcing launcher refresh: {e}")

                return False  # Don't repeat

            # Use a small delay to ensure the bluetooth action completes first
            GLib.timeout_add(100, trigger_refresh)

        except Exception as e:
            print(f"Could not trigger refresh: {e}")

    def query(self, query_string: str) -> List[Result]:
        """Process bluetooth queries."""
        # Update last query time to track plugin activity
        import time
        self._last_query_time = time.time()

        # Schedule periodic check for inactive scanning
        try:
            from gi.repository import GLib
            GLib.timeout_add_seconds(15, lambda: (self._check_and_stop_inactive_scanning(), False))
        except Exception:
            pass

        results = []
        query = query_string.strip()
        query_lower = query.lower()

        if not query_lower:
            # Check if bluetooth client is available
            if not self.bluetooth_client:
                results.append(
                    Result(
                        title="Bluetooth Service Unavailable",
                        subtitle="Bluetooth service is not available",
                        icon_markup=icons.bluetooth_off,
                        action=lambda: None,
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "error"},
                    )
                )
                return results

            # Show current bluetooth status
            title, subtitle = self._format_bluetooth_status()
            status_icon = self._get_bluetooth_status_icon()

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
            if self.bluetooth_client.enabled:
                results.append(
                    Result(
                        title="Disable Bluetooth",
                        subtitle="Turn off Bluetooth adapter",
                        icon_markup=icons.bluetooth_off,
                        action=lambda: self._toggle_bluetooth(),
                        relevance=0.9,
                        plugin_name=self.display_name,
                        data={"type": "toggle", "keep_launcher_open": True},
                    )
                )


            else:
                results.append(
                    Result(
                        title="Enable Bluetooth",
                        subtitle="Turn on Bluetooth adapter",
                        icon_markup=icons.bluetooth,
                        action=lambda: self._toggle_bluetooth(),
                        relevance=0.9,
                        plugin_name=self.display_name,
                        data={"type": "toggle", "keep_launcher_open": True},
                    )
                )

            return results

        # Handle specific queries
        if query_lower in ["list", "devices"]:
            if not self.bluetooth_client or not self.bluetooth_client.enabled:
                results.append(
                    Result(
                        title="Bluetooth Disabled",
                        subtitle="Enable Bluetooth to see devices",
                        icon_markup=icons.bluetooth_off,
                        action=lambda: self._toggle_bluetooth(),
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "enable", "keep_launcher_open": True},
                    )
                )
                return results

            # Automatically scan when listing devices (like network plugin)
            self._scan_devices()

            devices = self.bluetooth_client.devices

            # Show scanning message if no devices available yet (like network plugin)
            if not devices:
                results.append(
                    Result(
                        title="Scanning for Devices...",
                        subtitle="Please wait while scanning for Bluetooth devices",
                        icon_markup=icons.radar,
                        action=lambda: None,  # Don't close launcher
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "scanning", "keep_launcher_open": True},
                    )
                )
            else:
                # Show all devices (limit to 10 like network plugin)
                for device in devices[:10]:
                    device_icon = self._get_device_icon(device)

                    # Add connection icon for connected devices
                    if device.connected:
                        title = f"🔗 {device.alias}"
                    else:
                        title = device.alias

                    if device.connected:
                        battery_info = ""
                        if device.battery_percentage > 0:
                            battery_info = f" • {device.battery_percentage:.0f}%"

                        subtitle = f"Connected • {device.type}{battery_info}"
                        action = self._create_disconnect_action(device)
                        relevance = 1.0
                    elif device.connecting:
                        subtitle = f"Connecting... • {device.type}"
                        action = lambda: None
                        relevance = 0.9
                    else:
                        subtitle = f"Disconnected • {device.type} • Click to connect"
                        action = self._create_connect_action(device)
                        relevance = 0.8

                    results.append(
                        Result(
                            title=title,
                            subtitle=subtitle,
                            icon_markup=device_icon,
                            action=action,
                            relevance=relevance,
                            plugin_name=self.display_name,
                            data={
                                "type": "device",
                                "device_address": device.address,
                                "device_name": device.alias,
                                "connected": device.connected,
                                "keep_launcher_open": True
                            },
                        )
                    )

            return results

        # Handle power/toggle commands
        if query_lower in ["toggle"]:
            if not self.bluetooth_client:
                return results

            if self.bluetooth_client.enabled:
                results.append(
                    Result(
                        title="Disable Bluetooth",
                        subtitle="Turn off Bluetooth adapter",
                        icon_markup=icons.bluetooth_off,
                        action=lambda: self._toggle_bluetooth(),
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "toggle", "keep_launcher_open": True},
                    )
                )
            else:
                results.append(
                    Result(
                        title="Enable Bluetooth",
                        subtitle="Turn on Bluetooth adapter",
                        icon_markup=icons.bluetooth,
                        action=lambda: self._toggle_bluetooth(),
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "toggle", "keep_launcher_open": True},
                    )
                )

            return results



        # Search for devices by name (like network plugin search)
        if self.bluetooth_client and self.bluetooth_client.enabled:
            devices = self.bluetooth_client.devices
            matching_devices = [
                device for device in devices
                if query_lower in device.alias.lower() or query_lower in device.name.lower()
            ]

            if matching_devices:
                # Show matching devices (limit to 5 like network plugin)
                for device in matching_devices[:5]:
                    device_icon = self._get_device_icon(device)

                    # Add connection icon for connected devices
                    if device.connected:
                        title = f"🔗 {device.alias}"
                    else:
                        title = device.alias

                    if device.connected:
                        battery_info = ""
                        if device.battery_percentage > 0:
                            battery_info = f" • {device.battery_percentage:.0f}%"

                        subtitle = f"Connected • {device.type}{battery_info}"
                        action = self._create_disconnect_action(device)
                        relevance = 1.0
                    elif device.connecting:
                        subtitle = f"Connecting... • {device.type}"
                        action = lambda: None
                        relevance = 0.9
                    else:
                        subtitle = f"Disconnected • {device.type} • Click to connect"
                        action = self._create_connect_action(device)
                        relevance = 0.9

                    results.append(
                        Result(
                            title=title,
                            subtitle=subtitle,
                            icon_markup=device_icon,
                            action=action,
                            relevance=relevance,
                            plugin_name=self.display_name,
                            data={
                                "type": "device",
                                "device_address": device.address,
                                "device_name": device.alias,
                                "connected": device.connected,
                                "keep_launcher_open": True
                            },
                        )
                    )

                return results
            else:
                # No matching devices found (like network plugin)
                results.append(
                    Result(
                        title=f"No devices matching '{query}'",
                        subtitle="Try scanning for more devices",
                        icon_markup=icons.radar,
                        action=lambda: self._scan_devices(),
                        relevance=0.5,
                        plugin_name=self.display_name,
                        data={"type": "scan", "keep_launcher_open": True},
                    )
                )
                return results

        # Fallback for when Bluetooth is disabled or not available (like network plugin)
        if not self.bluetooth_client or not self.bluetooth_client.enabled:
            results.append(
                Result(
                    title="Bluetooth Not Available",
                    subtitle="Enable Bluetooth to search for devices",
                    icon_markup=icons.bluetooth_off,
                    action=lambda: self._toggle_bluetooth() if self.bluetooth_client else None,
                    relevance=0.5,
                    plugin_name=self.display_name,
                    data={"type": "info"},
                )
            )

        return results