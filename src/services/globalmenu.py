"""Global Menu Service - extracts and manages application menus."""

import json
import re
import threading
from typing import List, Optional, Dict, Union

from fabric.core.service import Property, Service, Signal
from fabric.utils import (
    Gio,
    GLib,
    exec_shell_command,
    idle_add,
    logger,
    os,
)


from utils.dbusmenu import DBusMenuClient, DBusMenuItem, _get_bus
from utils.gtkmenu import ActionMenuClient, GtkMenuClient

_MAX_CACHE_SIZE = 5
_EMPTY_CACHE_TTL = 30.0  # re-check apps with empty menus after 30s
_DBUS_TIMEOUT_INTROSPECT = 500  # ms for introspection calls
_DBUS_TIMEOUT_PID = 200  # ms for PID lookups
_DBUS_TIMEOUT_FAST = 100  # ms for expected-fast calls

_DE_NAMESPACES = [
    "xfce",
    "mate",
    "kde",
    "gnome",
    "enlightenment",
    "pantheon",
    "elementary",
    "budgie",
    "deepin",
]


def _dbus_introspect(bus, service: str, path: str, timeout: int) -> str:
    try:
        res = bus.call_sync(
            service,
            path,
            "org.freedesktop.DBus.Introspectable",
            "Introspect",
            None,
            GLib.VariantType("(s)"),
            Gio.DBusCallFlags.NONE,
            timeout,
            None,
        )
        return res.get_child_value(0).get_string() if res else ""
    except Exception:
        return ""


def _dbus_get_pid(bus, service: str, timeout: int) -> int:
    try:
        res = bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "GetConnectionUnixProcessID",
            GLib.Variant("(s)", (service,)),
            GLib.VariantType("(u)"),
            Gio.DBusCallFlags.NONE,
            timeout,
            None,
        )
        return res.get_child_value(0).get_uint32() if res else 0
    except Exception:
        return 0


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


