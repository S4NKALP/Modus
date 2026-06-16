from types import SimpleNamespace
from typing import List, Literal

import gi
from fabric.core.service import Property, Service, Signal
from fabric.utils import Gio, bulk_connect, exec_shell_command_async, logger

try:
    gi.require_version("NM", "1.0")
    from gi.repository import NM
except ValueError:
    logger.error("Failed to start network manager")


class Wifi(Service):
    """A service to manage the wifi connection."""

    @Signal
    def changed(self) -> None: ...

    @Signal
    def enabled_changed(self) -> bool: ...

    def __init__(self, client: NM.Client, device: NM.DeviceWifi, **kwargs):
        self._client: NM.Client = client
        self._device: NM.DeviceWifi = device
        self._ap: NM.AccessPoint | None = None
        self._ap_signal: int | None = None
        super().__init__(**kwargs)

        self._client.connect(
            "notify::wireless-enabled",
            lambda *args: self.notifier("enabled", args),
        )
        if self._device:
            bulk_connect(
                self._device,
                {
                    "notify::active-access-point": lambda *args: self._activate_ap(),
                    "access-point-added": lambda *args: self.emit("changed"),
                    "access-point-removed": lambda *args: self.emit("changed"),
                    "state-changed": lambda *args: self.ap_update(),
                },
            )
            self._activate_ap()

    def ap_update(self):
        self.emit("changed")
        for sn in [
            "enabled",
            "internet",
            "strength",
            "frequency",
            "access-points",
            "ssid",
            "state",
            "icon-name",
        ]:
            self.notify(sn)

    def _activate_ap(self):
        if self._ap:
            self._ap.disconnect(self._ap_signal)
        self._ap = self._device.get_active_access_point()
        if not self._ap:
            return

        self._ap_signal = self._ap.connect(
            "notify::strength", lambda *args: self.ap_update()
        )

    def toggle_wifi(self):
        self._client.wireless_set_enabled(not self._client.wireless_get_enabled())

    def scan(self):
        self._device.request_scan_async(
            None,
            lambda device, result: [
                device.request_scan_finish(result),
                self.emit("changed"),
            ],
        )

    def notifier(self, name: str, *args):
        self.notify(name)
        self.emit("changed")
        return

    @Property(bool, "read-write", default_value=False)
    def enabled(self) -> bool:
        return bool(self._client.wireless_get_enabled())

    @enabled.setter
    def enabled(self, value: bool):
        self._client.wireless_set_enabled(value)

    @Property(int, "readable")
    def strength(self):
        return self._ap.get_strength() if self._ap else -1

    @Property(str, "readable")
    def icon_name(self):
        if not self._ap:
            return "network-wireless-disabled-symbolic"

        if self.internet == "activated":
            return {
                80: "network-wireless-signal-excellent-symbolic",
                60: "network-wireless-signal-good-symbolic",
                40: "network-wireless-signal-ok-symbolic",
                20: "network-wireless-signal-weak-symbolic",
                00: "network-wireless-signal-none-symbolic",
            }.get(
                min(80, 20 * round(self._ap.get_strength() / 20)),
                "network-wireless-no-route-symbolic",
            )
        if self.internet == "activating":
            return "network-wireless-acquiring-symbolic"

        return "network-wireless-offline-symbolic"

    @Property(int, "readable")
    def frequency(self):
        return self._ap.get_frequency() if self._ap else -1

    @Property(str, "readable")
    def internet(self):
        conn = self._device.get_active_connection()
        if not conn:
            return "unknown"
        return {
            NM.ActiveConnectionState.ACTIVATED: "activated",
            NM.ActiveConnectionState.ACTIVATING: "activating",
            NM.ActiveConnectionState.DEACTIVATING: "deactivating",
            NM.ActiveConnectionState.DEACTIVATED: "deactivated",
        }.get(conn.get_state(), "unknown")

    @Property(object, "readable")
    def access_points(self) -> List[object]:
        points: list[NM.AccessPoint] = self._device.get_access_points()
        active_bssid = self._ap.get_bssid() if self._ap else None

        def make_ap(ap: NM.AccessPoint):
            ssid_bytes = ap.get_ssid()
            ssid = (
                NM.utils_ssid_to_utf8(ssid_bytes.get_data())
                if ssid_bytes
                else "Unknown"
            )
            bssid = ap.get_bssid()
            strength = ap.get_strength()
            is_active = bssid == active_bssid if active_bssid else False
            flags = ap.get_rsn_flags() or ap.get_wpa_flags()
            requires_password = bool(flags)
            icon = {
                80: "network-wireless-signal-excellent-symbolic",
                60: "network-wireless-signal-good-symbolic",
                40: "network-wireless-signal-ok-symbolic",
                20: "network-wireless-signal-weak-symbolic",
                0: "network-wireless-signal-none-symbolic",
            }.get(
                min(80, 20 * round(strength / 20)),
                "network-wireless-no-route-symbolic",
            )
            return SimpleNamespace(
                ssid=ssid,
                bssid=bssid,
                strength=strength,
                is_active=is_active,
                requires_password=requires_password,
                icon=icon,
            )

        return list(map(make_ap, points))

    @Property(str, "readable")
    def ssid(self):
        if not self._ap:
            return "Disconnected"
        ssid = self._ap.get_ssid().get_data()
        return NM.utils_ssid_to_utf8(ssid) if ssid else "Unknown"

    @Property(int, "readable")
    def state(self):
        return {
            NM.DeviceState.UNMANAGED: "unmanaged",
            NM.DeviceState.UNAVAILABLE: "unavailable",
            NM.DeviceState.DISCONNECTED: "disconnected",
            NM.DeviceState.PREPARE: "prepare",
            NM.DeviceState.CONFIG: "config",
            NM.DeviceState.NEED_AUTH: "need_auth",
            NM.DeviceState.IP_CONFIG: "ip_config",
            NM.DeviceState.IP_CHECK: "ip_check",
            NM.DeviceState.SECONDARIES: "secondaries",
            NM.DeviceState.ACTIVATED: "activated",
            NM.DeviceState.DEACTIVATING: "deactivating",
            NM.DeviceState.FAILED: "failed",
        }.get(self._device.get_state(), "unknown")


