import gi
from fabric.core.service import Property, Service, Signal
from gi.repository import Gio, GLib
from loguru import logger

gi.require_version("Gtk", "3.0")

BATTERY_BUS_NAME = "org.freedesktop.UPower"
BATTERY_BUS_PATH = "/org/freedesktop/UPower/devices/DisplayDevice"
BATTERY_INTERFACE = "org.freedesktop.UPower.Device"

POWER_PROFILE_BUS_NAME = "net.hadess.PowerProfiles"
POWER_PROFILE_BUS_PATH = "/net/hadess/PowerProfiles"
POWER_PROFILE_INTERFACE = "net.hadess.PowerProfiles"

DEVICE_STATE = {
    0: "UNKNOWN",
    1: "CHARGING",
    2: "DISCHARGING",
    3: "EMPTY",
    4: "FULLY_CHARGED",
    5: "PENDING_CHARGE",
    6: "PENDING_DISCHARGE",
}


class Battery(Service):
    """A service for interacting with the battery's DBus and Power Profiles"""

    @Signal
    def changed(self) -> None: ...

    @Signal
    def power_profile_changed(self) -> None: ...

    @Property(bool, "readable", default_value=False)
    def available(self) -> bool:
        return self.do_get_cached_property("IsPresent") or False

    @Property(str, "readable", default_value="")
    def vendor(self) -> str:
        return self.do_get_cached_property("Vendor") or ""

    @Property(int, "readable", default_value=0)
    def percent(self) -> int:
        return self.do_get_cached_property("Percentage") or 0

    @Property(bool, "readable", default_value=False)
    def charging(self) -> bool:
        val = self.do_get_cached_property("State")
        if val is None:
            return False
        return val == DEVICE_STATE.get("CHARGING", 1)

    @Property(bool, "readable", default_value=False)
    def discharging(self) -> bool:
        val = self.do_get_cached_property("State")
        if val is None:
            return False
        return val == DEVICE_STATE.get("DISCHARGING", 2)

    @Property(bool, "readable", default_value=False)
    def charged(self) -> bool:
        val = self.do_get_cached_property("State")
        if val is None:
            return False
        return val == DEVICE_STATE.get("FULLY_CHARGED", 4)

    @Property(str, "readable", default_value="")
    def icon_name(self) -> str:
        return self.do_get_cached_property("IconName") or ""

    @Property(int, "readable", default_value=0)
    def time_remaining(self) -> int:
        return self.do_get_cached_property("TimeToEmpty") or 0

    @Property(int, "readable", default_value=0)
    def time_to_full(self) -> int:
        return self.do_get_cached_property("TimeToFull") or 0

    @Property(float, "readable", default_value=0.0)
    def energy(self) -> float:
        return self.do_get_cached_property("Energy") or 0.0

    @Property(float, "readable", default_value=0.0)
    def energy_full(self) -> float:
        return self.do_get_cached_property("EnergyFull") or 0.0

    @Property(float, "readable", default_value=0.0)
    def energy_rate(self) -> float:
        return self.do_get_cached_property("EnergyRate") or 0.0

    @Property(float, "readable", default_value=0.0)
    def temperature(self) -> float:
        return self.do_get_cached_property("Temperature") or 0.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._bus: Gio.DBusConnection | None = None
        self._proxy = None
        self._power_profile_proxy = None
        self.do_register()

    def do_register(self) -> None:
        self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        self._proxy = Gio.DBusProxy.new_sync(
            self._bus,
            Gio.DBusProxyFlags.NONE,
            None,
            BATTERY_BUS_NAME,
            BATTERY_BUS_PATH,
            BATTERY_INTERFACE,
            None,
        )

        logger.info("[Battery] Proxy initialized")

        self._bus.signal_subscribe(
            BATTERY_BUS_NAME,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            BATTERY_BUS_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self.do_handle_property_change,
        )

        try:
            self._power_profile_proxy = Gio.DBusProxy.new_sync(
                self._bus,
                Gio.DBusProxyFlags.NONE,
                None,
                POWER_PROFILE_BUS_NAME,
                POWER_PROFILE_BUS_PATH,
                POWER_PROFILE_INTERFACE,
                None,
            )
            self._bus.signal_subscribe(
                POWER_PROFILE_BUS_NAME,
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                POWER_PROFILE_BUS_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self.do_handle_power_profile_change,
            )
            logger.info("[Battery] Power Profiles Proxy initialized")
        except Exception as e:
            logger.warning(f"[Battery] Power Profiles daemon not available: {e}")

    def do_handle_property_change(self, *_):
        self.emit("changed")

    def do_handle_power_profile_change(self, *_):
        self.emit("power_profile_changed")

    def do_call_proxy_method(
        self,
        bus_name,
        object_path,
        interface_name,
        method_name,
        parameters=None,
        timeout=-1,
    ):
        if parameters is None:
            parameters = GLib.Variant("()", ())
        result = self._bus.call_sync(
            bus_name,
            object_path,
            interface_name,
            method_name,
            parameters,
            None,
            Gio.DBusCallFlags.NONE,
            timeout,
            None,
        )
        return result.unpack()

    def do_get_cached_property(self, property_name):
        result = self._proxy.get_cached_property(property_name)
        return result.unpack() if result is not None else None

    def get_power_profile(self) -> str | None:
        """Get the current active power profile."""
        if not self._power_profile_proxy:
            return None
        result = self._power_profile_proxy.get_cached_property("ActiveProfile")
        return result.unpack() if result is not None else None

    def set_power_profile(self, profile: str) -> bool:
        """Set the active power profile."""
        if not self._power_profile_proxy:
            return False
        try:
            parameters = GLib.Variant(
                "(ssv)",
                (POWER_PROFILE_INTERFACE, "ActiveProfile", GLib.Variant("s", profile)),
            )
            self._bus.call_sync(
                POWER_PROFILE_BUS_NAME,
                POWER_PROFILE_BUS_PATH,
                "org.freedesktop.DBus.Properties",
                "Set",
                parameters,
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            return True
        except Exception as e:
            logger.error(f"[Battery] Failed to set power profile: {e}")
            return False

    def get_available_power_profiles(self) -> list | None:
        """Get list of available power profiles."""
        if not self._power_profile_proxy:
            return None
        result = self._power_profile_proxy.get_cached_property("Profiles")
        if result is not None:
            profiles_data = result.unpack()
            profiles = []
            for profile_dict in profiles_data:
                if "Profile" in profile_dict:
                    profiles.append(profile_dict["Profile"])
            return profiles
        return None
