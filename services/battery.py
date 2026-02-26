from typing import Literal, Optional

from fabric import Service, Signal
from gi.repository import Gio, GLib
from loguru import logger

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

PowerProfile = {
    "power-saver": "Power Saver",
    "balanced": "Balanced",
    "performance": "Performance",
}


class BatteryService(Service):
    """Service to interact with UPower and Power Profiles via GIO D-Bus"""

    @Signal
    def changed(self) -> None:
        """Signal emitted when battery changes."""

    @Signal
    def power_profile_changed(self) -> None:
        """Signal emitted when power profile changes."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # UPower D-Bus configuration
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

        # Listen for PropertiesChanged signals from UPower
        self.dbus_helper.listen_signal(
            member="PropertiesChanged",
            callback=self.handle_property_change,
        )

        # Power Profiles D-Bus configuration
        self.power_profile_bus_name = "net.hadess.PowerProfiles"
        self.power_profile_object_path = "/net/hadess/PowerProfiles"
        self.power_profile_interface_name = "net.hadess.PowerProfiles"

        try:
            self.power_profile_helper = GioDBusHelper(
                bus_type=Gio.BusType.SYSTEM,
                bus_name=self.power_profile_bus_name,
                object_path=self.power_profile_object_path,
                interface_name=self.power_profile_interface_name,
            )

            self.power_profile_proxy = self.power_profile_helper.proxy

            # Listen for PropertiesChanged signals from Power Profiles
            self.power_profile_helper.listen_signal(
                member="PropertiesChanged",
                callback=self.handle_power_profile_change,
            )

            self._power_profiles_available = True
        except Exception as e:
            logger.warning(f"[Battery] Power Profiles daemon not available: {e}")
            self.power_profile_helper = None
            self.power_profile_proxy = None
            self._power_profiles_available = False

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

    def get_power_profile(self) -> Optional[str]:
        """Get the current active power profile."""
        if not self._power_profiles_available:
            return None

        try:
            result = self.power_profile_proxy.get_cached_property("ActiveProfile")
            return result.unpack() if result is not None else None
        except Exception as e:
            logger.exception(f"[Battery] Error retrieving active power profile: {e}")
            return None

    def set_power_profile(
        self, profile: Literal["power-saver", "balanced", "performance"]
    ) -> bool:
        """Set the active power profile."""
        if not self._power_profiles_available:
            logger.warning("[Battery] Power Profiles daemon not available")
            return False

        if profile not in PowerProfile:
            return False

        try:
            self.power_profile_helper.set_property(
                interface_name=self.power_profile_interface_name,
                property_name="ActiveProfile",
                value_variant=GLib.Variant("s", profile),
            )
            return True
        except Exception as e:
            logger.exception(
                f"[Battery] Error setting power profile to '{profile}': {e}"
            )
            return False

    def get_available_power_profiles(self) -> Optional[list]:
        """Get list of available power profiles."""
        if not self._power_profiles_available:
            return None

        try:
            result = self.power_profile_proxy.get_cached_property("Profiles")
            if result is not None:
                profiles_data = result.unpack()
                # Extract profile names from the array of dictionaries
                profiles = []
                for profile_dict in profiles_data:
                    if "Profile" in profile_dict:
                        profiles.append(profile_dict["Profile"])
                return profiles
            return None
        except Exception as e:
            logger.exception(
                f"[Battery] Error retrieving available power profiles: {e}"
            )
            return None

    def is_power_profiles_available(self) -> bool:
        """Check if power profiles daemon is available."""
        return self._power_profiles_available

    def get_power_profile_display_name(self, profile: str) -> str:
        """Get display name for a power profile."""
        return PowerProfile.get(profile, profile.title())

    def handle_property_change(self, *_):
        # You may filter which property changed by checking parameters[1]
        self.emit("changed")

    def handle_power_profile_change(self, *_):
        """Handle power profile property changes."""
        self.emit("power_profile_changed")
