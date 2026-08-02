import os
from enum import IntEnum
from glob import glob

from fabric.core.service import Property, Service, Signal
from fabric.utils import Gio, GLib, logger

UPOWER_BUS = "org.freedesktop.UPower"
UPOWER_PATH = "/org/freedesktop/UPower"
DEVICE_IFACE = "org.freedesktop.UPower.Device"
DEVICE_DISPLAY_PATH = "/org/freedesktop/UPower/devices/DisplayDevice"

POWER_PROFILE_BUS = "org.freedesktop.UPower.PowerProfiles"
POWER_PROFILE_PATH = "/org/freedesktop/UPower/PowerProfiles"


class DeviceState(IntEnum):
    UNKNOWN = 0
    CHARGING = 1
    DISCHARGING = 2
    EMPTY = 3
    FULLY_CHARGED = 4
    PENDING_CHARGE = 5
    PENDING_DISCHARGE = 6


class UpDeviceKind(IntEnum):
    UNKNOWN = 0
    LINE_POWER = 1
    BATTERY = 2
    UPS = 3
    MONITOR = 4
    MOUSE = 5
    KEYBOARD = 6
    PDA = 7
    PHONE = 8
    MEDIA_PLAYER = 9
    TABLET = 10
    COMPUTER = 11
    GAMING_INPUT = 12
    PEN = 13
    TOUCHPAD = 14
    HEADSET = 17
    SPEAKERS = 18
    HEADPHONES = 19

    def is_peripheral(self) -> bool:
        return self in (
            self.MOUSE,
            self.KEYBOARD,
            self.GAMING_INPUT,
            self.HEADSET,
            self.HEADPHONES,
            self.TOUCHPAD,
        )

    def is_power_source(self) -> bool:
        return self == self.BATTERY


class PeripheralDeviceKind(IntEnum):
    KEYBOARD = 0
    MOUSE = 1
    HEADPHONES = 2
    GAMEPAD = 3

    def __str__(self) -> str:
        return _PERIPHERAL_NAMES[self]


_PERIPHERAL_NAMES = {
    PeripheralDeviceKind.KEYBOARD: "Keyboard",
    PeripheralDeviceKind.MOUSE: "Mouse",
    PeripheralDeviceKind.HEADPHONES: "Headphones",
    PeripheralDeviceKind.GAMEPAD: "Gamepad",
}

_DEVICE_KIND_TO_PERIPHERAL = {
    UpDeviceKind.MOUSE: PeripheralDeviceKind.MOUSE,
    UpDeviceKind.TOUCHPAD: PeripheralDeviceKind.MOUSE,
    UpDeviceKind.KEYBOARD: PeripheralDeviceKind.KEYBOARD,
    UpDeviceKind.HEADPHONES: PeripheralDeviceKind.HEADPHONES,
    UpDeviceKind.HEADSET: PeripheralDeviceKind.HEADPHONES,
    UpDeviceKind.GAMING_INPUT: PeripheralDeviceKind.GAMEPAD,
}


class BatteryData:
    __slots__ = ("capacity", "is_discharging", "status")

    def __init__(self, capacity: int, status: "BatteryStatus", is_discharging: bool):
        self.capacity = capacity
        self.status = status
        self.is_discharging = is_discharging

    def get_icon_name(self) -> str:
        if self.status == BatteryStatus.CHARGING:
            return "battery-level-04-charging-symbolic"
        if self.status == BatteryStatus.FULL:
            return "battery-full-charged-symbolic"
        return _level_icon(self.capacity)


class BatteryStatus(IntEnum):
    UNKNOWN = 0
    CHARGING = 1
    DISCHARGING = 2
    NOT_CHARGING = 3
    FULL = 4

    def __str__(self) -> str:
        return _STATUS_NAMES[self]


_STATUS_NAMES = {
    BatteryStatus.UNKNOWN: "UNKNOWN",
    BatteryStatus.CHARGING: "CHARGING",
    BatteryStatus.DISCHARGING: "DISCHARGING",
    BatteryStatus.NOT_CHARGING: "NOT_CHARGING",
    BatteryStatus.FULL: "FULLY_CHARGED",
}


