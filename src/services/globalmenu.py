"""Global Menu Service - extracts and manages application menus.

Uses the pure Python DBusMenu extractor via Gio.DBus.
"""

import threading
import json
import subprocess
from typing import Optional, List

from fabric.core.service import Property, Service, Signal
from fabric.utils import logger
from gi.repository import Gio, GLib

from utils.dbusmenu import DBusMenuClient, DBusMenuItem

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


class GlobalMenuService(Service):
    """Service that extracts and provides application menus for the global menu bar."""

    @Signal
    def menu_changed(self, menu_items: object) -> None: ...

    @Signal
    def active_app_changed(self, app_name: str, wm_class: str) -> None: ...

    @Property(object, flags="read-write")
    def current_menu(self) -> Optional[List[DBusMenuItem]]:
        return self._current_menu

    @Property(str, flags="read-write")
    def current_app(self) -> str:
        return self._current_app

    @Property(str, flags="read-write")
    def current_wm_class(self) -> str:
        return self._current_wm_class

    def __init__(self):
        super().__init__()
        self._current_menu: Optional[List[DBusMenuItem]] = None
        self._current_app: str = ""
        self._current_wm_class: str = ""

        # Cache holds DBusMenuClient instances
        self._client_cache: dict[str, Optional[DBusMenuClient]] = {}
        # Cache holds the extracted top-level menus
        self._menu_cache: dict[str, Optional[List[DBusMenuItem]]] = {}

        # Registrar mapping: sender -> object_path
        self._registered_menus: dict[str, str] = {}
        self._setup_registrar()

        self._lock = threading.Lock()
        self._extraction_seq = 0  # Monotonic counter to discard stale results

        logger.info(
            "[GlobalMenuService] Initialized native Python DBusMenu parser successfully"
        )

    def _setup_registrar(self):
        """Host the AppMenu Registrar on DBus to allow GTK/KDE apps to register menus."""
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._node = Gio.DBusNodeInfo.new_for_xml(REGISTRAR_XML)
            self._reg_id = self._bus.register_object(
                "/com/canonical/AppMenu/Registrar",
                self._node.interfaces[0],
                self._handle_registrar_method,
                None,
                None,
            )
            Gio.bus_own_name_on_connection(
                self._bus,
                "com.canonical.AppMenu.Registrar",
                Gio.BusNameOwnerFlags.NONE,
                None,
                None,
            )
            logger.info("[GlobalMenuService] AppMenu Registrar DBus service started")
        except Exception as e:
            logger.error(f"[GlobalMenuService] Failed to start Registrar: {e}")

    def _handle_registrar_method(
        self,
        connection,
        sender,
        object_path,
        interface_name,
        method_name,
        parameters,
        invocation,
    ):
        """Handles incoming DBus requests from apps registering their menus."""
        try:
            if method_name == "RegisterWindow":
                window_id, menu_path = parameters.unpack()
                logger.debug(
                    f"[GlobalMenuService] App {sender} registered menu {menu_path} for window {window_id}"
                )
                self._registered_menus[sender] = menu_path
                invocation.return_value(None)

            elif method_name == "UnregisterWindow":
                invocation.return_value(None)

            elif method_name == "GetMenuForWindow":
                invocation.return_value(
                    GLib.Variant("(so)", (sender, "/com/canonical/menu/0"))
                )

            elif method_name == "GetMenus":
                invocation.return_value(GLib.Variant("(a(uso))", ([])))
        except Exception as e:
            logger.error(
                f"[GlobalMenuService] Error handling Registrar method {method_name}: {e}"
            )
            invocation.return_error_literal(Gio.DBusError.FAILED, str(e))

    def update_active_window(self, app_name: str, wm_class: str):
        """Called when the active window changes. Triggers menu extraction."""
        if wm_class == self._current_wm_class:
            return

        logger.info(
            f"[GlobalMenuService] Active window changed: {app_name} ({wm_class})"
        )
        self._current_app = app_name
        self._current_wm_class = wm_class
        self._extraction_seq += 1
        seq = self._extraction_seq
        self.active_app_changed(app_name, wm_class)

        # Check cache first
        if wm_class in self._menu_cache and wm_class in self._client_cache:
            cached_menu = self._menu_cache[wm_class]
            self._current_menu = cached_menu
            logger.info(f"[GlobalMenuService] Cache hit for '{wm_class}'")
            self.menu_changed(cached_menu if cached_menu else [])
            return

        # Clear menu immediately for new app while extraction runs
        self._current_menu = None
        self.menu_changed([])

        # Extract menu in background thread
        logger.info(f"[GlobalMenuService] Starting extraction for '{wm_class}'")
        thread = threading.Thread(
            target=self._extract_menu,
            args=(wm_class, seq),
            daemon=True,
        )
        thread.start()

    def _discover_dbus_client(self) -> Optional[DBusMenuClient]:
        """Discovers the DBusMenu object path for the active Wayland window using Gio.DBus."""
        try:
            out = subprocess.check_output(["hyprctl", "activewindow", "-j"], timeout=2)
            data = json.loads(out)
            target_pid = data.get("pid", 0)

            if target_pid <= 0:
                return None

            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            res = bus.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "ListNames",
                None,
                GLib.VariantType("(as)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            names = res.get_child_value(0).unpack()

            for svc in names:
                if (
                    svc.startswith("org.freedesktop.systemd")
                    or svc.startswith("org.freedesktop.login1")
                    or svc == "org.freedesktop.DBus"
                ):
                    continue

                try:
                    pid_res = bus.call_sync(
                        "org.freedesktop.DBus",
                        "/org/freedesktop/DBus",
                        "org.freedesktop.DBus",
                        "GetConnectionUnixProcessID",
                        GLib.Variant("(s)", (svc,)),
                        GLib.VariantType("(u)"),
                        Gio.DBusCallFlags.NONE,
                        1000,
                        None,
                    )
                    pid = pid_res.get_child_value(0).get_uint32()

                    if pid == target_pid:
                        # 1. Check if this app explicitly registered its menu via Registrar
                        if svc in self._registered_menus:
                            path = self._registered_menus[svc]
                            logger.info(
                                f"[GlobalMenuService] Found Registrar path {path} for {svc}"
                            )
                            return DBusMenuClient(svc, path)

                        # 2. Fallback to common paths
                        for path in [
                            "/com/canonical/menu/0",
                            "/com/canonical/menu/1",
                            "/MenuBar",
                            "/MenuBar/1",
                            "/org/xfce/Thunar/menus/menubar/0",
                            "/com/canonical/AppMenu/Registrar/0",
                        ]:
                            try:
                                introspect_res = bus.call_sync(
                                    svc,
                                    path,
                                    "org.freedesktop.DBus.Introspectable",
                                    "Introspect",
                                    None,
                                    GLib.VariantType("(s)"),
                                    Gio.DBusCallFlags.NONE,
                                    500,
                                    None,
                                )
                                xml = introspect_res.get_child_value(0).get_string()
                                if "com.canonical.dbusmenu" in xml:
                                    logger.info(
                                        f"[GlobalMenuService] Discovered DBusMenu natively at {svc} {path}"
                                    )
                                    return DBusMenuClient(svc, path)
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[GlobalMenuService] DBus discovery failed: {e}")

        return None

    def _extract_menu(self, wm_class: str, seq: int):
        """Extract menu for a given WM class in a background thread."""
        try:
            client = self._discover_dbus_client()
            items = []

            if client:
                items = client.get_layout()

            with self._lock:
                self._client_cache[wm_class] = client
                self._menu_cache[wm_class] = items

                if items:
                    logger.info(
                        f"[GlobalMenuService] Found menu for '{wm_class}': {len(items)} items"
                    )
                else:
                    logger.info(
                        f"[GlobalMenuService] No DBus menu found for '{wm_class}'"
                    )

            # Only update UI if this extraction is still current
            if seq != self._extraction_seq:
                return

            # Update UI on main thread via GLib idle
            GLib.idle_add(self._emit_menu_changed, items)

        except Exception as e:
            logger.error(
                f"[GlobalMenuService] Error extracting menu for '{wm_class}': {e}"
            )

    def _emit_menu_changed(self, items: List[DBusMenuItem]):
        """Emit menu_changed signal on the main thread."""
        self._current_menu = items
        self.menu_changed(items)
        return False  # Remove from idle queue

    def click_item(self, item_id: int) -> bool:
        """Click a menu item by ID."""
        client = self._client_cache.get(self._current_wm_class)
        if client:
            client.click_item(item_id)
            return True
        return False

    def about_to_show(self, item_id: int) -> bool:
        """Triggers the AboutToShow event on a DBusMenu item."""
        client = self._client_cache.get(self._current_wm_class)
        if client:
            return client.about_to_show(item_id)
        return False

    def refresh_menu_sync(self) -> List[DBusMenuItem]:
        """Synchronously refetches the menu for the current app."""
        client = self._client_cache.get(self._current_wm_class)
        if client:
            items = client.get_layout()
            with self._lock:
                self._menu_cache[self._current_wm_class] = items
            return items
        return []


_global_menu_svc_instance = None


def get_global_menu_service() -> GlobalMenuService:
    global _global_menu_svc_instance
    if _global_menu_svc_instance is None:
        _global_menu_svc_instance = GlobalMenuService()
    return _global_menu_svc_instance
