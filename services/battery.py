import psutil
from gi.repository import GLib
from pydbus import SystemBus

from fabric.core import Property, Service, Signal

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
        if self._use_psutil_fallback:
            if self._psutil_battery:
                return int(self._psutil_battery.percent)
            return 0
        return int(self._battery.Percentage)

    @Property(str, "readable")
    def temperature(self):
        if self._use_psutil_fallback:
            return "N/A"  # psutil doesn't provide temperature
        return (
            f"{self._battery.Temperature}°C"
            if hasattr(self._battery, "Temperature")
            else "N/A"
        )

    @Property(str, "readable")
    def time_to_empty(self):
        if self._use_psutil_fallback:
            if self._psutil_battery and hasattr(self._psutil_battery, "secsleft"):
                return self.seconds_to_hours_minutes(self._psutil_battery.secsleft)
            return "N/A"
        return self.seconds_to_hours_minutes(getattr(self._battery, "TimeToEmpty", 0))

    @Property(str, "readable")
    def time_to_full(self):
        if self._use_psutil_fallback:
            return "N/A"  # psutil doesn't provide time to full
        return self.seconds_to_hours_minutes(getattr(self._battery, "TimeToFull", 0))

    @Property(str, "readable")
    def icon_name(self):
        if self._use_psutil_fallback:
            return "battery"  # Generic icon name for psutil fallback
        return self._battery.IconName

    @Property(str, "readable")
    def state(self):
        if self._use_psutil_fallback:
            if self._psutil_battery:
                # psutil returns power_plugged boolean, convert to state
                if self._psutil_battery.power_plugged:
                    if self._psutil_battery.percent >= 100:
                        return "FULLY_CHARGED"
                    else:
                        return "CHARGING"
                else:
                    return "DISCHARGING"
            return "UNKNOWN"
        return DeviceState.get(self._battery.State, "UNKNOWN")

    @Property(str, "readable")
    def capacity(self):
        if self._use_psutil_fallback:
            return "N/A"  # psutil doesn't provide capacity info
        return f"{int(self._battery.Capacity)}%"

    @Property(bool, "readable", default_value=False)
    def is_present(self):
        if self._use_psutil_fallback:
            return self._psutil_battery is not None
        return self._battery.IsPresent

    @Property(str, "readable")
    def power_profile(self):
        if self._profile_proxy:
            return self._profile_proxy.ActiveProfile
        return None

    def set_power_profile(self, profile: str) -> bool:
        if not self._profile_proxy:
            return False
        if profile not in [p.Profile for p in self._profile_proxy.Profiles]:
            return False
        try:
            self._profile_proxy.ActiveProfile = profile
            self.profile_changed.emit(profile)
            self.changed.emit()
            return True
        except Exception:
            return False

    def __init__(self):
        super().__init__()
        self._bus = SystemBus()
        self._use_psutil_fallback = False
        self._psutil_battery = None

        # Battery device
        try:
            self._battery = self._bus.get(
                "org.freedesktop.UPower", "/org/freedesktop/UPower/devices/battery_BAT0"
            )
            self._battery.onPropertiesChanged = self.handle_battery_change
        except Exception:
            # Fallback to psutil if UPower is not available
            self._use_psutil_fallback = True
            try:
                self._psutil_battery = psutil.sensors_battery()
                if self._psutil_battery is None:
                    return  # No battery found
                # Start periodic updates for psutil fallback - increased interval
                GLib.timeout_add_seconds(10, self._update_psutil_battery)
            except Exception:
                return  # psutil battery not available either

        # PowerProfiles
        try:
            self._profile_proxy = self._bus.get(
                "net.hadess.PowerProfiles", "/net/hadess/PowerProfiles"
            )
            # Use onPropertiesChanged for consistency with battery device
            self._profile_proxy.onPropertiesChanged = (
                lambda _, changed, __: self._handle_profile_props_changed(changed)
            )
        except Exception:
            self._profile_proxy = None

        self.changed.emit()

    def _update_psutil_battery(self):
        """Update psutil battery data periodically"""
        try:
            self._psutil_battery = psutil.sensors_battery()
            self.changed.emit()
        except Exception:
            pass  # Continue trying
        return True  # Keep the timeout active

    def _handle_profile_props_changed(self, changed):
        """Internal handler for property changes that processes only the changed properties"""
        if "ActiveProfile" in changed:
            new_profile = changed["ActiveProfile"]
            self.profile_changed.emit(new_profile)
            self.changed.emit()

    def handle_battery_change(self, iface, changed, invalidated):
        self.changed.emit()
