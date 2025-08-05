from gi.repository import NM, GLib
import gi
from typing import List, Optional
from fabric.core.service import Property, Service, Signal
from fabric.utils import bulk_connect, get_enum_member_name, snake_case_to_kebab_case
from loguru import logger

gi.require_version("NM", "1.0")  # Ensure the correct version is loaded


class NetworkClient(Service):
    """A service to manage network devices"""

    @Signal
    def wifi_device_added(self) -> None: ...

    @Signal
    def ethernet_device_added(self) -> None: ...

    @Signal
    def wifi_device_removed(self) -> None: ...

    @Signal
    def ethernet_device_removed(self) -> None: ...

    @Signal
    def changed(self) -> None: ...

    @Property(list, "readable")
    def connections(self) -> Optional[list]:
        """Returns the active connections, if available."""
        return self._client.get_property("connections") if self._client else None

    @Property(object, "readable")
    def wifi_device(self) -> Optional[object]:
        """Returns the WiFi device if available."""
        return self._wifi_device

    @Property(object, "readable")
    def ethernet_device(self) -> Optional[object]:
        """Returns the Ethernet device if available."""
        return self._ethernet_device

    @Property(str, "readable")
    def primary_connection(self) -> Optional[str]:
        """Returns the primary connection if available."""
        return self._client.get_property("primary_connection") if self._client else None

    @Property(str, "readable")
    def active_connection(self) -> Optional[str]:
        """Returns the active connection if available."""
        return self._client.get_property("active_connection") if self._client else None

    @Property(str, "readable")
    def state(self) -> str:
        """Returns the current network state."""
        if not self._client:
            return "disconnected"
        return snake_case_to_kebab_case(
            get_enum_member_name(
                self._client.get_property("state"), default="disconnected"
            )
        )

    @Property(str, "readable")
    def connectivity(self) -> str:
        """Returns the connectivity state."""
        if not self._client:
            return "disconnected"
        return snake_case_to_kebab_case(
            get_enum_member_name(
                self._client.get_property("connectivity"), default="disconnected"
            )
        )

    @Property(list, "readable")
    def devices(self) -> Optional[list]:
        """Returns the list of network devices if available."""
        return self._client.get_property("devices") if self._client else None

    @Property(str, "readable")
    def hostname(self) -> Optional[str]:
        """Returns the hostname if available."""
        return self._client.get_property("hostname") if self._client else None

    @Property(bool, "read-write", default_value=False)
    def networking_enabled(self) -> bool:
        """Checks if networking is enabled."""
        return (
            self._client.get_property("networking_enabled") if self._client else False
        )

    @networking_enabled.setter
    def networking_enabled(self, value: bool):
        """Sets the networking state if the client is available."""
        if self._client:
            self._client.set_property("networking_enabled", value)

    @Property(bool, "read-write", default_value=False)
    def wireless_enabled(self) -> bool:
        """Checks if wireless networking is enabled."""
        return self._client.get_property("wireless_enabled") if self._client else False

    @wireless_enabled.setter
    def wireless_enabled(self, value: bool):
        """Sets the wireless networking state if the client is available."""
        if self._client:
            self._client.set_property("wireless_enabled", value)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._client: NM.Client = None
        self._wifi_device: Wifi | None = None
        self._ethernet_device: Ethernet | None = None

        logger.info("[Network] Initializing client asynchronously...")

        # Start async NM client initialization
        NM.Client.new_async(None, self.on_client_ready)

    def on_client_ready(self, source, result):
        """Callback when NM.Client is ready."""
        try:
            self._client = NM.Client.new_finish(result)  # Retrieve client instance
            logger.info("[Network] NM.Client initialized successfully!")

            # Connect signals
            bulk_connect(
                self._client,
                {
                    "device-added": lambda _, device: self.on_device_added(
                        device=device
                    ),
                    "device-removed": lambda _, device: self.on_device_removed(
                        device=device
                    ),
                    "notify::state": lambda *args: self.notifier("state"),
                    "notify::networking-enabled": lambda *args: self.notifier(
                        "networking-enabled"
                    ),
                    "notify::wireless-enabled": lambda *args: self.notifier(
                        "wireless-enabled"
                    ),
                    # "notify::primary-connection": lambda *args: self.notifier('primary-connection'),
                    # "notify::active-connection": lambda *args: self.notifier('active-connection'),
                    # "active-connection-added": lambda *args: self.emit("changed"),
                    # "active-connection-removed": lambda *args: self.emit("changed")
                },
            )

            # Process devices AFTER client is ready
            for device in self.do_get_raw_devices():
                self.on_device_added(device=device)

            self.notify("state")
            self.notify("networking-enabled")
            self.notify("wireless-enabled")

        except Exception as e:
            logger.error(f"[Network] Error initializing NM.Client: {e}")

    def do_get_raw_devices(self) -> list[NM.Device]:
        return [
            dev
            for dev in self.devices
            if dev.get_device_type() in (NM.DeviceType.WIFI, NM.DeviceType.ETHERNET)
        ]

    def on_device_added(self, device):
        device_type = device.get_device_type()
        if device_type == NM.DeviceType.WIFI and not self._wifi_device:
            logger.info("[Network] WiFi device detected, initializing...")
            self._wifi_device = Wifi(client=self, device=device)
            self.wifi_device_added.emit()

        elif device_type == NM.DeviceType.ETHERNET and not self._ethernet_device:
            logger.info("[Network] Ethernet device detected, initializing...")
            self._ethernet_device = Ethernet(client=self, device=device)
            self.ethernet_device_added.emit()

    def on_device_removed(self, device):
        if device == self._wifi_device:
            logger.info("[Network] WiFi device removed.")
            self._wifi_device = None
            self.wifi_device_removed.emit()

        elif device == self._ethernet_device:
            logger.info("[Network] Ethernet device removed.")
            self._ethernet_device = None
            self.ethernet_device_removed.emit()

    def toggle_network(self):
        """Enable or disable Network"""
        self.networking_enabled = not self.networking_enabled

    def deactivate_connection(self, connection):
        """Disconnect"""
        self._client.deactivate_connection_async(connection, None, None)

    def notifier(self, name):
        self.notify(name)
        self.emit("changed")


