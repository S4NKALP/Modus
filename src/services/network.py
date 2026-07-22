import subprocess
from dataclasses import dataclass, field
from typing import List, Literal

from fabric.core.service import Property, Service, Signal
from fabric.utils import Gio, GLib, logger

from services.bluetooth import _rfkill_soft_blocked

NM_SERVICE = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager"
NM_SETTINGS_PATH = "/org/freedesktop/NetworkManager/Settings"
NM_DEVICE_PATH = "/org/freedesktop/NetworkManager/Device"
NM_WIRELESS_PATH = "/org/freedesktop/NetworkManager/Device/Wireless"
NM_AP_PATH = "/org/freedesktop/NetworkManager/AccessPoint"
NM_ACTIVE_CONN_PATH = "/org/freedesktop/NetworkManager/Connection/Active"
NM_CONN_SETTINGS_PATH = "/org/freedesktop/NetworkManager/Settings/Connection"

NM_IFACE = "org.freedesktop.NetworkManager"
NM_DEVICE_IFACE = "org.freedesktop.NetworkManager.Device"
NM_WIRELESS_IFACE = "org.freedesktop.NetworkManager.Device.Wireless"
NM_AP_IFACE = "org.freedesktop.NetworkManager.AccessPoint"
NM_SETTINGS_IFACE = "org.freedesktop.NetworkManager.Settings"
NM_ACTIVE_CONN_IFACE = "org.freedesktop.NetworkManager.Connection.Active"
NM_CONN_SETTINGS_IFACE = "org.freedesktop.NetworkManager.Settings.Connection"

# DeviceType constants
DEVICE_TYPE_ETHERNET = 1
DEVICE_TYPE_WIFI = 2

# DeviceState constants
DEVICE_STATE_UNMANAGED = 10
DEVICE_STATE_UNAVAILABLE = 20
DEVICE_STATE_DISCONNECTED = 30
DEVICE_STATE_PREPARE = 40
DEVICE_STATE_CONFIG = 50
DEVICE_STATE_NEED_AUTH = 60
DEVICE_STATE_IP_CONFIG = 70
DEVICE_STATE_IP_CHECK = 80
DEVICE_STATE_SECONDARIES = 90
DEVICE_STATE_ACTIVATED = 100
DEVICE_STATE_DEACTIVATING = 110
DEVICE_STATE_FAILED = 120

# ActiveConnectionState constants
AC_STATE_ACTIVATED = 2
AC_STATE_ACTIVATING = 1
AC_STATE_DEACTIVATING = 3
AC_STATE_DEACTIVATED = 0

# ConnectivityState constants
CONNECTIVITY_NONE = 1
CONNECTIVITY_PORTAL = 2
CONNECTIVITY_LIMITED = 3
CONNECTIVITY_FULL = 4

_DEVICE_STATE_NAMES = {
    DEVICE_STATE_UNMANAGED: "unmanaged",
    DEVICE_STATE_UNAVAILABLE: "unavailable",
    DEVICE_STATE_DISCONNECTED: "disconnected",
    DEVICE_STATE_PREPARE: "prepare",
    DEVICE_STATE_CONFIG: "config",
    DEVICE_STATE_NEED_AUTH: "need_auth",
    DEVICE_STATE_IP_CONFIG: "ip_config",
    DEVICE_STATE_IP_CHECK: "ip_check",
    DEVICE_STATE_SECONDARIES: "secondaries",
    DEVICE_STATE_ACTIVATED: "activated",
    DEVICE_STATE_DEACTIVATING: "deactivating",
    DEVICE_STATE_FAILED: "failed",
}

_AC_STATE_NAMES = {
    AC_STATE_ACTIVATED: "activated",
    AC_STATE_ACTIVATING: "activating",
    AC_STATE_DEACTIVATING: "deactivating",
    AC_STATE_DEACTIVATED: "deactivated",
}

_CONNECTIVITY_NAMES = {
    CONNECTIVITY_NONE: "none",
    CONNECTIVITY_PORTAL: "portal",
    CONNECTIVITY_LIMITED: "loss",
    CONNECTIVITY_FULL: "full",
}


def _make_proxy(bus: Gio.DBusConnection, path: str, iface: str) -> Gio.DBusProxy:
    return Gio.DBusProxy.new_sync(
        bus,
        Gio.DBusProxyFlags.NONE,
        None,
        NM_SERVICE,
        path,
        iface,
        None,
    )


def _get(proxy: Gio.DBusProxy, prop: str):
    v = proxy.get_cached_property(prop)
    if v is None:
        return None
    return v.unpack() if isinstance(v, GLib.Variant) else v


