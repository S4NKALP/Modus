"""Global Menu Service - extracts and manages application menus.

Uses the pure Python DBusMenu extractor via Gio.DBus.
"""

import json
import threading
from typing import List, Optional

from fabric.core.service import Property, Service, Signal
from fabric.utils import (
    Gio,
    GLib,
    exec_shell_command,
    idle_add,
    logger,
    os,
)

from utils.dbusmenu import DBusMenuClient, DBusMenuItem
from utils.gtkmenu import GtkMenuClient

_MAX_CACHE_SIZE = 32

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
        # LRU-style insertion-order tracking for cache eviction
        self._cache_order: list[str] = []

        # Cache DBus service -> PID to make discovery instant
        self._pid_cache: dict[str, int] = {}

        # Registrar mapping: sender -> (service_name, object_path)
        self._registered_menus: dict[str, tuple[str, str]] = {}

        self._seq_lock = threading.Lock()
        self._extraction_seq = 0

        self._lock = threading.Lock()
        self._registry_lock = threading.Lock()

        self._setup_registrar()
        self._setup_environment()

        # Prewarm the PID cache in the background
        threading.Thread(target=self._prewarm_dbus_cache, daemon=True).start()

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

    def _prewarm_dbus_cache(self):
        """Pre-fetches PIDs for all current DBus services so discovery is instant."""
        try:
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

            def fetch_pid(svc):
                with self._registry_lock:
                    cached = svc in self._pid_cache
                if not cached:
                    try:
                        pid_res = bus.call_sync(
                            "org.freedesktop.DBus",
                            "/org/freedesktop/DBus",
                            "org.freedesktop.DBus",
                            "GetConnectionUnixProcessID",
                            GLib.Variant("(s)", (svc,)),
                            GLib.VariantType("(u)"),
                            Gio.DBusCallFlags.NONE,
                            500,
                            None,
                        )
                        with self._registry_lock:
                            self._pid_cache[svc] = pid_res.get_child_value(
                                0
                            ).get_uint32()
                    except Exception:
                        with self._registry_lock:
                            self._pid_cache[svc] = 0

            for svc in names:
                with self._registry_lock:
                    if svc in self._pid_cache:
                        continue
                threading.Thread(target=fetch_pid, args=(svc,), daemon=True).start()

            logger.info(
                f"[GlobalMenuService] Pre-warmed DBus PID cache with {len(self._pid_cache)} entries"
            )
        except Exception as e:
            logger.debug(f"[GlobalMenuService] Pre-warm failed: {e}")

    def _setup_environment(self):
        """Automatically setup environment variables and system overrides for global menus."""
        try:
            # 1. Inject GTK Modules for standard GTK3 apps
            os.environ["GTK_MODULES"] = "appmenu-gtk-module"
            exec_shell_command("hyprctl keyword env GTK_MODULES,appmenu-gtk-module")
            exec_shell_command(
                "dbus-update-activation-environment --systemd GTK_MODULES=appmenu-gtk-module"
            )

            # 2. Automatically grant Flatpak apps permission to talk to the DBus Registrar
            exec_shell_command(
                "flatpak override --user --talk-name=com.canonical.AppMenu.Registrar"
            )

            # 3. Force XFCE / GTK3 apps to show menubars globally by writing to settings.ini
            settings_path = os.path.expanduser("~/.config/gtk-3.0/settings.ini")
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    content = f.read()
                if "gtk-shell-shows-menubar" not in content:
                    with open(settings_path, "a") as f:
                        f.write("\ngtk-shell-shows-menubar=1\n")

            logger.info(
                "[GlobalMenuService] Injected GTK environment and Flatpak overrides automatically"
            )
        except Exception as e:
            logger.debug(
                f"[GlobalMenuService] Failed to set up global menu environment overrides: {e}"
            )

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
                with self._registry_lock:
                    # the real bus name instead of echoing back the caller's address.
                    self._registered_menus[sender] = (sender, menu_path)
                invocation.return_value(None)

            elif method_name == "UnregisterWindow":
                with self._registry_lock:
                    self._registered_menus.pop(sender, None)
                invocation.return_value(None)

            elif method_name == "GetMenuForWindow":
                window_id = parameters.unpack()[0]
                with self._registry_lock:
                    entry = self._registered_menus.get(sender)
                if entry:
                    svc_name, svc_path = entry
                    invocation.return_value(GLib.Variant("(so)", (svc_name, svc_path)))
                else:
                    # Fallback — nothing registered for this sender
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

        with self._seq_lock:
            self._extraction_seq += 1
            seq = self._extraction_seq

        self.active_app_changed(app_name, wm_class)

        # Check cache first
        with self._lock:
            has_client = wm_class in self._client_cache
            has_menu = wm_class in self._menu_cache
            cached_menu = self._menu_cache.get(wm_class) if has_menu else None

        if has_client and has_menu:
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

    def _discover_dbus_client(self, wm_class: str) -> Optional[DBusMenuClient]:
        """Fast and deterministic DBusMenu discovery (Wayland-safe)."""
        try:
            out = exec_shell_command("hyprctl activewindow -j")
            if not out:
                logger.warning("[GlobalMenuService] hyprctl returned no output")
                return None

            data = json.loads(out)
            target_pid = data.get("pid", 0)

            if target_pid <= 0:
                return None

            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

            # =========================
            # 1. FAST PATH: Registrar cache
            # =========================
            with self._registry_lock:
                registered = dict(self._registered_menus)

            for sender, (service, path) in registered.items():
                try:
                    pid_res = bus.call_sync(
                        "org.freedesktop.DBus",
                        "/org/freedesktop/DBus",
                        "org.freedesktop.DBus",
                        "GetConnectionUnixProcessID",
                        GLib.Variant("(s)", (service,)),
                        GLib.VariantType("(u)"),
                        Gio.DBusCallFlags.NONE,
                        100,
                        None,
                    )

                    pid = pid_res.get_child_value(0).get_uint32()

                    if pid == target_pid or self._is_same_app(pid, target_pid):
                        logger.info(
                            f"[GlobalMenuService] Registrar match: {service} {path}"
                        )
                        return DBusMenuClient(service, path)

                except Exception:
                    # stale entry cleanup
                    with self._registry_lock:
                        self._registered_menus.pop(sender, None)

            # =========================
            # 2. SIMPLE FALLBACK PATHS ONLY
            # =========================
            fallback_paths = (
                "/com/canonical/menu/0",
                "/MenuBar",
                "/appmenu",
                "/com/canonical/AppMenu/Registrar/0",
                "/org/gtk/Application/menus/appmenu",
                "/org/gtk/Application/menus/menubar",
                "/org/xfce/Thunar/menus/menubar/0",
            )

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

            # filter only real app services (cheap filter)
            services = [
                n
                for n in names
                if not n.startswith("org.freedesktop.") and not n.startswith(":")
            ]

            for svc in services:
                try:
                    pid_res = bus.call_sync(
                        "org.freedesktop.DBus",
                        "/org/freedesktop/DBus",
                        "org.freedesktop.DBus",
                        "GetConnectionUnixProcessID",
                        GLib.Variant("(s)", (svc,)),
                        GLib.VariantType("(u)"),
                        Gio.DBusCallFlags.NONE,
                        200,
                        None,
                    )

                    pid = pid_res.get_child_value(0).get_uint32()

                    if not (pid == target_pid or self._is_same_app(pid, target_pid)):
                        continue

                    # check only known paths (NO brute force)
                    for path in fallback_paths:
                        try:
                            introspect = bus.call_sync(
                                svc,
                                path,
                                "org.freedesktop.DBus.Introspectable",
                                "Introspect",
                                None,
                                GLib.VariantType("(s)"),
                                Gio.DBusCallFlags.NONE,
                                300,
                                None,
                            )

                            xml = introspect.get_child_value(0).get_string()

                            if "com.canonical.dbusmenu" in xml:
                                logger.info(
                                    f"[GlobalMenuService] DBusMenu found: {svc} {path}"
                                )
                                with self._registry_lock:
                                    self._registered_menus[svc] = (svc, path)
                                return DBusMenuClient(svc, path)
                            elif "org.gtk.Menus" in xml:
                                logger.info(
                                    f"[GlobalMenuService] GtkMenu found: {svc} {path}"
                                )
                                with self._registry_lock:
                                    self._registered_menus[svc] = (svc, path)
                                return GtkMenuClient(svc, path)

                        except Exception:
                            continue

                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"[GlobalMenuService] Discovery failed: {e}")

        return None

    def _is_same_app(self, pid1: int, pid2: int) -> bool:
        if pid1 == pid2:
            return True
        try:
            # multiple instances of the same executable (e.g. two terminals).
            exe1 = os.path.realpath(f"/proc/{pid1}/exe")
            exe2 = os.path.realpath(f"/proc/{pid2}/exe")
            if not (exe1 and exe2 and exe1 == exe2):
                return False

            # Read start time from /proc/<pid>/stat field 22 (0-indexed: field index 21)
            def _start_time(pid: int) -> Optional[str]:
                try:
                    with open(f"/proc/{pid}/stat") as f:
                        fields = f.read().split()
                    return fields[21] if len(fields) > 21 else None
                except OSError:
                    return None

            st1 = _start_time(pid1)
            st2 = _start_time(pid2)

            # If we can read start times, they must also match
            if st1 is not None and st2 is not None:
                return st1 == st2

            # Fall back to exe-only match if /proc/stat is unreadable
            return True
        except OSError:
            pass
        return False

    def _evict_cache_if_needed(self, key: str):
        """Evict oldest cache entries when over the size limit. Must be called under _lock."""
        if key not in self._cache_order:
            self._cache_order.append(key)

        while len(self._cache_order) > _MAX_CACHE_SIZE:
            oldest = self._cache_order.pop(0)
            self._client_cache.pop(oldest, None)
            self._menu_cache.pop(oldest, None)
            logger.debug(f"[GlobalMenuService] Evicted cache for '{oldest}'")

    def _extract_menu(self, wm_class: str, seq: int):
        """Extract menu for a given WM class in a background thread."""
        try:
            client = self._discover_dbus_client(wm_class)
            items = []

            if client:
                items = client.get_layout()

            with self._lock:
                self._client_cache[wm_class] = client
                self._menu_cache[wm_class] = items
                self._evict_cache_if_needed(wm_class)

                if items:
                    logger.info(
                        f"[GlobalMenuService] Found menu for '{wm_class}': {len(items)} items"
                    )
                else:
                    logger.info(
                        f"[GlobalMenuService] No DBus menu found for '{wm_class}'"
                    )

            with self._seq_lock:
                current_seq = self._extraction_seq

            if seq != current_seq:
                return

            # Update UI on main thread via GLib idle
            idle_add(self._emit_menu_changed, items)

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
        with self._lock:
            client = self._client_cache.get(self._current_wm_class)
        if client:
            client.click_item(item_id)
            return True
        return False

    def about_to_show(self, item_id: int) -> bool:
        """Triggers the AboutToShow event on a DBusMenu item."""
        with self._lock:
            client = self._client_cache.get(self._current_wm_class)
        if client:
            return client.about_to_show(item_id)
        return False

    def refresh_menu_sync(self) -> List[DBusMenuItem]:
        """Synchronously refetches the menu for the current app."""
        with self._lock:
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