class AccessPoint(Service):
    """A service to manage access points"""

    @Signal
    def changed(self) -> None: ...

    @Property(object, "readable")
    def device(self) -> object:
        return self._device

    @Property(int, "readable")
    def strength(self) -> int:
        return self._ap.get_property("strength")

    @Property(int, "readable")
    def frequency(self) -> int:
        return self._ap.get_property("frequency")

    @Property(str, "readable")
    def bssid(self) -> str:
        return self._ap.get_property("bssid") if self._ap else None

    @Property(str, "readable")
    def hw_address(self) -> str:
        return self._ap.get_property("hw_address")

    @Property(str, "readable")
    def ssid(self) -> str:
        ssid = self._ap.get_ssid()
        return NM.utils_ssid_to_utf8(ssid.get_data()) if ssid else "Unknown"

    @Property(str, "readable")
    def icon(self) -> str:
        return {
            80: "network-wireless-signal-excellent-symbolic",
            60: "network-wireless-signal-good-symbolic",
            40: "network-wireless-signal-ok-symbolic",
            20: "network-wireless-signal-weak-symbolic",
            00: "network-wireless-signal-none-symbolic",
        }.get(
            min(80, 20 * round(self.strength / 20)),
            "network-wireless-no-route-symbolic",
        )

    @Property(bool, "readable", default_value=False)
    def requires_password(self) -> bool:
        ssid = self.ssid
        settings = self._client.connections
        connection = None
        for setting in settings:
            wifi_setting = setting.get_setting_wireless()
            if (
                wifi_setting
                and NM.utils_ssid_to_utf8(wifi_setting.get_ssid().get_data()) == ssid
            ):
                connection = setting
                break
        if not connection:
            return bool(self._ap.get_wpa_flags() or self._ap.get_rsn_flags())
        return False

    @Property(bool, "readable", default_value=False)
    def is_active(self) -> bool:
        if self._device.active_access_point:
            return self.bssid == self._device.active_access_point.get_bssid()
        return False

    def __init__(self, device: "Wifi", ap: NM.AccessPoint, **kwargs):
        super().__init__(**kwargs)
        self._client: NetworkClient = device.client
        self._device: Wifi = device
        self._ap: NM.AccessPoint = ap

        self._ap.connect("notify::strength", lambda *args: self.notifier("strength"))
        self._device.connect(
            "notify::active-access-point", lambda *args: self.notifier("is-active")
        )

    def notifier(self, name: str, *args):
        self.notify(name)
        self.emit("changed")
        return


