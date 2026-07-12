from typing import Literal

from fabric import Service, Signal
from fabric.utils import Gio, logger

from utils.dbus_helper import GioDBusHelper

DeviceState = {
    0: "UNKNOWN",
    1: "CHARGING",
    2: "DISCHARGING",
    3: "EMPTY",
    4: "FULLY_CHARGED",
    5: "PENDING_CHARGE",
    6: "PENDING_DISCHARGE",
}


class BatteryService(Service):
    """Service to interact with UPower via GIO D-Bus"""

    @Signal
    def changed(self) -> None:
        """Signal emitted when battery changes."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.bus_name = "org.freedesktop.UPower"
        self.object_path = "/org/freedesktop/UPower/devices/DisplayDevice"
        self.interface_name = "org.freedesktop.UPower.Device"

        self.dbus_helper = GioDBusHelper(
            bus_type=Gio.BusType.SYSTEM,
            bus_name=self.bus_name,
            object_path=self.object_path,
            interface_name=self.interface_name,
        )

        self.proxy = self.dbus_helper.proxy

        # Listen for PropertiesChanged signals
        self.dbus_helper.listen_signal(
            member="PropertiesChanged",
            callback=self.handle_property_change,
        )

    def get_property(
        self,
        property: Literal[
            "Percentage",
            "Temperature",
            "TimeToEmpty",
            "TimeToFull",
            "IconName",
            "State",
            "Capacity",
            "IsPresent",
            "Vendor",
        ],
    ):
        try:
            result = self.proxy.get_cached_property(property)
            return result.unpack() if result is not None else None
        except Exception as e:
            logger.exception(f"[Battery] Error retrieving '{property}': {e}")
            return None

    def handle_property_change(self, *_):
        # You may filter which property changed by checking parameters[1]

        self.emit("changed")