def _level_icon(capacity: int) -> str:
    if capacity < 20:
        return "battery-level-00-symbolic"
    if capacity < 40:
        return "battery-level-02-symbolic"
    if capacity < 60:
        return "battery-level-04-symbolic"
    if capacity < 80:
        return "battery-level-06-symbolic"
    return "battery-level-08-symbolic"


_STATE_FROM_RAW = {
    DeviceState.CHARGING: BatteryStatus.CHARGING,
    DeviceState.DISCHARGING: BatteryStatus.DISCHARGING,
    DeviceState.FULLY_CHARGED: BatteryStatus.FULL,
    DeviceState.PENDING_CHARGE: BatteryStatus.NOT_CHARGING,
    DeviceState.PENDING_DISCHARGE: BatteryStatus.NOT_CHARGING,
}


def _state_from_raw(state: int) -> BatteryStatus:
    return _STATE_FROM_RAW.get(state, BatteryStatus.UNKNOWN)


def _device_kind_from_u32(value: int) -> UpDeviceKind:
    try:
        return UpDeviceKind(value)
    except ValueError:
        return UpDeviceKind.UNKNOWN


class Peripheral:
    __slots__ = ("data", "kind", "name", "path")

    def __init__(
        self, name: str, kind: PeripheralDeviceKind, data: BatteryData, path: str
    ):
        self.name = name
        self.kind = kind
        self.data = data
        self.path = path


class ChargeLimit:
    __slots__ = ("device_path", "enabled", "sysfs_path", "threshold")

    def __init__(
        self,
        enabled: bool,
        device_path: str,
        threshold: int | None = None,
        sysfs_path: str | None = None,
    ):
        self.enabled = enabled
        self.device_path = device_path
        self.threshold = threshold
        self.sysfs_path = sysfs_path


