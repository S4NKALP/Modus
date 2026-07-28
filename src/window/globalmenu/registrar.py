"""AppMenu Registrar — D-Bus service for com.canonical.AppMenu.Registrar.

GTK apps with appmenu-gtk-module loaded call RegisterWindow(windowId,
objectPath) on this service to announce that they export a dbusmenu at the
given object path on their own bus name.  We store those registrations and
expose GetMenuForWindow so the global menu bar can look them up.

Follows NovaBar's clean Registrar pattern — standalone singleton with
hash-table storage and proper D-Bus skeleton.
"""

from dataclasses import dataclass
from typing import Optional

from fabric.utils import Gio, GLib, logger


@dataclass
class MenuRegistration:
    """Registration entry for a window's menu."""

    window_id: int
    bus_name: str
    object_path: str


REGISTRAR_XML = """
<node>
  <interface name="com.canonical.AppMenu.Registrar">
    <method name="RegisterWindow">
      <arg type="u" name="windowId" direction="in"/>
      <arg type="o" name="menuObjectPath" direction="in"/>
    </method>
    <method name="UnregisterWindow">
      <arg type="u" name="windowId" direction="in"/>
    </method>
    <method name="GetMenuForWindow">
      <arg type="u" name="windowId" direction="in"/>
      <arg type="s" name="service" direction="out"/>
      <arg type="o" name="menuObjectPath" direction="out"/>
    </method>
    <method name="GetMenus">
      <arg type="a(uso)" name="menus" direction="out"/>
    </method>
  </interface>
</node>
"""


class Registrar:
    """Singleton D-Bus service implementing com.canonical.AppMenu.Registrar.

    Mirrors NovaBar's ``GlobalMenu.Registrar`` — owns the well-known bus
    name, stores window→menu registrations, and exposes ``GetMenuForWindow``.
    """

    _instance: Optional["Registrar"] = None

    @classmethod
    def get_instance(cls) -> "Registrar":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._registrations: dict[int, MenuRegistration] = {}
        self._bus_owner_id: Optional[int] = None
        self._registration_id: Optional[int] = None
        self._connection: Optional[Gio.DBusConnection] = None

    # ---- Public API ----

    def start(self):
        """Acquire the bus name and export the D-Bus object."""
        try:
            bus = _get_bus()
            node = Gio.DBusNodeInfo.new_for_xml(REGISTRAR_XML)
            self._registration_id = bus.register_object(
                "/com/canonical/AppMenu/Registrar",
                node.interfaces[0],
                self._handle_method,
                None,
                None,
            )
            Gio.bus_own_name_on_connection(
                bus,
                "com.canonical.AppMenu.Registrar",
                Gio.BusNameOwnerFlags.NONE,
                None,
                None,
            )
            self._connection = bus
            logger.info("[Registrar] AppMenu Registrar D-Bus service started")
        except Exception as e:
            logger.error(f"[Registrar] Failed to start: {e}")

    def stop(self):
        """Release the bus name and unregister the object."""
        if self._connection and self._registration_id is not None:
            try:
                self._connection.unregister_object(self._registration_id)
            except Exception as e:
                logger.warning(f"[Registrar] Failed to unregister object: {e}")
            self._registration_id = None

    def get_menu_for_window(self, window_id: int) -> Optional[MenuRegistration]:
        """Look up the menu registration for a window."""
        return self._registrations.get(window_id)

    def get_menu_for_bus_name(self, bus_name: str) -> Optional[MenuRegistration]:
        """Look up the menu registration by D-Bus bus name."""
        for reg in self._registrations.values():
            if reg.bus_name == bus_name:
                return reg
        return None

    def get_all_registrations(self) -> dict[int, MenuRegistration]:
        """Return a copy of all current registrations."""
        return dict(self._registrations)

    # ---- Internal ----

    def register_window(self, window_id: int, sender: str, menu_path: str):
        """Store a window→menu registration."""
        reg = MenuRegistration(
            window_id=window_id,
            bus_name=sender,
            object_path=menu_path,
        )
        self._registrations[window_id] = reg
        logger.debug(
            f"[Registrar] Registered window {window_id} -> {sender} {menu_path}"
        )

    def unregister_window(self, window_id: int):
        """Remove a window registration."""
        self._registrations.pop(window_id, None)
        logger.debug(f"[Registrar] Unregistered window {window_id}")

    def _handle_method(
        self,
        connection,
        sender,
        object_path,
        _interface_name,
        method_name,
        parameters,
        invocation,
    ):
        """D-Bus method dispatcher."""
        try:
            if method_name == "RegisterWindow":
                window_id, menu_path = parameters.unpack()
                self.register_window(window_id, sender, str(menu_path))
                invocation.return_value(None)

            elif method_name == "UnregisterWindow":
                window_id = parameters.unpack()[0]
                self.unregister_window(window_id)
                invocation.return_value(None)

            elif method_name == "GetMenuForWindow":
                window_id = parameters.unpack()[0]
                reg = self.get_menu_for_window(window_id)
                if reg:
                    invocation.return_value(
                        GLib.Variant("(so)", (reg.bus_name, reg.object_path))
                    )
                else:
                    invocation.return_value(
                        GLib.Variant("(so)", (sender, "/com/canonical/menu/0"))
                    )

            elif method_name == "GetMenus":
                menus = [
                    (0, reg.bus_name, reg.object_path)
                    for reg in self._registrations.values()
                ]
                invocation.return_value(GLib.Variant("(a(uso))", (menus,)))

        except Exception as e:
            logger.error(f"[Registrar] D-Bus method {method_name} failed: {e}")
            invocation.return_error_literal(Gio.DBusError.FAILED, "FAILED", str(e))


def _get_bus() -> Gio.DBusConnection:
    """Get or create the shared session bus connection."""
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)