def _set(proxy: Gio.DBusProxy, prop: str, value):
    proxy.set_cached_property(prop, value)


def _call(proxy: Gio.DBusProxy, method: str, args=None, flags=0):
    try:
        result = proxy.call_sync(method, args, flags, -1, None)
        return result.unpack() if result else None
    except GLib.Error as e:
        logger.warning(f"[Network] D-Bus call {method} failed: {e}")
        return None


def _ssid_bytes_to_str(data) -> str:
    if data is None:
        return "Unknown"
    if isinstance(data, (bytes, bytearray)):
        return data.decode("utf-8", errors="replace") or "Unknown"
    if isinstance(data, (list, tuple)):
        return bytes(data).decode("utf-8", errors="replace") or "Unknown"
    if isinstance(data, str):
        return data or "Unknown"
    return "Unknown"


def _signal_icon(strength: int) -> str:
    return {
        80: "network-wireless-signal-excellent-symbolic",
        60: "network-wireless-signal-good-symbolic",
        40: "network-wireless-signal-ok-symbolic",
        20: "network-wireless-signal-weak-symbolic",
        0: "network-wireless-signal-none-symbolic",
    }.get(
        min(80, 20 * round(strength / 20)),
        "network-wireless-no-route-symbolic",
    )


@dataclass
class AccessPointData:
    ssid: str
    bssid: str | None
    strength: int
    max_bitrate: int = 0
    frequency: int = 0
    state: str = "unknown"
    requires_password: bool = False
    is_active: bool = False
    working: bool = False
    icon: str = ""
    path: str = "/"
    device_path: str = "/"

    @staticmethod
    def is_better(
        max_bitrate1: int,
        frequency1: int,
        strength1: int,
        max_bitrate2: int,
        frequency2: int,
        strength2: int,
    ) -> bool:
        if max_bitrate1 > max_bitrate2:
            return True
        if max_bitrate1 == max_bitrate2:
            if frequency1 > frequency2:
                return True
            if frequency1 == frequency2:
                return strength1 > strength2
        return False


@dataclass
class ActiveConnectionInfo:
    name: str
    connection_type: Literal["wired", "wifi", "vpn"] = "wired"
    strength: int = -1
    object_path: str = ""

    @property
    def is_vpn(self) -> bool:
        return self.connection_type == "vpn"


@dataclass
class Vpn:
    name: str
    path: str = ""


@dataclass
class KnownConnection:
    connection_type: Literal["access_point", "vpn"] = "access_point"
    access_point: AccessPointData | None = None
    vpn: Vpn | None = None


@dataclass
class NetworkData:
    wifi_present: bool = False
    wireless_access_points: list = field(default_factory=list)
    active_connections: list = field(default_factory=list)
    known_connections: list = field(default_factory=list)
    wifi_enabled: bool = False
    airplane_mode: bool = False
    connectivity: str = "unknown"
    scanning_nearby_wifi: bool = False


