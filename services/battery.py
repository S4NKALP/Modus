from fabric.core import Service, Property, Signal
from pydbus import SystemBus

DeviceState = {
    0: "UNKNOWN",
    1: "CHARGING",
    2: "DISCHARGING",
    3: "EMPTY",
    4: "FULLY_CHARGED",
    5: "PENDING_CHARGE",
    6: "PENDING_DISCHARGE",
}


class Battery(Service):
    @staticmethod
    def seconds_to_hours_minutes(seconds):
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m" if hours else f"{minutes}m"

    @Signal
    def changed(self) -> None: ...

    @Signal
    def profile_changed(self, value: str) -> None: ...

    @Property(int, "readable")
    def percentage(self):
        return int(self._battery.Percentage)

    @Property(str, "readable")
    def temperature(self):
        return f"{self._battery.Temperature}°C" if hasattr(self._battery, "Temperature") else "N/A"

    @Property(str, "readable")
    def time_to_empty(self):
        return self.seconds_to_hours_minutes(getattr(self._battery, "TimeToEmpty", 0))

    @Property(str, "readable")
    def time_to_full(self):
        return self.seconds_to_hours_minutes(getattr(self._battery, "TimeToFull", 0))

    @Property(str, "readable")
    def icon_name(self):
        return self._battery.IconName

    @Property(str, "readable")
    def state(self):
        return DeviceState.get(self._battery.State, "UNKNOWN")

    @Property(str, "readable")
    def capacity(self):
        return f"{self._battery.Capacity}%"

    @Property(bool, "readable", default_value=False)
    def is_present(self):
        return self._battery.IsPresent

    @Property(str, "readable")
    def power_profile(self):
        return self._profile_proxy.ActiveProfile

    def set_power_profile(self, profile: str) -> bool:
        if profile not in [p.Profile for p in self._profile_proxy.Profiles]:
            return False
        try:
            self._profile_proxy.ActiveProfile = profile
            self.profile_changed.emit(profile)
            self.changed.emit()
            return True
        except Exception as e:
            return False

    def __init__(self):
        super().__init__()
        self._bus = SystemBus()

        # Battery device
        try:
            self._battery = self._bus.get("org.freedesktop.UPower", "/org/freedesktop/UPower/devices/battery_BAT0")
            self._battery.onPropertiesChanged = self.handle_battery_change
        except Exception as e:
            return

        # PowerProfiles
        try:
            self._profile_proxy = self._bus.get("net.hadess.PowerProfiles", "/net/hadess/PowerProfiles")
            # Use onPropertiesChanged for consistency with battery device
            self._profile_proxy.onPropertiesChanged = lambda _, changed, __: self._handle_profile_props_changed(changed)
        except Exception as e:
            self._profile_proxy = None

        self.changed.emit()

    def _handle_profile_props_changed(self, changed):
        """Internal handler for property changes that processes only the changed properties"""
        if "ActiveProfile" in changed:
            new_profile = changed["ActiveProfile"]
            self.profile_changed.emit(new_profile)
            self.changed.emit()

    def handle_battery_change(self, iface, changed, invalidated):
        self.changed.emit()