class Wifi(Service):
    """A service to manage wifi devices"""

    @Signal
    def changed(self) -> None: ...

    @Signal
    def ap_added(self, ap: AccessPoint) -> None: ...

    @Signal
    def ap_removed(self, ap: AccessPoint) -> None: ...

    @Property(NetworkClient, "readable")
    def client(self) -> NetworkClient:
        """Returns the client"""
        return self._client

    @Property(bool, "read-write", default_value=False)
    def wireless_enabled(self) -> bool:
        """Returns if the wifi is enabled"""
        return self._client.get_property("wireless_enabled")

    @wireless_enabled.setter
    def wireless_enabled(self, value: bool):
        return self._client.set_property("wireless_enabled", value)

    @Property(list[AccessPoint], "readable")
    def access_points(self) -> list[AccessPoint]:
        return sorted(
            self._access_points.values(), key=lambda x: x.is_active, reverse=True
        )

    @Property(AccessPoint, "readable")
    def active_access_point(self) -> Optional[AccessPoint]:
        return self._active_access_point

    def __init__(self, client: NetworkClient, device: NM.DeviceWifi, **kwargs):
        super().__init__(**kwargs)
        self._client: NetworkClient = client
        self._device: NM.DeviceWifi = device
        self._active_access_point: NM.AccessPoint | None = None
        self._access_points: dict[str, AccessPoint] = {}

        bulk_connect(
            self._device,
            {
                "notify::active-access-point": lambda *args: self.on_access_point_activated(),
                "access-point-added": lambda _, ap: self.on_access_point_added(ap=ap),
                "access-point-removed": lambda _, ap: self.on_access_point_removed(
                    ap=ap
                ),
                # "state-changed": lambda device, new, old, reason: self.on_state_changed(new),
            },
        )

        self._client.connect(
            "notify::wireless-enabled", lambda *args: self.notifier("wireless-enabled")
        )

        for ap in self.do_get_access_points():
            self.on_access_point_added(ap=ap)

        self.on_access_point_activated()

    def on_state_changed(self, state):
        self.emit("changed")

    def do_get_access_points(self):
        return self._device.get_access_points()

    def on_access_point_added(self, ap):
        ssid = ap.get_ssid()
        ssid = NM.utils_ssid_to_utf8(ssid.get_data()) if ssid else "Unknown"

        access_point: AccessPoint = AccessPoint(ap=ap, device=self)

        self._access_points[ssid] = access_point

        self.ap_added.emit(access_point)

        # self.notifier("access-points")

        logger.info(f"[Wifi] New access point added with ssid: {ssid}")

    def on_access_point_removed(self, ap):
        ssid = ap.get_ssid()
        ssid = NM.utils_ssid_to_utf8(ssid.get_data()) if ssid else "Unknown"

        if not (access_point := self._access_points.pop(ssid, None)):
            return logger.warning(
                f"[Network] tried to remove a unknwon access point with ssid {ssid}"
            )

        self.ap_removed.emit(access_point)

        logger.info(f"[Wifi] Access point with ssid: {ssid} removed.")

    def on_access_point_activated(self):
        if self._device.get_active_access_point():
            self._active_access_point: AccessPoint = AccessPoint(
                ap=self._device.get_active_access_point(), device=self
            )

        else:
            self._active_access_point = None

        self.notifier("active-access-point")

        logger.info("[Wifi] New active connection")

    def disconnect_wifi(self):
        """Disconnect from the current WiFi network."""
        active_connection = self._device.get_active_connection()
        self._client.deactivate_connection(active_connection)
        logger.info("[Wifi] Wifi network disconnected")

    def scan(self):
        self._device.request_scan_async(
            None,
            lambda device, result: [
                device.request_scan_finish(result),
                self.notifier("access-points"),
            ],
        )
        logger.info("[Wifi] Scan started")

    def toggle_wifi(self):
        """Enable or disable WiFi"""
        self.wireless_enabled = not self.wireless_enabled

    def connect_to_wifi(self, ap: AccessPoint, password: str = None, callback=None):
        """Connect to a WiFi network."""

        ssid = ap.ssid

        if ssid == "Unknown":
            logger.error("Invalid access point data")
            if callback:
                callback(False, "Invalid access point data")
            return False

        logger.info(f"Connecting to WiFi SSID: {ssid}")

        # Check for existing connections
        settings = self._client.connections
        connection = None

        for setting in settings:
            wifi_setting = setting.get_setting_wireless()
            if (
                wifi_setting
                and NM.utils_ssid_to_utf8(wifi_setting.get_ssid().get_data()) == ssid
            ):
                connection = setting
                break

        def on_activation_result(client, result):
            """Handle the result of connection activation"""
            try:
                active_connection = client.activate_connection_finish(result)
                if active_connection:
                    logger.info(f"Successfully connected to '{ssid}'")
                    if callback:
                        callback(True, "Connected successfully")
                else:
                    logger.error(f"Failed to connect to '{ssid}'")
                    if callback:
                        callback(False, "Failed to connect. Please try again.")
            except Exception as e:
                error_msg = str(e).lower()
                logger.error(f"Connection to '{ssid}' failed: {e}")

                # Parse NetworkManager error messages and provide user-friendly responses
                if "802-11-wireless-security" in error_msg:
                    if "property is invalid" in error_msg or "psk" in error_msg:
                        user_msg = "Incorrect password. Please try again."
                    else:
                        user_msg = "Security configuration error. Please try again."
                elif "secrets were required" in error_msg or "no secrets" in error_msg:
                    user_msg = "Incorrect password. Please try again."
                elif "timeout" in error_msg:
                    user_msg = "Connection timeout. Please try again."
                elif "not found" in error_msg or "no such device" in error_msg:
                    user_msg = "Network not available. Please try again."
                elif "already connected" in error_msg:
                    user_msg = "Already connected to this network."
                else:
                    user_msg = "Failed to connect. Please try again."

                if callback:
                    callback(False, user_msg)

        if not connection:
            # Create a new connection profile
            logger.info(f"Creating new WiFi connection for SSID '{ssid}'")
            connection = NM.SimpleConnection.new()

            # Required connection settings
            s_con = NM.SettingConnection.new()
            s_con.set_property(NM.SETTING_CONNECTION_ID, ssid)
            s_con.set_property(NM.SETTING_CONNECTION_TYPE, "802-11-wireless")
            s_con.set_property(
                NM.SETTING_CONNECTION_INTERFACE_NAME, self._device.get_iface()
            )  # Set interface name
            connection.add_setting(s_con)

            # Wireless settings
            s_wifi = NM.SettingWireless.new()
            s_wifi.set_property(NM.SETTING_WIRELESS_SSID, GLib.Bytes.new(ssid.encode()))
            s_wifi.set_property(
                NM.SETTING_WIRELESS_MODE, "infrastructure"
            )  # Ensure mode is correct
            connection.add_setting(s_wifi)

            # Security settings (only if password is required and provided)
            if ap.requires_password:
                if not password:
                    logger.error("Password required but not provided")
                    if callback:
                        callback(False, "Password required but not provided")
                    return False

                s_sec = NM.SettingWirelessSecurity.new()
                s_sec.set_property(NM.SETTING_WIRELESS_SECURITY_KEY_MGMT, "wpa-psk")
                s_sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
                connection.add_setting(s_sec)

            # IPv4 settings
            s_ipv4 = NM.SettingIP4Config.new()
            s_ipv4.set_property("method", "auto")
            connection.add_setting(s_ipv4)

            # IPv6 settings
            s_ipv6 = NM.SettingIP6Config.new()
            s_ipv6.set_property("method", "auto")
            connection.add_setting(s_ipv6)

            # Callback for async connection
            def on_connection_added(client, result):
                try:
                    new_connection = client.add_connection_finish(result)
                    if not new_connection:
                        logger.error(f"Failed to create connection for '{ssid}'")
                        if callback:
                            callback(
                                False, "Failed to create connection. Please try again."
                            )
                        return

                    logger.info(f"Connection for '{ssid}' added successfully")

                    # Now activate the newly created connection
                    client.activate_connection_async(
                        new_connection, self._device, None, None, on_activation_result
                    )
                except Exception as e:
                    error_msg = str(e).lower()
                    logger.error(f"Failed to add connection: {e}")

                    # Parse connection creation errors and provide user-friendly responses
                    if "802-11-wireless-security" in error_msg:
                        if "property is invalid" in error_msg or "psk" in error_msg:
                            user_msg = "Incorrect password. Please try again."
                        else:
                            user_msg = "Security configuration error. Please try again."
                    elif "invalid" in error_msg or "property" in error_msg:
                        user_msg = "Invalid network configuration. Please try again."
                    else:
                        user_msg = "Failed to connect. Please try again."

                    if callback:
                        callback(False, user_msg)

            # Save the new connection
            self._client._client.add_connection_async(
                connection, True, None, on_connection_added
            )
        else:
            # Activate existing connection
            self._client._client.activate_connection_async(
                connection, self._device, None, None, on_activation_result
            )

        return True

    def notifier(self, name: str, *args):
        self.notify(name)
        self.emit("changed")
        return