class NmProxy:
    """Thin wrapper around Gio.DBusProxy for org.freedesktop.NetworkManager.

    Mirrors the Rust NetworkDbus struct from network/dbus.rs.
    """

    def __init__(self, bus: Gio.DBusConnection):
        self._bus = bus
        self._nm = _make_proxy(bus, NM_PATH, NM_IFACE)
        self._settings = _make_proxy(bus, NM_SETTINGS_PATH, NM_SETTINGS_IFACE)

    # -- NetworkManager properties --

    @property
    def wireless_enabled(self) -> bool:
        return bool(_get(self._nm, "WirelessEnabled"))

    @wireless_enabled.setter
    def wireless_enabled(self, value: bool):
        self._nm.set_cached_property("WirelessEnabled", GLib.Variant("b", value))
        _call(
            self._nm,
            "org.freedesktop.DBus.Properties.Set",
            GLib.Variant(
                "(ssv)",
                (NM_IFACE, "WirelessEnabled", GLib.Variant("b", value)),
            ),
        )

    @property
    def connectivity(self) -> str:
        return _CONNECTIVITY_NAMES.get(_get(self._nm, "Connectivity") or 0, "unknown")

    @property
    def devices(self) -> list[str]:
        return list(_get(self._nm, "Devices") or [])

    @property
    def active_connection_paths(self) -> list[str]:
        return list(_get(self._nm, "ActiveConnections") or [])

    # -- Methods (mirrors Rust proxy methods) --

    def activate_connection(
        self, conn_path: str, device_path: str, specific_path: str = "/"
    ) -> tuple | None:
        return _call(
            self._nm,
            "ActivateConnection",
            GLib.Variant("(ooo)", (conn_path, device_path, specific_path)),
        )

    def add_and_activate_connection(
        self, settings: dict, device_path: str, ap_path: str = "/"
    ) -> tuple | None:
        return _call(
            self._nm,
            "AddAndActivateConnection",
            GLib.Variant("(sa{sv}ss)", ("", settings, device_path, ap_path)),
        )

    def deactivate_connection(self, active_conn_path: str) -> bool:
        return (
            _call(
                self._nm,
                "DeactivateConnection",
                GLib.Variant("(o)", (active_conn_path,)),
            )
            is True
        )

    #  Device enumeration

    def wifi_devices(self) -> list[str]:
        return [d for d in self.devices if self._device_type(d) == DEVICE_TYPE_WIFI]

    def ethernet_devices(self) -> list[str]:
        return [d for d in self.devices if self._device_type(d) == DEVICE_TYPE_ETHERNET]

    def wifi_device_present(self) -> bool:
        return len(self.wifi_devices()) > 0

    def _device_type(self, path: str) -> int:
        proxy = _make_proxy(self._bus, path, NM_DEVICE_IFACE)
        return _get(proxy, "DeviceType") or 0

    #  Access points

    def wireless_access_points(self) -> list[AccessPointData]:
        """Get all wireless access points across all wifi devices.

        Port of dbus.rs wireless_access_points().
        """
        aps: dict[str, AccessPointData] = {}
        for dev_path in self.wifi_devices():
            wdev = _make_proxy(self._bus, dev_path, NM_WIRELESS_IFACE)
            ap_paths = _get(wdev, "AccessPoints") or []
            device_state = self._device_state_name(dev_path)
            active_ap_path = _get(wdev, "ActiveAccessPoint")

            for ap_path in ap_paths:
                is_active = ap_path == active_ap_path
                ap = self._read_ap(ap_path, dev_path, device_state, is_active)
                if ap is None:
                    continue
                # Deduplicate by ssid, keep best (mirrors Rust logic)
                existing = aps.get(ap.ssid)
                if existing and AccessPointData.is_better(
                    existing.max_bitrate,
                    existing.frequency,
                    existing.strength,
                    ap.max_bitrate,
                    ap.frequency,
                    ap.strength,
                ):
                    continue
                aps[ap.ssid] = ap

        return sorted(aps.values(), key=lambda a: a.strength, reverse=True)

    def _read_ap(
        self, ap_path: str, dev_path: str, device_state: str, is_active: bool = False
    ) -> AccessPointData | None:
        try:
            proxy = _make_proxy(self._bus, ap_path, NM_AP_IFACE)
            ssid_data = _get(proxy, "Ssid")
            ssid = _ssid_bytes_to_str(ssid_data)
            if ssid == "Unknown":
                return None
            strength = _get(proxy, "Strength") or 0
            flags = _get(proxy, "Flags") or 0
            return AccessPointData(
                ssid=ssid,
                bssid=None,
                strength=strength,
                max_bitrate=_get(proxy, "MaxBitrate") or 0,
                frequency=_get(proxy, "Frequency") or 0,
                state=device_state,
                requires_password=flags != 0,
                icon=_signal_icon(strength),
                path=ap_path,
                device_path=dev_path,
                is_active=is_active,
            )
        except GLib.Error as e:
            logger.debug(f"[Network] Failed to read AP {ap_path}: {e}")
            return None

    def _device_state_name(self, dev_path: str) -> str:
        proxy = _make_proxy(self._bus, dev_path, NM_DEVICE_IFACE)
        state = _get(proxy, "State") or 0
        return _DEVICE_STATE_NAMES.get(state, "unknown")

    def active_access_point_path(self, dev_path: str) -> str | None:
        wdev = _make_proxy(self._bus, dev_path, NM_WIRELESS_IFACE)
        return _get(wdev, "ActiveAccessPoint")

    def active_connections_info(self) -> list[ActiveConnectionInfo]:
        """Get info about active connections.

        Port of dbus.rs active_connections_info().
        """
        result: list[ActiveConnectionInfo] = []
        for ac_path in self.active_connection_paths:
            try:
                ac = _make_proxy(self._bus, ac_path, NM_ACTIVE_CONN_IFACE)
                conn_type = _get(ac, "Type") or ""
                name = _get(ac, "Id") or ""

                if _get(ac, "Vpn"):
                    result.append(
                        ActiveConnectionInfo(
                            name=name, connection_type="vpn", object_path=ac_path
                        )
                    )
                    continue

                is_vpn = "vpn" in conn_type.lower()
                if is_vpn:
                    result.append(
                        ActiveConnectionInfo(
                            name=name, connection_type="vpn", object_path=ac_path
                        )
                    )
                    continue

                is_wireless = "wireless" in conn_type
                if is_wireless:
                    strength = -1
                    for dev_path in _get(ac, "Devices") or []:
                        if self._device_type(dev_path) == DEVICE_TYPE_WIFI:
                            ap_path = self.active_access_point_path(dev_path)
                            if ap_path:
                                ap = _make_proxy(self._bus, ap_path, NM_AP_IFACE)
                                strength = _get(ap, "Strength") or 0
                    result.append(
                        ActiveConnectionInfo(
                            name=name, connection_type="wifi", strength=strength
                        )
                    )
                elif "wireguard" in conn_type.lower():
                    result.append(
                        ActiveConnectionInfo(
                            name=name, connection_type="vpn", object_path=ac_path
                        )
                    )
                else:
                    result.append(
                        ActiveConnectionInfo(name=name, connection_type="wired")
                    )
            except GLib.Error as e:
                logger.debug(
                    f"[Network] Failed to read active connection {ac_path}: {e}"
                )

        result.sort(
            key=lambda c: {"vpn": 0, "wired": 1, "wifi": 2}.get(c.connection_type, 3)
        )
        return result

    def request_scan(self, dev_path: str) -> bool:
        try:
            wdev = _make_proxy(self._bus, dev_path, NM_WIRELESS_IFACE)
            wdev.call_sync(
                "RequestScan",
                GLib.Variant("(a{sv})", ({},)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            return True
        except GLib.Error as e:
            logger.warning(f"[Network] Scan request failed for {dev_path}: {e}")
            return False

    def scan_nearby_wifi(self) -> list[str]:
        """Request scan on all wireless devices. Returns paths of devices that accepted."""
        requested: list[str] = []
        for dev_path in self.wifi_devices():
            if self.request_scan(dev_path):
                requested.append(dev_path)
        return requested

    # Known connections

    def known_connections(
        self, wireless_aps: list[AccessPointData] | None = None
    ) -> list[KnownConnection]:
        known_ssid: list[str] = []
        known_vpn: list[Vpn] = []
        conn_paths = _get(self._settings, "Connections") or []

        for conn_path in conn_paths:
            try:
                cs = _make_proxy(self._bus, conn_path, NM_CONN_SETTINGS_IFACE)
                settings = _call(cs, "GetSettings")
                if not settings:
                    continue
                # settings is a{sa{sv}} — dict of section -> dict of key -> variant
                if isinstance(settings, tuple) and settings:
                    settings = settings[0]
                sections = settings if isinstance(settings, dict) else {}

                if "802-11-wireless" in sections:
                    conn_section = sections.get("connection", {})
                    conn_id = conn_section.get("id")
                    if isinstance(conn_id, GLib.Variant):
                        conn_id = conn_id.unpack()
                    if conn_id:
                        known_ssid.append(str(conn_id))
                elif "vpn" in sections or "wireguard" in sections:
                    conn_section = sections.get("connection", {})
                    conn_id = conn_section.get("id")
                    if isinstance(conn_id, GLib.Variant):
                        conn_id = conn_id.unpack()
                    if conn_id:
                        known_vpn.append(Vpn(name=str(conn_id), path=conn_path))
            except GLib.Error as e:
                logger.debug(f"[Network] Failed to read connection {conn_path}: {e}")

        if wireless_aps is None:
            wireless_aps = self.wireless_access_points()

        result: list[KnownConnection] = []
        for ap in wireless_aps:
            if ap.ssid in known_ssid:
                result.append(
                    KnownConnection(connection_type="access_point", access_point=ap)
                )
        for vpn in known_vpn:
            result.append(KnownConnection(connection_type="vpn", vpn=vpn))
        return result

    def find_connection(self, name: str) -> str | None:
        """Find a connection path by SSID/id."""
        conn_paths = _get(self._settings, "Connections") or []
        for conn_path in conn_paths:
            try:
                cs = _make_proxy(self._bus, conn_path, NM_CONN_SETTINGS_IFACE)
                settings = _call(cs, "GetSettings")
                if not settings:
                    continue
                if isinstance(settings, tuple) and settings:
                    settings = settings[0]
                sections = settings if isinstance(settings, dict) else {}
                conn_section = sections.get("connection", {})
                conn_id = conn_section.get("id")
                if isinstance(conn_id, GLib.Variant):
                    conn_id = conn_id.unpack()
                if conn_id == name:
                    return conn_path
            except GLib.Error:
                continue
        return None

    def update_connection_password(self, conn_path: str, password: str):
        """Update the PSK in an existing connection."""
        try:
            cs = _make_proxy(self._bus, conn_path, NM_CONN_SETTINGS_IFACE)
            settings = _call(cs, "GetSettings")
            if not settings:
                return
            if isinstance(settings, tuple) and settings:
                settings = settings[0]
            sections = dict(settings) if isinstance(settings, dict) else {}
            sec = dict(sections.get("802-11-wireless-security", {}))
            sec["psk"] = GLib.Variant("s", password)
            sections["802-11-wireless-security"] = sec
            _call(cs, "Update", GLib.Variant("(a{sa{sv}})", (sections,)))
        except GLib.Error as e:
            logger.warning(f"[Network] Failed to update connection password: {e}")


class Wifi(Service):
    """A service to manage the wifi connection via D-Bus."""

    @Signal
    def changed(self) -> None: ...

    def __init__(self, nm: NmProxy, device_path: str, **kwargs):
        self._nm = nm
        self._device_path = device_path
        self._ap_path: str | None = None
        self._handler_id: int | None = None
        self._nm_handler_id: int | None = None
        self._device_handler_id: int | None = None
        super().__init__(**kwargs)

        # Watch for active access point changes on this device
        wdev = _make_proxy(nm._bus, device_path, NM_WIRELESS_IFACE)
        self._handler_id = wdev.connect(
            "g-properties-changed", self._on_device_props_changed
        )

        # Watch WirelessEnabled on the NM main proxy so the toggle stays in sync
        self._nm_handler_id = nm._nm.connect(
            "g-properties-changed", self._on_nm_props_changed
        )

        self._refresh_active_ap()

    def close(self):
        if self._nm_handler_id is not None:
            try:
                self._nm._nm.disconnect(self._nm_handler_id)
            except Exception:
                pass
            self._nm_handler_id = None
        if self._handler_id is not None:
            try:
                wdev = _make_proxy(self._nm._bus, self._device_path, NM_WIRELESS_IFACE)
                wdev.disconnect(self._handler_id)
            except Exception:
                pass
            self._handler_id = None

    def _on_nm_props_changed(self, proxy, changed, invalidated):
        """React to WirelessEnabled changes on the NM main proxy."""
        props = changed.unpack() if changed else {}
        if "WirelessEnabled" in props:
            self.notify("enabled")
            self.emit("changed")

    def _on_device_props_changed(self, proxy, changed, invalidated):
        props = changed.unpack() if changed else {}
        if "ActiveAccessPoint" in props or "AccessPoints" in props:
            self._refresh_active_ap()
            self.emit("changed")
            for sn in (
                "strength",
                "frequency",
                "access-points",
                "ssid",
                "internet",
                "icon-name",
            ):
                self.notify(sn)

    def _refresh_active_ap(self):
        self._ap_path = self._nm.active_access_point_path(self._device_path)

    def _get_active_ap_prop(self, prop):
        if not self._ap_path:
            return None
        try:
            proxy = _make_proxy(self._nm._bus, self._ap_path, NM_AP_IFACE)
            return _get(proxy, prop)
        except GLib.Error:
            return None

    def get_interface_name(self) -> str | None:
        """Return the kernel interface name (e.g. 'wlan0') for this device."""
        try:
            proxy = _make_proxy(self._nm._bus, self._device_path, NM_DEVICE_IFACE)
            return _get(proxy, "Interface") or None
        except GLib.Error:
            return None

    def toggle_wifi(self):
        self._nm.wireless_enabled = not self._nm.wireless_enabled

    def scan(self):
        if getattr(self, "_scanning", False):
            return
        self._scanning = True
        self.notify("scanning")
        self.emit("changed")

        def _finish():
            self._scanning = False
            self.notify("scanning")
            self.emit("changed")
            return False

        def _do_scan():
            self._nm.request_scan(self._device_path)
            GLib.timeout_add(3000, _finish)
            return False

        GLib.idle_add(_do_scan)

    @Property(bool, "read-write", default_value=False)
    def enabled(self) -> bool:
        return self._nm.wireless_enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._nm.wireless_enabled = value

    @Property(int, "readable")
    def strength(self) -> int:
        v = self._get_active_ap_prop("Strength")
        return v if v is not None else -1

    @Property(str, "readable")
    def icon_name(self) -> str:
        if not self._ap_path:
            return "network-wireless-disabled-symbolic"
        if self.internet == "activated":
            return _signal_icon(self.strength)
        if self.internet == "activating":
            return "network-wireless-acquiring-symbolic"
        return "network-wireless-offline-symbolic"

    @Property(int, "readable")
    def frequency(self) -> int:
        v = self._get_active_ap_prop("Frequency")
        return v if v is not None else -1

    @Property(str, "readable")
    def internet(self) -> str:
        ac_paths = self._nm.active_connection_paths
        for ac_path in ac_paths:
            try:
                ac = _make_proxy(self._nm._bus, ac_path, NM_ACTIVE_CONN_IFACE)
                devices = _get(ac, "Devices") or []
                if self._device_path not in devices:
                    continue
                state = _get(ac, "State") or 0
                return _AC_STATE_NAMES.get(state, "unknown")
            except GLib.Error:
                continue
        return "unknown"

    @Property(object, "readable")
    def access_points(self) -> List[AccessPointData]:
        return self._nm.wireless_access_points()

    @Property(str, "readable")
    def ssid(self) -> str:
        ssid_data = self._get_active_ap_prop("Ssid")
        return _ssid_bytes_to_str(ssid_data) if ssid_data else "Disconnected"

    @Property(int, "readable")
    def state(self) -> str:
        return self._nm._device_state_name(self._device_path)

    @Property(bool, "readable", default_value=False)
    def scanning(self) -> bool:
        return getattr(self, "_scanning", False)


class Ethernet(Service):
    """A service to manage the ethernet connection via D-Bus."""

    @Signal
    def changed(self) -> None: ...

    def __init__(self, nm: NmProxy, device_path: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._nm = nm
        self._device_path = device_path
        self._handler_id: int | None = None
        dev = _make_proxy(nm._bus, device_path, NM_DEVICE_IFACE)
        self._handler_id = dev.connect(
            "g-properties-changed", lambda *_: self.emit("changed")
        )

    def close(self):
        if self._handler_id is not None:
            try:
                dev = _make_proxy(self._nm._bus, self._device_path, NM_DEVICE_IFACE)
                dev.disconnect(self._handler_id)
            except Exception:
                pass
            self._handler_id = None

    @Property(int, "readable")
    def speed(self) -> int:
        dev = _make_proxy(self._nm._bus, self._device_path, NM_DEVICE_IFACE)
        return _get(dev, "Speed") or 0

    @Property(int, "readable")
    def internet(self) -> str:
        ac_paths = self._nm.active_connection_paths
        for ac_path in ac_paths:
            try:
                ac = _make_proxy(self._nm._bus, ac_path, NM_ACTIVE_CONN_IFACE)
                devices = _get(ac, "Devices") or []
                if self._device_path not in devices:
                    continue
                state = _get(ac, "State") or 0
                return _AC_STATE_NAMES.get(state, "unknown")
            except GLib.Error:
                continue
        return "unknown"

    @Property(str, "readable")
    def icon_name(self) -> str:
        internet = self.internet
        if internet == "activated":
            return "network-wired-symbolic"
        if internet == "activating":
            return "network-wired-acquiring-symbolic"
        if self._nm.connectivity != "full":
            return "network-wired-no-route-symbolic"
        return "network-wired-disconnected-symbolic"


class NetworkClient(Service):
    _instance: "NetworkClient | None" = None

    @Signal
    def device_ready(self) -> None: ...

    @Signal
    def device_added(self, iface: str) -> None: ...

    @Signal
    def device_removed(self, iface: str) -> None: ...

    def __new__(cls, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._nm: NmProxy | None = None
        self.wifi_device: Wifi | None = None
        self.wifi_devices: dict[str, Wifi] = {}
        self.ethernet_device: Ethernet | None = None
        self._airplane_mode: bool = False
        self._nm_proxy_handler: int | None = None
        super().__init__(**kwargs)
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        if bus is None:
            logger.error("[Network] Failed to connect to system bus")
            return
        self._nm = NmProxy(bus)
        self._init_devices()

    def _init_devices(self):
        if not self._nm:
            return

        for dev_path in self._nm.devices:
            self._handle_device_added(dev_path)

        # Watch for device additions/removals via PropertiesChanged on NM
        self._nm_proxy_handler = self._nm._nm.connect(
            "g-properties-changed", self._on_nm_props_changed
        )

        # Initial airplane mode
        bluetooth_blocked = _rfkill_soft_blocked()
        wifi_enabled = self._nm.wireless_enabled
        self._airplane_mode = bluetooth_blocked and not wifi_enabled

        self.notify("primary-device")
        self.notify("airplane-mode")

    def _on_nm_props_changed(self, proxy, changed, invalidated):
        props = changed.unpack() if changed else {}
        if "Devices" not in props:
            return
        new_devices = set(self._nm.devices)
        # Track by old wifi device paths
        old_paths = {w._device_path for w in self.wifi_devices.values()}
        if self.ethernet_device:
            old_paths.add(self.ethernet_device._device_path)

        new_paths = set(new_devices)
        added = new_paths - old_paths
        removed = old_paths - new_paths

        for dev_path in added:
            self._handle_device_added(dev_path)
        for dev_path in removed:
            self._handle_device_removed(dev_path)

    def _handle_device_added(self, dev_path: str):
        if not self._nm:
            return
        dtype = self._nm._device_type(dev_path)
        iface = dev_path.split("/")[-1]

        if dtype == DEVICE_TYPE_WIFI:
            if dev_path in {w._device_path for w in self.wifi_devices.values()}:
                return
            wifi = Wifi(self._nm, dev_path)
            self.wifi_devices[dev_path] = wifi
            if self.wifi_device is None:
                self.wifi_device = wifi
            logger.info(f"[Network] Wifi device added: {iface}")
            self.emit("device-added", iface)
            self.emit("device-ready")

        elif dtype == DEVICE_TYPE_ETHERNET:
            if self.ethernet_device is None:
                self.ethernet_device = Ethernet(self._nm, dev_path)
                self.emit("device-ready")

    def _handle_device_removed(self, dev_path: str):
        if not self._nm:
            return
        dtype = self._nm._device_type(dev_path)
        iface = dev_path.split("/")[-1]

        if dtype == DEVICE_TYPE_WIFI:
            wifi = self.wifi_devices.pop(dev_path, None)
            if wifi is None:
                return
            if self.wifi_device is wifi:
                self.wifi_device = next(iter(self.wifi_devices.values()), None)
            wifi.close()
            logger.info(f"[Network] Wifi device removed: {iface}")
            self.emit("device-removed", iface)

        elif dtype == DEVICE_TYPE_ETHERNET:
            if self.ethernet_device is not None:
                self.ethernet_device.close()
                self.ethernet_device = None
                self.emit("device-removed", iface)

    def _get_primary_device(self) -> Literal["wifi", "wired"] | None:
        if not self._nm:
            return None
        try:
            for ac_path in self._nm.active_connection_paths:
                ac = _make_proxy(self._nm._bus, ac_path, NM_ACTIVE_CONN_IFACE)
                conn_type = _get(ac, "Type") or ""
                if "wireless" in conn_type:
                    return "wifi"
                if "ethernet" in conn_type:
                    return "wired"
        except Exception as e:
            logger.error(f"[Network] _get_primary_device failed: {e}")
        return None

    def is_network_saved(self, ssid: str) -> bool:
        if not self._nm:
            return False
        conn_paths = _get(self._nm._settings, "Connections") or []
        for conn_path in conn_paths:
            try:
                cs = _make_proxy(self._nm._bus, conn_path, NM_CONN_SETTINGS_IFACE)
                settings = _call(cs, "GetSettings")
                if not settings:
                    continue
                if isinstance(settings, tuple) and settings:
                    settings = settings[0]
                sections = settings if isinstance(settings, dict) else {}
                if "802-11-wireless" not in sections:
                    continue
                conn_section = sections.get("connection", {})
                conn_id = conn_section.get("id")
                if isinstance(conn_id, GLib.Variant):
                    conn_id = conn_id.unpack()
                if conn_id == ssid:
                    return True
            except GLib.Error:
                continue
        return False

    def connect_wifi(self, ap: AccessPointData, callback=None):
        if not self._nm or not self.wifi_device:
            if callback:
                callback(False, "No wifi device")
            return

        def _do_connect():
            try:
                logger.info(
                    f"[Network] connect_wifi ssid={ap.ssid!r} device={ap.device_path} ap={ap.path}"
                )
                conn_path = self._nm.find_connection(ap.ssid)
                logger.info(f"[Network] find_connection({ap.ssid!r}) = {conn_path!r}")
                if conn_path:
                    result = self._nm.activate_connection(
                        conn_path, ap.device_path, ap.path
                    )
                else:
                    settings = {
                        "802-11-wireless": {
                            "ssid": GLib.Variant("ay", ap.ssid.encode("utf-8"))
                        },
                        "connection": {
                            "id": GLib.Variant("s", ap.ssid),
                            "type": GLib.Variant("s", "802-11-wireless"),
                        },
                    }
                    result = self._nm.add_and_activate_connection(
                        settings, ap.device_path, ap.path
                    )
                logger.info(
                    f"[Network] activate/add_result={result!r} for ssid={ap.ssid!r}"
                )
                ok = isinstance(result, tuple) and result[0]
                if callback:
                    GLib.idle_add(callback, ok, "")
            except Exception as e:
                logger.error(f"[Network] Connect failed: {e}")
                if callback:
                    GLib.idle_add(callback, False, str(e))

        import threading

        threading.Thread(target=_do_connect, daemon=True).start()

    def connect_wifi_with_password(
        self, ap: AccessPointData, password: str, callback=None
    ):
        if not self._nm or not self.wifi_device:
            if callback:
                callback(False, "No wifi device")
            return

        def _do_connect():
            try:
                logger.info(
                    f"[Network] connect_wifi_with_password ssid={ap.ssid!r} device={ap.device_path} ap={ap.path}"
                )
                conn_path = self._nm.find_connection(ap.ssid)
                logger.info(f"[Network] find_connection({ap.ssid!r}) = {conn_path!r}")
                if conn_path:
                    self._nm.update_connection_password(conn_path, password)
                    result = self._nm.activate_connection(
                        conn_path, ap.device_path, ap.path
                    )
                else:
                    settings = {
                        "802-11-wireless": {
                            "ssid": GLib.Variant("ay", ap.ssid.encode("utf-8"))
                        },
                        "connection": {
                            "id": GLib.Variant("s", ap.ssid),
                            "type": GLib.Variant("s", "802-11-wireless"),
                        },
                        "802-11-wireless-security": {
                            "key-mgmt": GLib.Variant("s", "wpa-psk"),
                            "psk": GLib.Variant("s", password),
                        },
                    }
                    result = self._nm.add_and_activate_connection(
                        settings, ap.device_path, ap.path
                    )
                logger.info(
                    f"[Network] activate/add_result={result!r} for ssid={ap.ssid!r}"
                )
                ok = isinstance(result, tuple) and result[0]
                if callback:
                    GLib.idle_add(callback, ok, "")
            except Exception as e:
                logger.error(f"[Network] Connect with password failed: {e}")
                if callback:
                    GLib.idle_add(callback, False, str(e))

        import threading

        threading.Thread(target=_do_connect, daemon=True).start()

    def disconnect_wifi(self):
        if not self._nm or not self.wifi_device:
            return

        def _do_disconnect():
            for ac_path in self._nm.active_connection_paths:
                try:
                    ac = _make_proxy(self._nm._bus, ac_path, NM_ACTIVE_CONN_IFACE)
                    devices = _get(ac, "Devices") or []
                    if self.wifi_device._device_path in devices:
                        self._nm.deactivate_connection(ac_path)
                        break
                except Exception:
                    continue

        import threading

        threading.Thread(target=_do_disconnect, daemon=True).start()

    # Airplane mode

    @Property(bool, "read-write", default_value=False)
    def airplane_mode(self) -> bool:
        if self._nm:
            bluetooth_blocked = _rfkill_soft_blocked()
            wifi_enabled = self._nm.wireless_enabled
            self._airplane_mode = bluetooth_blocked and not wifi_enabled
        return self._airplane_mode

    @airplane_mode.setter
    def airplane_mode(self, value: bool):
        self.set_airplane_mode(value)

    def set_airplane_mode(self, enable: bool):
        """Toggle airplane mode: block/unblock bluetooth rfkill + toggle wifi radio.

        Port of dbus.rs NetworkBackend::set_airplane_mode.
        """
        try:
            action = "block" if enable else "unblock"
            subprocess.run(
                ["rfkill", action, "bluetooth"],
                capture_output=True,
                timeout=5,
            )
        except FileNotFoundError:
            logger.warning("[Network] rfkill not found")
        except Exception as e:
            logger.warning(f"[Network] rfkill {action} failed: {e}")

        if self._nm:
            self._nm.wireless_enabled = not enable

        self._airplane_mode = enable
        self.notify("airplane-mode")
        self.emit("changed")

    @Property(str, "readable")
    def connectivity(self) -> str:
        if not self._nm:
            return "unknown"
        return self._nm.connectivity

    # Known connections
    @Property(object, "readable")
    def known_connections(self) -> List[KnownConnection]:
        if not self._nm:
            return []
        return self._nm.known_connections()

    # Active connections info

    @Property(object, "readable")
    def active_connections(self) -> List[ActiveConnectionInfo]:
        if not self._nm:
            return []
        return self._nm.active_connections_info()

    # Network data snapshot

    def get_network_data(self) -> NetworkData:
        return NetworkData(
            wifi_present=self.wifi_device is not None,
            wireless_access_points=(
                self.wifi_device.access_points if self.wifi_device else []
            ),
            active_connections=self.active_connections,
            known_connections=self.known_connections,
            wifi_enabled=(self.wifi_device.enabled if self.wifi_device else False),
            airplane_mode=self.airplane_mode,
            connectivity=self.connectivity,
            scanning_nearby_wifi=(
                self.wifi_device.scanning if self.wifi_device else False
            ),
        )