class Battery(Service):
    """A service for interacting with the battery's DBus and Power Profiles.

    Use Battery.get_initial() to get the shared singleton instance.
    """

    _instance = None

    @classmethod
    def get_initial(cls) -> "Battery":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @Signal
    def changed(self) -> None: ...

    @Signal
    def power_profile_changed(self) -> None: ...

    @Property(bool, "readable", default_value=False)
    def available(self) -> bool:
        if self._system_battery is not None:
            return True
        return self._do_get_cached_property("IsPresent") or False

    @Property(str, "readable", default_value="")
    def vendor(self) -> str:
        return self._do_get_cached_property("Vendor") or ""

    @Property(int, "readable", default_value=0)
    def percent(self) -> int:
        if self._system_battery is not None:
            return self._system_battery.capacity
        return self._do_get_cached_property("Percentage") or 0

    @Property(bool, "readable", default_value=False)
    def charging(self) -> bool:
        if self._system_battery is not None:
            return self._system_battery.status == BatteryStatus.CHARGING
        return self._raw_state() == DeviceState.CHARGING

    @Property(bool, "readable", default_value=False)
    def discharging(self) -> bool:
        if self._system_battery is not None:
            return self._system_battery.status == BatteryStatus.DISCHARGING
        return self._raw_state() == DeviceState.DISCHARGING

    @Property(bool, "readable", default_value=False)
    def charged(self) -> bool:
        if self._system_battery is not None:
            return self._system_battery.status == BatteryStatus.FULL
        return self._raw_state() == DeviceState.FULLY_CHARGED

    @Property(str, "readable", default_value="")
    def icon_name(self) -> str:
        if self._system_battery is not None:
            return self._system_battery.get_icon_name()
        return self._do_get_cached_property("IconName") or ""

    @Property(int, "readable", default_value=0)
    def time_remaining(self) -> int:
        return self._do_get_cached_property("TimeToEmpty") or 0

    @Property(int, "readable", default_value=0)
    def time_to_full(self) -> int:
        return self._do_get_cached_property("TimeToFull") or 0

    @Property(float, "readable", default_value=0.0)
    def temperature(self) -> float:
        return self._do_get_cached_property("Temperature") or 0.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._bus: Gio.DBusConnection | None = None
        self._display_proxy: Gio.DBusProxy | None = None
        self._power_profile_proxy: Gio.DBusProxy | None = None
        self._prop_cache: dict[str, object] = {}
        self._device_proxies: dict[str, Gio.DBusProxy] = {}
        self._system_battery: BatteryData | None = None
        self._system_battery_paths: list[str] = []
        self._peripherals: list[Peripheral] = []
        self._charge_limit: ChargeLimit | None = None
        self._power_profile: str = ""
        self._toggling_charge_limit: bool = False
        self._do_register()

    def _raw_state(self) -> DeviceState:
        val = self._do_get_cached_property("State")
        if val is None:
            return DeviceState.UNKNOWN
        try:
            return DeviceState(val)
        except ValueError:
            return DeviceState.UNKNOWN

    def _do_register(self) -> None:
        self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)

        self._display_proxy = Gio.DBusProxy.new_sync(
            self._bus,
            Gio.DBusProxyFlags.NONE,
            None,
            UPOWER_BUS,
            DEVICE_DISPLAY_PATH,
            DEVICE_IFACE,
            None,
        )
        logger.info("[Battery] DisplayDevice proxy initialized")

        self._bus.signal_subscribe(
            UPOWER_BUS,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            DEVICE_DISPLAY_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self._do_handle_display_device_change,
        )

        self._do_enumerate_devices()
        self._do_setup_upower_signals()
        self._do_setup_power_profile()

    def _do_enumerate_devices(self) -> None:
        try:
            result = self._bus.call_sync(
                UPOWER_BUS,
                UPOWER_PATH,
                UPOWER_BUS,
                "EnumerateDevices",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            device_paths = result.unpack()[0]
        except Exception as e:
            logger.warning(f"[Battery] Failed to enumerate devices: {e}")
            return

        for path in device_paths:
            self._do_add_device(path)

        self._do_recalculate_system_battery()

    def _do_add_device(self, path: str) -> None:
        try:
            proxy = Gio.DBusProxy.new_sync(
                self._bus,
                Gio.DBusProxyFlags.NONE,
                None,
                UPOWER_BUS,
                path,
                DEVICE_IFACE,
                None,
            )
            self._device_proxies[path] = proxy

            self._bus.signal_subscribe(
                UPOWER_BUS,
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                path,
                None,
                Gio.DBusSignalFlags.NONE,
                self._do_handle_device_change,
            )
        except Exception as e:
            logger.warning(f"[Battery] Failed to create proxy for {path}: {e}")

    def _do_setup_upower_signals(self) -> None:
        try:
            self._bus.signal_subscribe(
                UPOWER_BUS,
                UPOWER_BUS,
                "DeviceAdded",
                UPOWER_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self._do_handle_device_added,
            )
            self._bus.signal_subscribe(
                UPOWER_BUS,
                UPOWER_BUS,
                "DeviceRemoved",
                UPOWER_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self._do_handle_device_removed,
            )
            logger.info("[Battery] UPower device signals subscribed")
        except Exception as e:
            logger.warning(f"[Battery] Failed to setup UPower signals: {e}")

    def _do_setup_power_profile(self) -> None:
        try:
            self._power_profile_proxy = Gio.DBusProxy.new_sync(
                self._bus,
                Gio.DBusProxyFlags.NONE,
                None,
                POWER_PROFILE_BUS,
                POWER_PROFILE_PATH,
                POWER_PROFILE_BUS,
                None,
            )
            result = self._power_profile_proxy.get_cached_property("ActiveProfile")
            if result is not None:
                self._power_profile = result.unpack()

            self._bus.signal_subscribe(
                POWER_PROFILE_BUS,
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                POWER_PROFILE_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self._do_handle_power_profile_change,
            )
            logger.info("[Battery] Power Profiles proxy initialized")
        except Exception as e:
            logger.warning(f"[Battery] Power Profiles daemon not available: {e}")

    def _do_handle_display_device_change(
        self,
        _connection: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _interface: str,
        _signal: str,
        parameters: GLib.Variant,
    ):
        if self._toggling_charge_limit:
            return
        try:
            _iface, changed_props, _invalidated = parameters.unpack()
            for prop_name, value in changed_props.items():
                self._prop_cache[prop_name] = value
        except Exception as e:
            logger.warning(
                f"[Battery] Failed to parse DisplayDevice PropertiesChanged: {e}"
            )
        self.emit("changed")

    def _do_handle_device_change(self, *_args):
        if self._toggling_charge_limit:
            return
        self._do_recalculate_system_battery()
        self._do_recalculate_peripherals()
        self.emit("changed")

    def _do_handle_device_added(self, *_args):
        try:
            result = self._bus.call_sync(
                UPOWER_BUS,
                UPOWER_PATH,
                UPOWER_BUS,
                "EnumerateDevices",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            for path in result.unpack()[0]:
                if path not in self._device_proxies:
                    self._do_add_device(path)
            self._do_recalculate_system_battery()
            self._do_recalculate_peripherals()
            self.emit("changed")
        except Exception as e:
            logger.warning(f"[Battery] Failed to handle DeviceAdded: {e}")

    def _do_handle_device_removed(self, *_args):
        try:
            result = self._bus.call_sync(
                UPOWER_BUS,
                UPOWER_PATH,
                UPOWER_BUS,
                "EnumerateDevices",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            current_paths = set(result.unpack()[0])
            removed = [p for p in self._device_proxies if p not in current_paths]
            for path in removed:
                del self._device_proxies[path]
            if removed:
                self._do_recalculate_system_battery()
                self._do_recalculate_peripherals()
                self.emit("changed")
        except Exception as e:
            logger.warning(f"[Battery] Failed to handle DeviceRemoved: {e}")

    def _do_recalculate_system_battery(self) -> None:
        charging = False
        discharging = False
        pending_charge = False
        pending_discharge = False
        fully_charged_count = 0
        total_devices = 0
        paths = []

        for path, proxy in self._device_proxies.items():
            kind_raw = proxy.get_cached_property("Type")
            power_supply = proxy.get_cached_property("PowerSupply")
            if kind_raw is None or power_supply is None:
                continue
            kind = _device_kind_from_u32(kind_raw.unpack())
            if not kind.is_power_source() or not power_supply.unpack():
                continue

            energy_full_variant = proxy.get_cached_property("EnergyFull")
            if energy_full_variant is not None and energy_full_variant.unpack() == 0.0:
                continue

            state_variant = proxy.get_cached_property("State")
            if state_variant is None:
                continue

            try:
                state = DeviceState(state_variant.unpack())
            except ValueError:
                continue

            total_devices += 1
            paths.append(path)
            if state == DeviceState.CHARGING:
                charging = True
            elif state == DeviceState.DISCHARGING:
                discharging = True
            elif state == DeviceState.FULLY_CHARGED:
                fully_charged_count += 1
            elif state == DeviceState.PENDING_CHARGE:
                pending_charge = True
            elif state == DeviceState.PENDING_DISCHARGE:
                pending_discharge = True

        self._system_battery_paths = paths

        if total_devices == 0:
            self._system_battery = None
            self._charge_limit = None
            return

        if fully_charged_count == total_devices:
            merged_state = DeviceState.FULLY_CHARGED
        elif charging:
            merged_state = DeviceState.CHARGING
        elif discharging:
            merged_state = DeviceState.DISCHARGING
        elif pending_charge:
            merged_state = DeviceState.PENDING_CHARGE
        elif pending_discharge:
            merged_state = DeviceState.PENDING_DISCHARGE
        else:
            merged_state = DeviceState.UNKNOWN

        if len(paths) == 1:
            proxy = self._device_proxies[paths[0]]
            pct_variant = proxy.get_cached_property("Percentage")
            if pct_variant is None:
                self._system_battery = None
                return
            capacity = int(pct_variant.unpack())
        else:
            energy = 0.0
            energy_full = 0.0
            for path in paths:
                proxy = self._device_proxies[path]
                e = proxy.get_cached_property("Energy")
                ef = proxy.get_cached_property("EnergyFull")
                if e is not None:
                    energy += e.unpack()
                if ef is not None:
                    energy_full += ef.unpack()
            if energy_full == 0.0:
                self._system_battery = None
                return
            capacity = int(energy / energy_full * 100.0)

        self._system_battery = BatteryData(
            capacity=capacity,
            status=_state_from_raw(merged_state),
            is_discharging=merged_state == DeviceState.DISCHARGING,
        )

        self._do_recalculate_charge_limit()

    def _do_recalculate_charge_limit(self) -> None:
        self._charge_limit = None

        # Try sysfs first
        sysfs_path = self._find_sysfs_charge_control()
        if sysfs_path is not None:
            try:
                with open(sysfs_path) as f:
                    current = int(f.read().strip())
                enabled = current < 100
                self._charge_limit = ChargeLimit(
                    enabled=enabled,
                    device_path="sysfs",
                    threshold=current if enabled else None,
                    sysfs_path=sysfs_path,
                )
                logger.info(
                    f"[Battery] Charge limit via sysfs: {sysfs_path} = {current}"
                )
                return
            except Exception as e:
                logger.warning(f"[Battery] Failed to read sysfs charge control: {e}")

        # Fall back to UPower D-Bus
        for path in self._system_battery_paths:
            proxy = self._device_proxies.get(path)
            if proxy is None:
                continue
            try:
                introspection = proxy.call_sync(
                    "org.freedesktop.DBus.Introspectable.Introspect",
                    None,
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None,
                )
                xml = introspection.unpack()[0]
                if "EnableChargeThreshold" not in xml:
                    continue

                supported_variant = proxy.get_cached_property(
                    "ChargeThresholdSupported"
                )
                if supported_variant is None or not supported_variant.unpack():
                    continue

                enabled_variant = proxy.get_cached_property("ChargeThresholdEnabled")
                if enabled_variant is None:
                    continue

                self._charge_limit = ChargeLimit(
                    enabled=enabled_variant.unpack(),
                    device_path=path,
                )
                return
            except Exception as e:
                logger.warning(f"[Battery] Failed to check charge limit on {path}: {e}")

    @staticmethod
    def _find_sysfs_charge_control() -> str | None:
        candidates = sorted(glob("/sys/class/power_supply/BAT*"))
        for bat_dir in candidates:
            for name in ("charge_control_end", "charge_control"):
                path = os.path.join(bat_dir, name)
                if os.path.isfile(path) and os.access(path, os.R_OK | os.W_OK):
                    return path
        return None

    def _do_recalculate_peripherals(self) -> None:
        peripherals = []
        for path, proxy in self._device_proxies.items():
            kind_raw = proxy.get_cached_property("Type")
            power_supply = proxy.get_cached_property("PowerSupply")
            if kind_raw is None or power_supply is None:
                continue
            kind = _device_kind_from_u32(kind_raw.unpack())
            if not kind.is_peripheral() or power_supply.unpack():
                continue

            peripheral_kind = _DEVICE_KIND_TO_PERIPHERAL.get(kind)
            if peripheral_kind is None:
                continue

            model_variant = proxy.get_cached_property("Model")
            name = (
                model_variant.unpack()
                if model_variant is not None
                else str(peripheral_kind)
            )

            state_variant = proxy.get_cached_property("State")
            state = (
                DeviceState(state_variant.unpack())
                if state_variant is not None
                else DeviceState.UNKNOWN
            )

            pct_variant = proxy.get_cached_property("Percentage")
            capacity = int(pct_variant.unpack()) if pct_variant is not None else 0

            peripherals.append(
                Peripheral(
                    name=name,
                    kind=peripheral_kind,
                    data=BatteryData(
                        capacity=capacity,
                        status=_state_from_raw(state),
                        is_discharging=state == DeviceState.DISCHARGING,
                    ),
                    path=path,
                )
            )
        self._peripherals = peripherals

    def _do_handle_power_profile_change(self, *_args):
        if self._power_profile_proxy is not None:
            result = self._power_profile_proxy.get_cached_property("ActiveProfile")
            if result is not None:
                self._power_profile = result.unpack()
        self.emit("power_profile_changed")

    def _do_get_cached_property(self, property_name: str):
        result = self._display_proxy.get_cached_property(property_name)
        if result is not None:
            return result.unpack()
        return self._prop_cache.get(property_name)

    def get_power_profile(self) -> str | None:
        if not self._power_profile_proxy:
            return None
        result = self._power_profile_proxy.get_cached_property("ActiveProfile")
        return result.unpack() if result is not None else None

    def set_power_profile(self, profile: str) -> bool:
        if not self._power_profile_proxy:
            return False
        try:
            parameters = GLib.Variant(
                "(ssv)",
                (POWER_PROFILE_BUS, "ActiveProfile", GLib.Variant("s", profile)),
            )
            self._bus.call_sync(
                POWER_PROFILE_BUS,
                POWER_PROFILE_PATH,
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
        if not self._power_profile_proxy:
            return None
        result = self._power_profile_proxy.get_cached_property("Profiles")
        if result is not None:
            profiles_data = result.unpack()
            return [p["Profile"] for p in profiles_data if "Profile" in p]
        return None

    @property
    def charge_limit(self) -> ChargeLimit | None:
        return self._charge_limit

    @property
    def peripherals(self) -> list[Peripheral]:
        return self._peripherals

    @property
    def system_battery(self) -> BatteryData | None:
        return self._system_battery

    def toggle_charge_limit(self) -> bool:
        if self._charge_limit is None:
            return False
        cl = self._charge_limit

        # sysfs path: write directly
        if cl.sysfs_path is not None:
            try:
                target = 100 if cl.enabled else (cl.threshold or 80)
                with open(cl.sysfs_path, "w") as f:
                    f.write(str(target))
                self._charge_limit = ChargeLimit(
                    enabled=target < 100,
                    device_path=cl.device_path,
                    threshold=target if target < 100 else None,
                    sysfs_path=cl.sysfs_path,
                )
                return True
            except Exception as e:
                logger.error(f"[Battery] Failed to toggle sysfs charge limit: {e}")
                return False

        # UPower D-Bus path
        try:
            proxy = self._device_proxies.get(cl.device_path)
            if proxy is None:
                return False
            target = not cl.enabled
            self._toggling_charge_limit = True
            try:
                proxy.call_sync(
                    "EnableChargeThreshold",
                    GLib.Variant("(b)", (target,)),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None,
                )
            finally:
                GLib.idle_add(self._clear_toggling_flag)
            self._charge_limit = ChargeLimit(enabled=target, device_path=cl.device_path)
            return True
        except Exception as e:
            logger.error(f"[Battery] Failed to toggle charge limit: {e}")
            return False

    def get_charge_threshold(self) -> int | None:
        cl = self._charge_limit
        if cl is None:
            return None
        if cl.threshold is not None:
            return cl.threshold
        if cl.enabled:
            return 80
        return 100

    def set_charge_threshold(self, threshold: int) -> bool:
        cl = self._charge_limit
        if cl is None:
            return False

        threshold = max(20, min(100, threshold))

        # sysfs path
        if cl.sysfs_path is not None:
            try:
                with open(cl.sysfs_path, "w") as f:
                    f.write(str(threshold))
                self._charge_limit = ChargeLimit(
                    enabled=threshold < 100,
                    device_path=cl.device_path,
                    threshold=threshold if threshold < 100 else None,
                    sysfs_path=cl.sysfs_path,
                )
                return True
            except Exception as e:
                logger.error(f"[Battery] Failed to set sysfs charge threshold: {e}")
                return False

        # UPower D-Bus: only supports on/off, not percentage
        if threshold < 100 and not cl.enabled:
            return self.toggle_charge_limit()
        if threshold >= 100 and cl.enabled:
            return self.toggle_charge_limit()
        return True

    def _clear_toggling_flag(self) -> bool:
        self._toggling_charge_limit = False
        return False