_EMPTY_SENTINEL: List[
    DBusMenuItem
] = []  # distinct sentinel for "discovery returned empty"


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
        self._current_pid: int = 0

        # Cached dbus menu clients mapping: wm_class -> Client
        self._client_cache: Dict[str, Union[GtkMenuClient, DBusMenuClient]] = {}
        # Cached layout for fast repaints
        self._menu_cache: Dict[str, List[DBusMenuItem]] = {}

        # Registrar mapping: sender -> (service_name, object_path)
        self._registered_menus: dict[str, tuple[str, str]] = {}

        self._seq_lock = threading.Lock()
        self._extraction_seq = 0
        self._extracting_in_flight: set[str] = set()

        self._lock = threading.Lock()
        self._registry_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self._setup_registrar()
        threading.Thread(target=self._setup_environment, daemon=True).start()

        logger.info(
            "[GlobalMenuService] Initialized native Python DBusMenu parser successfully"
        )

    def _setup_registrar(self):
        """Host the AppMenu Registrar on DBus to allow GTK/KDE apps to register menus."""
        try:
            self._bus = _get_bus()  # Shared connection — no extra allocation
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

    def _setup_environment(self):
        """Automatically setup environment variables and system overrides for global menus."""
        try:
            # 1. Inject GTK Modules for standard GTK3 apps
            # NOTE: We do NOT set os.environ here — that would affect Modus's own GTK windows,
            # causing gdk_wayland_window_set_dbus_properties_libgtk_only assertion failures.
            # The hyprctl/dbus-update-activation-environment calls set it for future apps instead.
            exec_shell_command("hyprctl keyword env GTK_MODULES,appmenu-gtk-module")
            exec_shell_command("hyprctl keyword env UBUNTU_MENUPROXY,1")
            exec_shell_command(
                "dbus-update-activation-environment --systemd GTK_MODULES=appmenu-gtk-module UBUNTU_MENUPROXY=1"
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
            logger.warning(
                f"[GlobalMenuService] Global menu environment setup failed: {e}"
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
                invocation.return_value(GLib.Variant("(a(uso))", ([],)))
        except Exception as e:
            logger.error(
                f"[GlobalMenuService] Error handling Registrar method {method_name}: {e}"
            )
            invocation.return_error_literal(Gio.DBusError.FAILED, "FAILED", str(e))

    def update_active_window(self, app_name: str, wm_class: str):
        """Called when the active window changes. Triggers menu extraction."""

        # Capture the PID right now at focus time — don't re-query later in the thread
        target_pid = 0
        try:
            out = exec_shell_command("hyprctl activewindow -j")
            if out:
                data = json.loads(out)
                target_pid = data.get("pid", 0)
        except Exception:
            pass

        # Snapshot current state under lock for race-free comparison
        with self._state_lock:
            same_class = wm_class == self._current_wm_class
            same_pid = target_pid != 0 and target_pid == self._current_pid

        # Re-focus of EXACT same window instance → use cached menu, not stale _current_menu
        if same_class and same_pid:
            with self._lock:
                cached = self._menu_cache.get(wm_class)
            if cached:
                with self._state_lock:
                    self._current_menu = cached
                self.menu_changed(cached)
            else:
                with self._state_lock:
                    current_menu = self._current_menu
                if current_menu is not None:
                    self.menu_changed(current_menu)
            return

        logger.info(
            f"[GlobalMenuService] Active window changed: {app_name} ({wm_class}) pid={target_pid}"
        )
        with self._state_lock:
            self._current_app = app_name
            self._current_wm_class = wm_class
            self._current_pid = target_pid

        with self._seq_lock:
            self._extraction_seq += 1
            seq = self._extraction_seq

        self.active_app_changed(app_name, wm_class)

        # Check cache — snapshot under lock, serve non-empty results
        with self._lock:
            cached_menu = self._menu_cache.get(wm_class)
            has_good_cache = wm_class in self._client_cache and cached_menu is not None

        if has_good_cache:
            with self._state_lock:
                self._current_menu = cached_menu
                self._current_app = app_name
                self._current_wm_class = wm_class
                self._current_pid = target_pid
            logger.info(f"[GlobalMenuService] Cache hit for '{wm_class}'")
            self.menu_changed(cached_menu)
            return

        # Clear menu IMMEDIATELY for the new app (before in_flight check below).
        # This ensures the old app's menu doesn't persist if an extraction is
        # already running for this wm_class (e.g. user focused Kitty, then Zen,
        # then Kitty again before the first extraction finished).
        with self._state_lock:
            self._current_menu = None
        self.menu_changed([])

        # Dedup in-flight extractions — atomic check+add under lock
        inflight_key = f"{wm_class}:{target_pid}"
        with self._lock:
            if inflight_key in self._extracting_in_flight:
                logger.debug(
                    f"[GlobalMenuService] Extraction already in-flight for '{inflight_key}' — skipping"
                )
                return
            self._extracting_in_flight.add(inflight_key)

        # Extract menu in background thread, passing captured pid
        logger.info(
            f"[GlobalMenuService] Starting extraction for '{wm_class}' pid={target_pid}"
        )
        thread = threading.Thread(
            target=self._extract_menu,
            args=(wm_class, seq, target_pid, inflight_key),
            daemon=True,
        )
        thread.start()

    def _discover_dbus_client(
        self, wm_class: str, target_pid: int = 0
    ) -> Optional[DBusMenuClient]:
        """Fast and deterministic DBusMenu discovery (Wayland-safe)."""
        try:
            if target_pid <= 0:
                out = exec_shell_command("hyprctl activewindow -j")
                if not out:
                    logger.warning("[GlobalMenuService] hyprctl returned no output")
                    return None
                target_pid = json.loads(out).get("pid", 0)

            if target_pid <= 0:
                return None

            bus = _get_bus()

            # 1. FAST PATH: Registrar cache
            with self._registry_lock:
                registered = dict(self._registered_menus)

            for sender, (service, path) in registered.items():
                try:
                    pid = _dbus_get_pid(bus, service, _DBUS_TIMEOUT_FAST)
                    if pid == target_pid or self._is_same_app(pid, target_pid):
                        logger.info(
                            f"[GlobalMenuService] Registrar match: {service} {path}"
                        )
                        return DBusMenuClient(service, path)
                except Exception as e:
                    if "NameHasNoOwner" in str(e):
                        with self._registry_lock:
                            self._registered_menus.pop(sender, None)

            # 2. FALLBACK: Scan DBus services matching the target PID
            static_paths = [
                "/com/canonical/menu/0",
                "/com/canonical/AppMenu/Registrar/0",
                "/com/canonical/Unity/Panel/Service",
                "/appmenu",
                "/org/gtk/Application/menus/appmenu",
                "/org/gtk/Application/menus/menubar",
                "/org/gtk/Application/menus/appmenu/0",
                "/org/gtk/Application/menus/menubar/0",
                "/org/appmenu/gtk/window/menus/menubar",
                "/org/appmenu/gtk/window/menus/appmenu",
                "/org/appmenu/gtk/window/menus/menubar/0",
                "/org/appmenu/gtk/window/menus/appmenu/0",
                "/MenuBar",
                "/KDEAppMenu",
                "/org/xfce/Thunar/menus/menubar/0",
            ]

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
            services = [
                n
                for n in names
                if n != "org.freedesktop.DBus"
                and not n.startswith("org.freedesktop.DBus")
            ]

            for svc in services:
                try:
                    pid = _dbus_get_pid(bus, svc, _DBUS_TIMEOUT_PID)
                    if not (pid == target_pid or self._is_same_app(pid, target_pid)):
                        continue

                    with self._registry_lock:
                        if reg_entry := self._registered_menus.get(svc):
                            logger.info(
                                f"[GlobalMenuService] Found Registrar path {reg_entry[1]} for {svc}"
                            )
                            return DBusMenuClient(reg_entry[0], reg_entry[1])

                    _safe_cls = (
                        re.sub(r"[^A-Za-z0-9_]", "", wm_class) if wm_class else ""
                    )
                    _safe_cap = _safe_cls.capitalize() if _safe_cls else ""

                    dynamic_bases = [
                        "/MenuBar",
                        "/com/canonical/menu",
                        "/org/appmenu/gtk/window/menus/menubar",
                        "/org/appmenu/gtk/window/menus/appmenu",
                        "/org/appmenu/gtk/window",
                        "/org/gtk/Application/menus",
                        "/org/gtk/Application",
                        "/org/libreoffice",
                        "/org/xfce",
                        "/org/mate",
                        "/org/kde",
                        "/org/gnome",
                        "/org/enlightenment",
                        "/org/pantheon",
                        "/org/elementary",
                        "/com/deepin",
                        "/com/solus-project",
                        "/com/canonical",
                    ]

                    if _safe_cls:
                        cls_lower = _safe_cls.lower()
                        for ns in _DE_NAMESPACES + [cls_lower]:
                            for app_part in (_safe_cap, _safe_cls):
                                for suffix in (
                                    "menus/menubar",
                                    "menus/appmenu",
                                    "menus",
                                ):
                                    p = f"/org/{ns}/{app_part}/{suffix}"
                                    if GLib.Variant.is_object_path(p):
                                        dynamic_bases.append(p)

                    fallback_paths = list(static_paths)
                    seen_fallback = set(fallback_paths)

                    # Helper for safe path addition
                    def _add_paths(parent_path, xml_str):
                        for child in re.findall(r'<node name="([^"]+)"', xml_str):
                            child_path = f"{parent_path}/{child}"
                            if (
                                GLib.Variant.is_object_path(child_path)
                                and child_path not in seen_fallback
                            ):
                                seen_fallback.add(child_path)
                                fallback_paths.insert(0, child_path)
                                yield child_path

                    # Multi-level child introspection
                    for base in dynamic_bases:
                        if not GLib.Variant.is_object_path(base):
                            continue
                        xml_text = _dbus_introspect(
                            bus, svc, base, _DBUS_TIMEOUT_INTROSPECT
                        )
                        for child_path in _add_paths(base, xml_text):
                            cxml_text = _dbus_introspect(
                                bus, svc, child_path, _DBUS_TIMEOUT_FAST
                            )
                            list(_add_paths(child_path, cxml_text))

                    gtk_candidates = []
                    for path in fallback_paths:
                        xml = _dbus_introspect(bus, svc, path, _DBUS_TIMEOUT_INTROSPECT)
                        if "com.canonical.dbusmenu" in xml:
                            logger.info(
                                f"[GlobalMenuService] DBusMenu found: {svc} {path}"
                            )
                            with self._registry_lock:
                                self._registered_menus[svc] = (svc, path)
                            return DBusMenuClient(svc, path)
                        elif "org.gtk.Menus" in xml:
                            gtk_candidates.append((svc, path))

                    for dfs_path in self._dfs_find_interface(svc, "org.gtk.Menus"):
                        if dfs_path not in {p for _, p in gtk_candidates}:
                            gtk_candidates.append((svc, dfs_path))

                    for gsvc, gpath in gtk_candidates:
                        try:
                            test_client = GtkMenuClient(gsvc, gpath)
                            test_items = test_client.get_layout()
                            if not test_items:
                                import time

                                for _ in range(4):
                                    time.sleep(0.05)
                                    if test_items := test_client.get_layout():
                                        break

                            if test_items:
                                logger.info(
                                    f"[GlobalMenuService] GTK menu found: {gsvc} {gpath} ({len(test_items)} items)"
                                )
                                with self._registry_lock:
                                    self._registered_menus[gsvc] = (gsvc, gpath)
                                return test_client
                        except Exception:
                            pass

                    # Final fallback: flat menu from org.gtk.Actions
                    action_candidates = ["/"]
                    name_path = (
                        "/" + svc.replace(".", "/") if not svc.startswith(":") else ""
                    )
                    if name_path and GLib.Variant.is_object_path(name_path):
                        action_candidates.append(name_path)
                    action_candidates.append("/org/gtk/Application")

                    if _safe_cls:
                        cls_lower = _safe_cls.lower()
                        action_candidates.extend(
                            [f"/org/{cls_lower}/{_safe_cap}", f"/org/{cls_lower}"]
                        )
                        for ns in _DE_NAMESPACES + [cls_lower]:
                            for app_part in (_safe_cap, _safe_cls):
                                p = f"/org/{ns}/{app_part}"
                                if GLib.Variant.is_object_path(p):
                                    action_candidates.append(p)

                    action_candidates.extend(
                        self._dfs_find_interface(svc, "org.gtk.Actions")
                    )

                    for act_base in action_candidates:
                        xml = _dbus_introspect(bus, svc, act_base, _DBUS_TIMEOUT_FAST)
                        if 'interface name="org.gtk.Actions"' in xml:
                            test_client = ActionMenuClient(svc, act_base)
                            if test_items := test_client.get_layout():
                                logger.info(
                                    f"[GlobalMenuService] Action menu fallback: {svc} {act_base} ({len(test_items)} items)"
                                )
                                return test_client

                    logger.info(
                        f"[GlobalMenuService] No menu found for {svc} wm={wm_class}"
                    )
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[GlobalMenuService] Discovery failed: {e}")

        return None

    def _dfs_find_interface(
        self,
        service: str,
        interface: str,
        path: str = "/",
        _depth: int = 0,
        _visited: Optional[set] = None,
        _node_count: Optional[list[int]] = None,
    ) -> list[str]:
        """Bounded DFS returning ALL paths containing a target interface in a service's object tree."""
        if _node_count is None:
            _node_count = [0]
        if (
            _depth > 6
            or _node_count[0] > 100
            or (_visited is not None and path in _visited)
        ):
            return []
        if _visited is None:
            _visited = set()
        _visited.add(path)
        _node_count[0] += 1
        results: list[str] = []
        try:
            xml = _dbus_introspect(_get_bus(), service, path, _DBUS_TIMEOUT_INTROSPECT)
            if not xml:
                return results

            if f'interface name="{interface}"' in xml:
                results.append(path)

            for child in re.findall(r'<node name="([^"]+)"', xml):
                child_path = (
                    path.rstrip("/") + "/" + child if path != "/" else "/" + child
                )
                if not GLib.Variant.is_object_path(child_path):
                    continue
                results.extend(
                    self._dfs_find_interface(
                        service,
                        interface,
                        child_path,
                        _depth + 1,
                        _visited,
                        _node_count,
                    )
                )
        except Exception:
            pass
        return results

    def _is_same_app(self, pid1: int, pid2: int) -> bool:
        if pid1 == pid2:
            return True
        try:
            # Compare resolved executable paths
            exe1 = os.path.realpath(f"/proc/{pid1}/exe")
            exe2 = os.path.realpath(f"/proc/{pid2}/exe")
            if exe1 and exe2 and exe1 == exe2:
                return True

            # Compare process names (comm) — handles cases where exe differs
            # but the app is the same (e.g., launcher wrappers)
            try:
                with open(f"/proc/{pid1}/comm") as f:
                    comm1 = f.read().strip()
                with open(f"/proc/{pid2}/comm") as f:
                    comm2 = f.read().strip()
                if comm1 and comm2 and comm1 == comm2:
                    return True
            except OSError:
                pass

            # Also allow: one pid is the direct parent of the other
            # (Qt apps register DBus under a child thread pid)
            def _ppid(p: int) -> int:
                try:
                    with open(f"/proc/{p}/stat") as f:
                        parts = f.read().split()
                        return int(parts[3]) if len(parts) > 4 else 0
                except Exception:
                    return 0

            if _ppid(pid1) == pid2 or _ppid(pid2) == pid1:
                return True
        except (OSError, PermissionError, FileNotFoundError):
            pass
        return False

    def _evict_cache_if_needed(self, key: str):
        """Evict oldest cache entries when over the size limit. Must be called under _lock."""
        if not hasattr(self, "_cache_order"):
            self._cache_order: list[str] = []
        if key not in self._cache_order:
            self._cache_order.append(key)

        while len(self._cache_order) > _MAX_CACHE_SIZE:
            oldest = self._cache_order.pop(0)
            self._client_cache.pop(oldest, None)
            self._menu_cache.pop(oldest, None)
            logger.debug(f"[GlobalMenuService] Evicted cache for '{oldest}'")

    def _extract_menu(
        self, wm_class: str, seq: int, target_pid: int = 0, inflight_key: str = ""
    ):
        """Extract menu for a given WM class in a background thread."""
        try:
            # Bail early if a newer extraction has already superseded this one
            with self._seq_lock:
                if seq != self._extraction_seq:
                    return

            client = self._discover_dbus_client(wm_class, target_pid)
            items = []

            if client:
                items = client.get_layout()

            if items:
                with self._lock:
                    self._client_cache[wm_class] = client
                    self._menu_cache[wm_class] = items
                    self._evict_cache_if_needed(wm_class)
                    logger.info(
                        f"[GlobalMenuService] Found menu for '{wm_class}': {len(items)} items"
                    )
            else:
                logger.info(f"[GlobalMenuService] No DBus menu found for '{wm_class}'")

            with self._seq_lock:
                current_seq = self._extraction_seq

            if seq != current_seq:
                return

            # Capture seq for race-safe emission in idle callback
            emit_seq = current_seq
            idle_add(self._emit_menu_changed, items, emit_seq)

        except Exception as e:
            logger.error(
                f"[GlobalMenuService] Error extracting menu for '{wm_class}': {e}"
            )
        finally:
            if inflight_key:
                with self._lock:
                    self._extracting_in_flight.discard(inflight_key)

    def _emit_menu_changed(self, items: List[DBusMenuItem], seq: int = 0):
        """Emit menu_changed signal on the main thread. Checks seq to avoid stale emissions."""
        if seq:
            with self._seq_lock:
                if seq != self._extraction_seq:
                    return False
        with self._state_lock:
            self._current_menu = items
        self.menu_changed(items)
        return False  # Remove from idle queue

    def click_item(self, item_id: int) -> bool:
        """Click a menu item by ID."""
        with self._state_lock:
            wm_class = self._current_wm_class
        with self._lock:
            client = self._client_cache.get(wm_class)
        if client:
            client.click_item(item_id)
            return True
        return False

    def about_to_show(self, item_id: int) -> bool:
        """Triggers the AboutToShow event on a DBusMenu item."""
        with self._state_lock:
            wm_class = self._current_wm_class
        with self._lock:
            client = self._client_cache.get(wm_class)
        if client:
            return client.about_to_show(item_id)
        return False

    def refresh_menu_sync(self) -> List[DBusMenuItem]:
        """Synchronously refetches the menu for the current app."""
        with self._state_lock:
            wm_class = self._current_wm_class
        with self._lock:
            client = self._client_cache.get(wm_class)
        if client:
            items = client.get_layout()
            with self._lock:
                self._menu_cache[wm_class] = items
            return items
        return []


_global_menu_svc_instance = None


def get_global_menu_service() -> GlobalMenuService:
    global _global_menu_svc_instance
    if _global_menu_svc_instance is None:
        _global_menu_svc_instance = GlobalMenuService()
    return _global_menu_svc_instance
