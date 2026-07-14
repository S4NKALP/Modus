from collections.abc import Callable
from typing import Any, Concatenate, ParamSpec

from fabric.core.service import Property, Service, Signal
from fabric.utils import Gio, GLib, Gtk, logger

P = ParamSpec("P")

BLUEZ_SERVICE = "org.bluez"
BLUEZ_ADAPTER_IFACE = "org.bluez.Adapter1"
BLUEZ_DEVICE_IFACE = "org.bluez.Device1"
BLUEZ_BATTERY_IFACE = "org.bluez.Battery1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROPS_IFACE = "org.freedesktop.DBus.Properties"


def _unpack_variant(v):
    if v is None:
        return None
    if isinstance(v, GLib.Variant):
        return _unpack_variant(v.unpack())
    if isinstance(v, dict):
        return {k: _unpack_variant(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_unpack_variant(i) for i in v]
    return v


def _make_proxy(bus: Gio.DBusConnection, path: str, iface: str) -> Gio.DBusProxy:
    return Gio.DBusProxy.new_sync(
        bus,
        Gio.DBusProxyFlags.NONE,
        None,
        BLUEZ_SERVICE,
        path,
        iface,
        None,
    )


class BluetoothDevice(Service):
    @Signal
    def changed(self) -> None: ...

    @Property(bool, "read-write", "is-connected", default_value=False)
    def connected(self) -> bool:
        return bool(self._get_prop("Connected"))

    @connected.setter
    def connected(self, value: bool):
        self.connecting = value

    @Property(bool, "read-write", "is-connecting", default_value=False)
    def connecting(self) -> bool:
        return self._connecting

    @connecting.setter
    def connecting(self, value: bool):
        self._connecting = True
        self.notify("connecting")

        def _cb(proxy, res, _):
            try:
                proxy.call_finish(res)
                logger.info(
                    f"[Bluetooth] {'Connected' if value else 'Disconnected'}: {self.address}"
                )
            except Exception as e:
                logger.warning(
                    f"[Bluetooth] connect_device failed for {self.address}: {e}"
                )
            finally:
                self._connecting = False
                self.notify("connecting")
                self.notify("connected")
                self.emit("changed")

        method = "Connect" if value else "Disconnect"
        self._proxy.call(method, None, Gio.DBusCallFlags.NONE, 30000, None, _cb, None)

    @Property(bool, "readable", "is-closed", default_value=False)
    def closed(self) -> bool:
        return self._closed

    @Property(bool, "read-write", "is-paired", default_value=False)
    def paired(self) -> bool:
        return bool(self._get_prop("Paired"))

    @Property(bool, "read-write", "is-trusted", default_value=False)
    def trusted(self) -> bool:
        return bool(self._get_prop("Trusted"))

    @trusted.setter
    def trusted(self, value: bool):
        self._set_prop("Trusted", GLib.Variant("b", value))

    @Property(str, "readable")
    def address(self) -> str:
        return str(self._get_prop("Address") or "")

    @Property(str, "readable")
    def name(self) -> str:
        return str(self._get_prop("Name") or self._get_prop("Alias") or "")

    @Property(str, "readable")
    def alias(self) -> str:
        return str(self._get_prop("Alias") or "")

    @Property(str, "readable")
    def icon_name(self) -> str:
        return str(self._get_prop("Icon") or "bluetooth")

    @Property(str, "readable")
    def type(self) -> str:
        return _icon_to_type(str(self._get_prop("Icon") or ""))

    @Property(float, "readable")
    def battery_percentage(self) -> float:
        return float(self._get_battery_prop("Percentage") or 0.0)

    def __init__(
        self, bus: Gio.DBusConnection, object_path: str, props: dict, **kwargs
    ):
        super().__init__(**kwargs)
        self._bus = bus
        self._object_path = object_path
        self._props: dict = props
        self._connecting = False
        self._closed = False
        self._prop_sub_id: int = 0
        self._battery_sub_id: int = 0
        self._battery_proxy: Gio.DBusProxy | None = None

        self._proxy = _make_proxy(bus, object_path, BLUEZ_DEVICE_IFACE)

        try:
            self._battery_proxy = _make_proxy(bus, object_path, BLUEZ_BATTERY_IFACE)
        except Exception as e:
            # Battery1 is optional — not all devices expose it
            logger.warning(
                f"[bluetooth] self._battery_proxy = _make_proxy(bus, object_path, BLUEZ... failed: {e}"
            )

        # Subscribe to Device1 PropertiesChanged
        self._prop_sub_id = bus.signal_subscribe(
            BLUEZ_SERVICE,
            DBUS_PROPS_IFACE,
            "PropertiesChanged",
            object_path,
            BLUEZ_DEVICE_IFACE,  # filter to Device1 only
            Gio.DBusSignalFlags.NONE,
            self._on_properties_changed,
            None,
        )

        self._battery_sub_id = bus.signal_subscribe(
            BLUEZ_SERVICE,
            DBUS_PROPS_IFACE,
            "PropertiesChanged",
            object_path,
            BLUEZ_BATTERY_IFACE,  # filter to Battery1 only
            Gio.DBusSignalFlags.NONE,
            self._on_battery_properties_changed,
            None,
        )

    def _get_prop(self, name: str):
        try:
            v = self._proxy.get_cached_property(name)
            if v is not None:
                return v.unpack()
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        return _unpack_variant(self._props.get(name))

    def _set_prop(self, name: str, value: GLib.Variant):
        """Set a property on the Device1 interface via D-Bus Properties.Set."""
        try:
            self._proxy.call_sync(
                "org.freedesktop.DBus.Properties.Set",
                GLib.Variant("(ssv)", (BLUEZ_DEVICE_IFACE, name, value)),
                Gio.DBusCallFlags.NONE,
                5000,
                None,
            )
        except Exception as e:
            logger.warning(f"[Bluetooth] Set {name} on {self._object_path} failed: {e}")

    def _get_battery_prop(self, name: str):
        if not self._battery_proxy:
            return None
        try:
            v = self._battery_proxy.get_cached_property(name)
            return v.unpack() if v else None
        except Exception as e:
            logger.warning(
                f"[bluetooth] v = self._battery_proxy.get_cached_property(name) failed: {e}"
            )
            return None

    def _on_properties_changed(
        self, _conn, _sender, _path, _iface, _signal, params, _data
    ):
        changed = _unpack_variant(params)[1] if params else {}
        self._props.update(changed)
        prop_map = {
            "Connected": "connected",
            "Paired": "paired",
            "Trusted": "trusted",
            "Name": "name",
            "Alias": "alias",
            "Icon": "icon-name",
            "RSSI": "rssi",
            "UUIDs": "uuids",
            "Appearance": "appearance",
            "Class": "device-class",
        }
        for bluez_key, fabric_prop in prop_map.items():
            if bluez_key in changed:
                self.notify(fabric_prop)
        self.emit("changed")

    def _on_battery_properties_changed(
        self, _conn, _sender, _path, _iface, _signal, params, _data
    ):
        changed = _unpack_variant(params)[1] if params else {}
        if "Percentage" in changed:
            self.notify("battery-level")
            self.notify("battery-percentage")
            self.emit("changed")

    def pair(self, callback: Callable | None = None):
        """Initiate pairing with the device."""

        def _cb(proxy, res, _):
            try:
                proxy.call_finish(res)
                logger.info(f"[Bluetooth] Paired: {self.address}")
            except Exception as e:
                logger.warning(f"[Bluetooth] Pair failed for {self.address}: {e}")
            finally:
                self.notify("paired")
                self.emit("changed")
                if callback:
                    callback(self.paired)

        self._proxy.call("Pair", None, Gio.DBusCallFlags.NONE, 60000, None, _cb, None)

    def remove(self):
        """Remove/forget the device (must be called on the adapter)."""
        # Removal is done via Adapter1.RemoveDevice — expose a convenience
        # flag so the adapter can act on it.
        logger.info(f"[Bluetooth] Remove requested for: {self.address}")
        self.emit("changed")

    def trust(self):
        """Mark the device as trusted."""
        self.trusted = True

    def untrust(self):
        """Mark the device as untrusted."""
        self._set_prop("Trusted", GLib.Variant("b", False))
        self.notify("trusted")
        self.emit("changed")

    def close(self):
        if self._prop_sub_id:
            self._bus.signal_unsubscribe(self._prop_sub_id)
            self._prop_sub_id = 0
        if self._battery_sub_id:
            self._bus.signal_unsubscribe(self._battery_sub_id)
            self._battery_sub_id = 0
        self._closed = True
        self.notify("closed")

    def connect_device(
        self,
        connect: bool = True,
        callback: Callable[Concatenate[bool, P], Any] | None = None,
        *args: P.args,
        **kwargs: P.kwargs,
    ):
        self.connecting = connect
        if callback:

            def _once(*_):
                callback(self.connected, *args, **kwargs)
                self.disconnect(_id)

            _id = self.connect("changed", _once)

    def notifier(self, name: str, args=None):
        self.notify(name)
        self.emit("changed")


class BluetoothAdapter(Service):
    @Signal
    def changed(self) -> None: ...

    @Signal
    def device_added(self, address: str) -> None: ...

    @Signal
    def device_removed(self, address: str) -> None: ...

    @Property(list, "readable")
    def devices(self) -> list:
        return list(self._devices.values())

    @Property(list, "readable")
    def connected_devices(self) -> list:
        return [d for d in self._devices.values() if d.connected]

    @Property(str, "readable")
    def object_path(self) -> str:
        return self._object_path

    @Property(str, "readable")
    def address(self) -> str:
        return str(self._get_prop("Address") or "")

    @Property(str, "readable")
    def name(self) -> str:
        return str(
            self._get_prop("Name") or self._get_prop("Alias") or self._object_path
        )

    @Property(str, "readable")
    def state(self) -> str:
        if not self._get_prop("Powered"):
            return "off"
        if self._get_prop("Discovering"):
            return "discovering"
        return "on"

    @Property(bool, "read-write", default_value=False)
    def powered(self) -> bool:
        return bool(self._get_prop("Powered"))

    @powered.setter
    def powered(self, value: bool):
        self._set_prop("Powered", GLib.Variant("b", value))

    @Property(bool, "read-write", default_value=False)
    def enabled(self) -> bool:
        return self.powered

    @enabled.setter
    def enabled(self, value: bool):
        self.powered = value

    @Property(bool, "read-write", default_value=False)
    def scanning(self) -> bool:
        return bool(self._get_prop("Discovering"))

    @scanning.setter
    def scanning(self, value: bool):
        if value == self.scanning:
            return
        method = "StartDiscovery" if value else "StopDiscovery"
        self._proxy.call(
            method,
            None,
            Gio.DBusCallFlags.NONE,
            10000,
            None,
            lambda p, r, _: self._finish_call(p, r, method),
            None,
        )

    def __init__(
        self, bus: Gio.DBusConnection, object_path: str, props: dict, **kwargs
    ):
        super().__init__(**kwargs)
        self._bus = bus
        self._object_path = object_path
        self._props: dict = props

        self._devices: dict[str, BluetoothDevice] = {}
        self._device_changed_ids: dict[str, int] = {}
        self._prop_sub_id: int = 0
        self._scan_timeout_id: int = 0

        self._proxy = _make_proxy(bus, object_path, BLUEZ_ADAPTER_IFACE)

        self._prop_sub_id = bus.signal_subscribe(
            BLUEZ_SERVICE,
            DBUS_PROPS_IFACE,
            "PropertiesChanged",
            object_path,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_properties_changed,
            None,
        )

    def _get_prop(self, name: str):
        try:
            v = self._proxy.get_cached_property(name)
            if v is not None:
                return v.unpack()
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        return _unpack_variant(self._props.get(name))

    def _set_prop(self, name: str, value: GLib.Variant):
        try:
            self._proxy.call_sync(
                "org.freedesktop.DBus.Properties.Set",
                GLib.Variant("(ssv)", (BLUEZ_ADAPTER_IFACE, name, value)),
                Gio.DBusCallFlags.NONE,
                5000,
                None,
            )
        except Exception as e:
            logger.warning(f"[Bluetooth] Set {name} on {self._object_path} failed: {e}")

    def _finish_call(self, proxy, res, method: str):
        try:
            proxy.call_finish(res)
        except Exception as e:
            logger.warning(f"[Bluetooth] {method} on {self._object_path} failed: {e}")

    def _on_properties_changed(
        self, _conn, _sender, _path, _iface, _signal, params, _data
    ):
        changed = _unpack_variant(params)[1] if params else {}
        self._props.update(changed)
        for key in ("Powered", "Discovering"):
            if key in changed:
                self.notify("powered" if key == "Powered" else "scanning")
                self.notify("enabled")
                self.notify("state")
        self.emit("changed")

    def add_device(self, object_path: str, props: dict):
        addr: str = props.get("Address", _path_to_addr(object_path))
        if addr in self._devices:
            return

        device = BluetoothDevice(
            self._bus,
            object_path,
            props,
            on_changed=lambda *_: self.emit("changed"),
        )
        self._devices[addr] = device

        handler_id = device.connect(
            "changed",
            lambda *_: self.notify("connected-devices"),
        )
        self._device_changed_ids[addr] = handler_id

        logger.info(f"[Bluetooth:{self.name}] Adding device: {addr}")
        self.emit("device-added", addr)
        self.notify("devices")
        self.notify("connected-devices")
        self.emit("changed")

    def remove_device(self, object_path: str):
        addr = _path_to_addr(object_path)
        device = self._devices.pop(addr, None)
        if not device:
            return

        logger.info(f"[Bluetooth:{self.name}] Removing device: {addr}")

        handler_id = self._device_changed_ids.pop(addr, None)
        if handler_id is not None:
            try:
                device.disconnect(handler_id)
            except Exception as e:
                logger.warning(f"[bluetooth] device.disconnect(handler_id) failed: {e}")

        self.emit("device-removed", addr)
        if device.connected:
            self.notify("connected-devices")
        self.notify("devices")
        self.emit("changed")

        device.close()

    def remove_device_from_bluez(self, device: "BluetoothDevice"):
        """Call Adapter1.RemoveDevice to unpair/forget the device entirely."""
        try:
            self._proxy.call_sync(
                "RemoveDevice",
                GLib.Variant("(o)", (device._object_path,)),
                Gio.DBusCallFlags.NONE,
                10000,
                None,
            )
            logger.info(f"[Bluetooth:{self.name}] Removed device: {device.address}")
        except Exception as e:
            logger.warning(f"[Bluetooth] RemoveDevice failed for {device.address}: {e}")

    def get_device(self, address: str) -> BluetoothDevice | None:
        return self._devices.get(address)

    def scan(self, duration_ms: int = 10_000):
        """Start discovery and automatically stop after duration_ms."""
        if self._scan_timeout_id:
            GLib.source_remove(self._scan_timeout_id)
            self._scan_timeout_id = 0

        self.scanning = True

        def _stop():
            self.scanning = False
            self._scan_timeout_id = 0
            return False

        self._scan_timeout_id = GLib.timeout_add(duration_ms, _stop)

    def stop_scan(self):
        if self._scan_timeout_id:
            GLib.source_remove(self._scan_timeout_id)
            self._scan_timeout_id = 0
        self.scanning = False

    def toggle_scan(self):
        if self.scanning:
            self.stop_scan()
        else:
            self.scan()

    def close(self):
        if self._scan_timeout_id:
            GLib.source_remove(self._scan_timeout_id)
            self._scan_timeout_id = 0
        if self._prop_sub_id:
            self._bus.signal_unsubscribe(self._prop_sub_id)
            self._prop_sub_id = 0
        for device in list(self._devices.values()):
            device.close()
        self._devices.clear()
        self._device_changed_ids.clear()

    def notifier(self, name: str, *args):
        self.notify(name)
        self.emit("changed")


class BluetoothClient(Service):
    @Signal
    def changed(self) -> None: ...

    @Signal
    def closed(self) -> None: ...

    @Signal
    def device_added(self, address: str) -> None: ...

    @Signal
    def device_removed(self, address: str) -> None: ...

    @Property(list, "readable")
    def adapters(self) -> list:
        return list(self._adapters.values())

    @Property(list, "readable")
    def devices(self) -> list:
        return [d for a in self._adapters.values() for d in a.devices]

    @Property(list, "readable")
    def connected_devices(self) -> list:
        return [d for d in self.devices if d.connected]

    @Property(str, "readable")
    def state(self) -> str:
        for a in self._adapters.values():
            if a.powered:
                return a.state
        return "absent" if not self._adapters else "off"

    @Property(bool, "read-write", default_value=False)
    def enabled(self) -> bool:
        return any(a.powered for a in self._adapters.values())

    @enabled.setter
    def enabled(self, value: bool):
        for a in self._adapters.values():
            a.powered = value

    @Property(bool, "read-write", default_value=False)
    def scanning(self) -> bool:
        return any(a.scanning for a in self._adapters.values())

    @scanning.setter
    def scanning(self, value: bool):
        for a in self._adapters.values():
            if a.powered:
                a.scanning = value

    @Property(bool, "read-write", "is-powered", default_value=False)
    def powered(self) -> bool:
        return self.enabled

    @powered.setter
    def powered(self, value: bool):
        self.enabled = value

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._adapters: dict[str, BluetoothAdapter] = {}
        self._bus: Gio.DBusConnection | None = None
        self._om_proxy: Gio.DBusProxy | None = None
        self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        self._om_proxy = Gio.DBusProxy.new_sync(
            self._bus,
            Gio.DBusProxyFlags.NONE,
            None,
            BLUEZ_SERVICE,
            "/",
            DBUS_OM_IFACE,
            None,
        )

        self._bus.signal_subscribe(
            BLUEZ_SERVICE,
            DBUS_OM_IFACE,
            "InterfacesAdded",
            None,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_interfaces_added,
            None,
        )
        self._bus.signal_subscribe(
            BLUEZ_SERVICE,
            DBUS_OM_IFACE,
            "InterfacesRemoved",
            None,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_interfaces_removed,
            None,
        )

        self._populate_from_object_manager()

    def _populate_from_object_manager(self):
        try:
            result = self._om_proxy.call_sync(
                "GetManagedObjects", None, Gio.DBusCallFlags.NONE, 5000, None
            )
            objects = _unpack_variant(result)[0]
        except Exception as e:
            logger.warning(f"[Bluetooth] GetManagedObjects failed: {e}")
            return

        for path, ifaces in objects.items():
            if BLUEZ_ADAPTER_IFACE in ifaces:
                self._add_adapter(path, ifaces[BLUEZ_ADAPTER_IFACE])

        for path, ifaces in objects.items():
            if BLUEZ_DEVICE_IFACE in ifaces:
                self._add_device(path, ifaces[BLUEZ_DEVICE_IFACE])

    def _add_adapter(self, path: str, props: dict):
        if path in self._adapters:
            return
        logger.info(f"[Bluetooth] Adding adapter: {path}")
        adapter = BluetoothAdapter(
            self._bus,
            path,
            props,
            on_changed=lambda *_: self.emit("changed"),
        )
        adapter.connect(
            "device-added",
            lambda a, addr: (
                self.emit("device-added", addr),
                self.notify("devices"),
                self.notify("connected-devices"),
                self.emit("changed"),
            ),
        )
        adapter.connect(
            "device-removed",
            lambda a, addr: (
                self.emit("device-removed", addr),
                self.notify("devices"),
                self.notify("connected-devices"),
                self.emit("changed"),
            ),
        )
        adapter.connect(
            "notify::connected-devices",
            lambda *_: self.notify("connected-devices"),
        )
        self._adapters[path] = adapter
        self.notify("adapters")
        self.emit("changed")

    def _add_device(self, path: str, props: dict):
        adapter_path = _device_path_to_adapter_path(path)
        adapter = self._adapters.get(adapter_path)
        if not adapter:
            logger.warning(f"[Bluetooth] No adapter found for device at {path}")
            return

        adapter.add_device(path, props)

    def _on_interfaces_added(
        self, _conn, _sender, _path, _iface, _signal, params, _data
    ):
        unpacked = _unpack_variant(params)
        obj_path: str = unpacked[0]
        ifaces: dict = unpacked[1]

        if BLUEZ_ADAPTER_IFACE in ifaces:
            self._add_adapter(obj_path, ifaces[BLUEZ_ADAPTER_IFACE])
        if BLUEZ_DEVICE_IFACE in ifaces:
            self._add_device(obj_path, ifaces[BLUEZ_DEVICE_IFACE])

    def _on_interfaces_removed(
        self, _conn, _sender, _path, _iface, _signal, params, _data
    ):
        unpacked = _unpack_variant(params)
        obj_path: str = unpacked[0]
        ifaces: list = unpacked[1]

        if BLUEZ_ADAPTER_IFACE in ifaces:
            adapter = self._adapters.pop(obj_path, None)
            if adapter:
                logger.info(f"[Bluetooth] Removing adapter: {obj_path}")
                adapter.close()
                self.notify("adapters")
                self.emit("changed")

        if BLUEZ_DEVICE_IFACE in ifaces:
            adapter_path = _device_path_to_adapter_path(obj_path)
            adapter = self._adapters.get(adapter_path)
            if adapter:
                adapter.remove_device(obj_path)

    def scan(self):
        for a in self._adapters.values():
            if a.powered:
                a.scan()

    def toggle_scan(self):
        for a in self._adapters.values():
            if a.powered:
                a.toggle_scan()

    def get_device(self, address: str) -> BluetoothDevice | None:
        for adapter in self._adapters.values():
            if d := adapter.get_device(address):
                return d
        return None

    def connect_device(
        self,
        device: BluetoothDevice,
        connect: bool = True,
        callback: Callable[Concatenate[bool, P], Any] | None = None,
        *args: P.args,
        **kwargs: P.kwargs,
    ):
        return device.connect_device(connect, callback, *args, **kwargs)

    def remove_device(self, device: BluetoothDevice):
        """Unpair/forget a device via its adapter's RemoveDevice call."""
        adapter_path = _device_path_to_adapter_path(device._object_path)
        adapter = self._adapters.get(adapter_path)
        if adapter:
            adapter.remove_device_from_bluez(device)
        else:
            logger.warning(
                f"[Bluetooth] Cannot remove {device.address}: adapter not found"
            )

    def notifier(self, name: str, *args):
        self.notify(name)
        self.emit("changed")


def _device_path_to_adapter_path(device_path: str) -> str:
    parts = device_path.rsplit("/", 1)
    return parts[0] if len(parts) == 2 else device_path


def _path_to_addr(object_path: str) -> str:
    return object_path.split("/")[-1][4:].replace("_", ":")


def _icon_to_type(icon: str) -> str:
    """Resolve a Bluez icon name to a GTK symbolic icon via the current theme.

    Checks the icon theme for the icon (with ``-symbolic`` suffix) and falls
    back to a hardcoded mapping when the theme doesn't provide it.
    """
    if icon:
        icon_theme = Gtk.IconTheme.get_default()
        symbolic = f"{icon}-symbolic"
        if icon_theme.has_icon(symbolic):
            return symbolic
        if icon_theme.has_icon(icon):
            return icon

    return {
        "audio-headset": "audio-headset-symbolic",
        "audio-headphones": "audio-headphones-symbolic",
        "audio-speakers": "audio-speakers-symbolic",
        "audio-card": "audio-speakers-symbolic",
        "input-keyboard": "input-keyboard-symbolic",
        "input-mouse": "input-mouse-symbolic",
        "input-gaming": "input-gaming-symbolic",
        "phone": "phone-symbolic",
        "printer": "printer-symbolic",
    }.get(icon, "bluetooth-symbolic")