class Ethernet(Service):
    """A service to manage ethernet devices"""

    @Signal
    def changed(self) -> None: ...

    @Signal
    def enabled(self) -> bool: ...

    @Property(int, "readable")
    def speed(self) -> str:
        speed_mbps = self._device.get_speed()
        return f"{speed_mbps} Mb/s"

    @Property(str, "readable")
    def state(self) -> str:
        return snake_case_to_kebab_case(
            get_enum_member_name(self._device.get_state(), default="disconnected")
        )

    @Property(str, "readable")
    def internet(self) -> str:
        if self._active_connection:
            return snake_case_to_kebab_case(
                get_enum_member_name(
                    self._active_connection.get_state(), default="disconnected"
                )
            )
        return "disconnected"

    @Property(str, "readable")
    def iface(self) -> str:
        return self._device.get_iface() if self._device else None

    @Property(str, "readable")
    def icon_name(self) -> str:
        network = self.internet
        if network == "activated":
            return "network-wired-symbolic"
        elif network == "activating":
            return "network-wired-acquiring-symbolic"
        return "network-wired-disconnected-symbolic"

    def __init__(self, client: NM.Client, device: NM.DeviceEthernet, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client: NM.Client = client
        self._device: NM.DeviceEthernet = device
        self._active_connection = None

        self._device.connect(
            "state-changed", lambda *args: self.on_network_state_changed()
        )

        self.update_active_connection()

    def on_network_state_changed(self):
        """Called when networking is toggled on/off."""
        if self.state != "unmanaged":
            # Re-initialize device when networking is re-enabled
            self.update_active_connection()
        else:
            self._active_connection = None

    def update_active_connection(self):
        """Updates the active connection and connects to its state change signal."""
        active_connection = self._device.get_active_connection()
        if active_connection:
            self._active_connection = active_connection
            self._active_connection.connect(
                "state-changed", lambda *args: self.emit("changed")
            )

    def get_network_stats(self):
        """Fetch received and transmitted bytes from the system files"""
        try:
            # Read data from /sys/class/net for accurate speed
            with open(
                f"/sys/class/net/{self.iface}/statistics/rx_bytes", "r"
            ) as rx_file:
                rx_bytes = int(rx_file.read().strip())
            with open(
                f"/sys/class/net/{self.iface}/statistics/tx_bytes", "r"
            ) as tx_file:
                tx_bytes = int(tx_file.read().strip())
            return rx_bytes, tx_bytes
        except FileNotFoundError:
            return None, None
