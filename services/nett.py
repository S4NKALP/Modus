import gi
from fabric.core.service import Service, Signal
from loguru import logger

try:
    gi.require_version("NM", "1.0")
    from gi.repository import NM
except ValueError:
    logger.error("Failed to start network manager")


class NetworkService(Service):

    @Signal
    def connection_change(
        self, ssid: str, connected: bool, status: str = ""
    ) -> None: ...

    def __init__(self):
        super().__init__()
        self.client = NM.Client.new(None)
        self.client.connect("device-added", self.on_device_added)
        self.client.connect("device-removed", self.on_device_removed)
        # self.client.connect("notify::state", self.handle_client_state_change)

        # active_connections = self.client.get_active_connections()
        # for ac in active_connections:
        #     connection = ac.get_connection()
        #     type = ac.get_connection_type()
        #     print("Active connection:", connection.get_id(), type)

        devices = self.client.get_devices()
        for dev in devices:
            if dev.get_device_type() == NM.DeviceType.WIFI:
                self.wifi_dev = dev
                active_ap = self.wifi_dev.get_active_access_point()
                if active_ap:
                    ssid = active_ap.get_ssid()
                    print("Connected SSID:", ssid.get_data().decode("utf-8"))

        if self.wifi_dev:
            self.wifi_dev.connect("state-changed", self.handle_device_state_change)
            self.wifi_dev.connect(
                "notify::active-access-point", self.handle_prop_change
            )

    def init_props(self):
        self.handle_prop_change(self.wifi_dev, None)

    def handle_prop_change(self, source, pspec):
        if source is None:
            self.connection_change("", False, "No Device")
            return

        device_state = source.get_state()
        if device_state == NM.DeviceState.UNAVAILABLE:
            self.connection_change("", False, "Wi-Fi Off")
            return

        active_ap = source.get_active_access_point()
        if active_ap:
            ssid = active_ap.get_ssid().get_data().decode("utf-8")
            print("Connected SSID:", ssid)
            self.connection_change(ssid, True, "Connected")
        else:
            self.connection_change("", False, "Wi-Fi On (No Connection)")

    def handle_device_state_change(self, device, new_state, old_state, reason):
        print("Device state changed:", old_state, "→", new_state)
        match new_state:
            case NM.DeviceState.UNAVAILABLE:
                self.connection_change("", False, "Wi-Fi Off")
            case NM.DeviceState.DISCONNECTED:
                self.connection_change("", False, "Wi-Fi On (No Connection)")
            case (
                NM.DeviceState.PREPARE
                | NM.DeviceState.CONFIG
                | NM.DeviceState.NEED_AUTH
                | NM.DeviceState.IP_CONFIG
                | NM.DeviceState.IP_CHECK
                | NM.DeviceState.SECONDARIES
            ):
                self.connection_change("", False, "Connecting…")
            case NM.DeviceState.ACTIVATED:
                active_ap = device.get_active_access_point()
                if active_ap:
                    ssid = active_ap.get_ssid().get_data().decode("utf-8")
                    self.connection_change(ssid, True, "Connected")
                else:
                    self.connection_change("", True, "Connected (No SSID)")
            case _:
                self.connection_change("", False, "Unknown")

    def on_device_added(self, source, device):
        print("Added device")
        if device.get_device_type() == NM.DeviceType.WIFI:
            self.wifi_dev = device
            self.wifi_dev.connect("state-changed", self.handle_device_state_change)
            self.wifi_dev.connect(
                "notify::active-access-point", self.handle_prop_change
            )

    def on_device_removed(self, client, device):
        print("Removed device")
        if self.wifi_dev and device.get_path() == self.wifi_dev.get_path():
            self.wifi_dev = None
            self.handle_prop_change(self.wifi_dev, None)

    def print_state(self):
        print(
            "wifi: ", self.wifi_dev.get_state(), "    client: ", self.client.get_state()
        )