class Ethernet(Service):
    """A service to manage the ethernet connection."""

    @Signal
    def changed(self) -> None: ...

    @Signal
    def enabled(self) -> bool: ...

    @Property(int, "readable")
    def speed(self) -> int:
        return self._device.get_speed()

    @Property(int, "readable")
    def internet(self):
        conn = self._device.get_active_connection()
        if not conn:
            return "unknown"
        return {
            NM.ActiveConnectionState.ACTIVATED: "activated",
            NM.ActiveConnectionState.ACTIVATING: "activating",
            NM.ActiveConnectionState.DEACTIVATING: "deactivating",
            NM.ActiveConnectionState.DEACTIVATED: "deactivated",
        }.get(conn.get_state(), "unknown")

    @Property(str, "readable")
    def icon_name(self) -> str:
        network = self.internet
        if network == "activated":
            return "network-wired-symbolic"

        elif network == "activating":
            return "network-wired-acquiring-symbolic"

        elif self._device.get_connectivity != NM.ConnectivityState.FULL:
            return "network-wired-no-route-symbolic"

        return "network-wired-disconnected-symbolic"

    def __init__(self, client: NM.Client, device: NM.DeviceEthernet, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client: NM.Client = client
        self._device: NM.DeviceEthernet = device

        for pn in (
            "active-connection",
            "icon-name",
            "internet",
            "speed",
            "state",
        ):
            self._device.connect(f"notify::{pn}", lambda *_: self.notifier(pn))

        self._device.connect("notify::speed", lambda *_: print(_))

    def notifier(self, pn):
        self.notify(pn)
        self.emit("changed")


class NetworkClient(Service):
    @Signal
    def device_ready(self) -> None: ...

    @Signal
    def device_added(self, iface: str) -> None: ...

    @Signal
    def device_removed(self, iface: str) -> None: ...

    def __init__(self, **kwargs):
        self._client: NM.Client | None = None
        self.wifi_device: Wifi | None = None
        self.wifi_devices: dict[str, Wifi] = {}
        self.ethernet_device: Ethernet | None = None
        super().__init__(**kwargs)
        NM.Client.new_async(
            cancellable=None,
            callback=self._init_network_client,
        )

    def _init_network_client(self, client: NM.Client, task: Gio.Task, **kwargs):
        self._client = client

        for device in self._client.get_devices():
            self._handle_device_added(device)

        self._client.connect("device-added", lambda _, d: self._handle_device_added(d))
        self._client.connect(
            "device-removed", lambda _, d: self._handle_device_removed(d)
        )

        self.notify("primary-device")

    def _handle_device_added(self, nm_device):
        dtype = nm_device.get_device_type()

        if dtype == NM.DeviceType.WIFI:
            iface = nm_device.get_iface()
            if iface in self.wifi_devices:
                return
            wifi = Wifi(self._client, nm_device)
            self.wifi_devices[iface] = wifi
            if self.wifi_device is None:
                self.wifi_device = wifi
            logger.info(f"[Network] Wifi device added: {iface}")
            self.emit("device-added", iface)
            self.emit("device-ready")

        elif dtype == NM.DeviceType.ETHERNET:
            if self.ethernet_device is None:
                self.ethernet_device = Ethernet(client=self._client, device=nm_device)
                self.emit("device-ready")

    def _handle_device_removed(self, nm_device):
        dtype = nm_device.get_device_type()

        if dtype == NM.DeviceType.WIFI:
            iface = nm_device.get_iface()
            wifi = self.wifi_devices.pop(iface, None)
            if wifi is None:
                return
            if self.wifi_device is wifi:
                self.wifi_device = next(iter(self.wifi_devices.values()), None)
            logger.info(f"[Network] Wifi device removed: {iface}")
            self.emit("device-removed", iface)

    def _get_primary_device(self) -> Literal["wifi", "wired"] | None:
        if not self._client:
            return None
        try:
            conn_type = self._client.get_primary_connection().get_connection_type()
            if "wireless" in str(conn_type):
                return "wifi"
            if "ethernet" in str(conn_type):
                return "wired"
        except Exception:
            pass
        return None

    def is_network_saved(self, ssid: str) -> bool:
        if not self._client:
            return False
        for conn in self._client.get_connections():
            s_wifi = conn.get_setting_wireless()
            if s_wifi:
                saved_ssid = s_wifi.get_ssid()
                if saved_ssid:
                    if NM.utils_ssid_to_utf8(saved_ssid.get_data()) == ssid:
                        return True
        return False

    def connect_wifi_bssid(self, bssid: str):
        exec_shell_command_async(
            f"nmcli device wifi connect {bssid}",
            lambda *args: logger.debug(f"connect result: {args}"),
        )

    def connect_wifi_with_password(self, bssid: str, password: str, callback):
        if not self._client or not self.wifi_device:
            callback(False, "No wifi device")
            return

        device = self.wifi_device._device
        handler_id: list[int] = []

        def _on_state_changed(dev, new_state, old_state, reason):
            state = NM.DeviceState(new_state)
            if state == NM.DeviceState.ACTIVATED:
                _cleanup()
                callback(True, "Connected")
            elif state in (NM.DeviceState.FAILED, NM.DeviceState.DISCONNECTED):
                _cleanup()
                reason_str = NM.DeviceStateReason(reason).value_nick
                if "secret" in reason_str or "auth" in reason_str:
                    callback(False, "Wrong password")
                else:
                    callback(False, f"Failed ({reason_str})")
            elif state == NM.DeviceState.NEED_AUTH:
                _cleanup()
                callback(False, "Wrong password")

        def _cleanup():
            if handler_id:
                try:
                    device.disconnect_by_func(_on_state_changed)
                except Exception:
                    pass

        handler_id.append(device.connect("state-changed", _on_state_changed))

        exec_shell_command_async(
            f"nmcli device wifi connect {bssid} password {password!r}",
            lambda *args: logger.debug(f"connect_with_password result: {args}"),
        )

    @Property(str, "readable")
    def primary_device(self) -> Literal["wifi", "wired"] | None:
        return self._get_primary_device()
