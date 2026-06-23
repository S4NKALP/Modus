"""Global Menu Service - extracts and manages application menus."""

import json
import re
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

from utils.dbusmenu import DBusMenuClient, DBusMenuItem, _get_bus
from utils.gtkmenu import GtkMenuClient

_MAX_CACHE_SIZE = 5

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
        self._current_pid: int = 0

        # Bounded LRU caches — deliberately small to save memory
        self._client_cache: dict[str, Optional[DBusMenuClient]] = {}
        self._menu_cache: dict[str, Optional[List[DBusMenuItem]]] = {}
        self._cache_order: list[str] = []

        # Registrar mapping: sender -> (service_name, object_path)
        self._registered_menus: dict[str, tuple[str, str]] = {}

        self._seq_lock = threading.Lock()
        self._extraction_seq = 0

        self._lock = threading.Lock()
        self._registry_lock = threading.Lock()

        self._setup_registrar()
        self._setup_environment()

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

        same_class = wm_class == self._current_wm_class
        same_pid = target_pid != 0 and target_pid == self._current_pid

        # Re-focus of EXACT same window instance → just re-emit what we have
        if same_class and same_pid:
            if self._current_menu is not None:
                self.menu_changed(self._current_menu)
            return

        logger.info(
            f"[GlobalMenuService] Active window changed: {app_name} ({wm_class}) pid={target_pid}"
        )
        self._current_app = app_name
        self._current_wm_class = wm_class
        self._current_pid = target_pid

        with self._seq_lock:
            self._extraction_seq += 1
            seq = self._extraction_seq

        self.active_app_changed(app_name, wm_class)

        # Check cache — but ONLY serve cached result if it's non-empty.
        # An empty cache entry means discovery failed last time; try again.
        with self._lock:
            has_good_cache = (
                wm_class in self._client_cache
                and wm_class in self._menu_cache
                and self._menu_cache.get(wm_class)  # non-empty
            )
            cached_menu = self._menu_cache.get(wm_class) if has_good_cache else None

        if has_good_cache and cached_menu:
            self._current_menu = cached_menu
            logger.info(f"[GlobalMenuService] Cache hit for '{wm_class}'")
            self.menu_changed(cached_menu)
            return

        # Clear menu immediately for new app while extraction runs
        self._current_menu = None
        self.menu_changed([])

        # Extract menu in background thread, passing captured pid
        logger.info(
            f"[GlobalMenuService] Starting extraction for '{wm_class}' pid={target_pid}"
        )
        thread = threading.Thread(
            target=self._extract_menu,
            args=(wm_class, seq, target_pid),
            daemon=True,
        )
        thread.start()

    def _discover_dbus_client(
        self, wm_class: str, target_pid: int = 0
    ) -> Optional[DBusMenuClient]:
        """Fast and deterministic DBusMenu discovery (Wayland-safe)."""
        try:
            # Use the pid captured at focus time; fall back to hyprctl only if not provided
            if target_pid <= 0:
                out = exec_shell_command("hyprctl activewindow -j")
                if not out:
                    logger.warning("[GlobalMenuService] hyprctl returned no output")
                    return None
                data = json.loads(out)
                target_pid = data.get("pid", 0)

            if target_pid <= 0:
                return None

            bus = _get_bus()

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
            # 2. FALLBACK: Scan DBus services matching the target PID
            # =========================

            # Static well-known paths (all known DEs and toolkits)
            static_paths: list[str] = [
                # Unity/Canonical
                "/com/canonical/menu/0",
                "/com/canonical/AppMenu/Registrar/0",
                "/com/canonical/Unity/Panel/Service",
                "/appmenu",
                # GTK generic
                "/org/gtk/Application/menus/appmenu",
                "/org/gtk/Application/menus/menubar",
                "/org/gtk/Application/menus/appmenu/0",
                "/org/gtk/Application/menus/menubar/0",
                # appmenu-gtk-module
                "/org/appmenu/gtk/window/menus/menubar",
                "/org/appmenu/gtk/window/menus/appmenu",
                "/org/appmenu/gtk/window/menus/menubar/0",
                "/org/appmenu/gtk/window/menus/appmenu/0",
                # KDE/Qt
                "/MenuBar",
                "/KDEAppMenu",
                # XFCE
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

            # Include BOTH well-known names AND unique names (:1.xxx) — many apps
            # only have a unique name and would be invisible with the old filter.
            # Only skip the DBus daemon itself.
            services = [
                n
                for n in names
                if n != "org.freedesktop.DBus"
                and not n.startswith("org.freedesktop.DBus")
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

                    # Check if this app explicitly registered its menu via Registrar
                    with self._registry_lock:
                        reg_entry = self._registered_menus.get(svc)
                    if reg_entry:
                        reg_svc, reg_path = reg_entry
                        logger.info(
                            f"[GlobalMenuService] Found Registrar path {reg_path} for {svc}"
                        )
                        return DBusMenuClient(reg_svc, reg_path)

                    # Sanitize wm_class for use in DBus paths
                    _safe_cls = (
                        re.sub(r"[^A-Za-z0-9_]", "", wm_class) if wm_class else ""
                    )
                    _safe_cap = _safe_cls.capitalize() if _safe_cls else ""

                    # Dynamic bases — introspected for child nodes to expand
                    # Ordered by likelihood to minimize DBus calls
                    dynamic_bases: list[str] = [
                        "/MenuBar",
                        "/com/canonical/menu",
                        "/org/appmenu/gtk/window/menus/menubar",
                        "/org/appmenu/gtk/window/menus/appmenu",
                        "/org/appmenu/gtk/window",
                        "/org/gtk/Application/menus",
                        "/org/gtk/Application",
                        # DE namespace roots — DFS handles deeper traversal
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

                    # wm_class-derived paths for each known DE namespace
                    if _safe_cls:
                        cls_lower = _safe_cls.lower()
                        for ns, app_part in [
                            ("xfce", _safe_cap),
                            ("xfce", _safe_cls),
                            ("mate", _safe_cap),
                            ("mate", _safe_cls),
                            ("kde", _safe_cap),
                            ("kde", _safe_cls),
                            ("gnome", _safe_cap),
                            ("gnome", _safe_cls),
                            ("enlightenment", _safe_cap),
                            ("enlightenment", _safe_cls),
                            ("pantheon", _safe_cap),
                            ("pantheon", _safe_cls),
                            ("elementary", _safe_cap),
                            ("elementary", _safe_cls),
                            ("budgie", _safe_cap),
                            ("budgie", _safe_cls),
                            ("deepin", _safe_cap),
                            ("deepin", _safe_cls),
                            (cls_lower, _safe_cap),  # generic fallback
                        ]:
                            for suffix in ("menus/menubar", "menus/appmenu", "menus"):
                                p = f"/org/{ns}/{app_part}/{suffix}"
                                if GLib.Variant.is_object_path(p):
                                    dynamic_bases.append(p)

                    fallback_paths = list(static_paths)
                    seen_fallback: set[str] = set(fallback_paths)

                    # Multi-level child introspection from dynamic bases
                    for base in dynamic_bases:
                        if not GLib.Variant.is_object_path(base):
                            continue
                        try:
                            xml_res = _get_bus().call_sync(
                                svc,
                                base,
                                "org.freedesktop.DBus.Introspectable",
                                "Introspect",
                                None,
                                GLib.VariantType("(s)"),
                                Gio.DBusCallFlags.NONE,
                                300,
                                None,
                            )
                            if not xml_res:
                                continue
                            xml_text = xml_res.get_child_value(0).get_string()
                            for child in re.findall(r'<node name="([^"]+)"', xml_text):
                                child_path = f"{base}/{child}"
                                if (
                                    not GLib.Variant.is_object_path(child_path)
                                    or child_path in seen_fallback
                                ):
                                    continue
                                seen_fallback.add(child_path)
                                fallback_paths.insert(0, child_path)
                                # Recurse one more level for deeply nested structures
                                try:
                                    cxml_res = _get_bus().call_sync(
                                        svc,
                                        child_path,
                                        "org.freedesktop.DBus.Introspectable",
                                        "Introspect",
                                        None,
                                        GLib.VariantType("(s)"),
                                        Gio.DBusCallFlags.NONE,
                                        200,
                                        None,
                                    )
                                    if cxml_res:
                                        for gchild in re.findall(
                                            r'<node name="([^"]+)"',
                                            cxml_res.get_child_value(0).get_string(),
                                        ):
                                            gp = f"{child_path}/{gchild}"
                                            if (
                                                GLib.Variant.is_object_path(gp)
                                                and gp not in seen_fallback
                                            ):
                                                seen_fallback.add(gp)
                                                fallback_paths.insert(0, gp)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    # Collect ALL GTK menu paths via both fallback_paths and DFS
                    gtk_candidates: list[tuple[str, str]] = []
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
                                logger.debug(
                                    f"[GlobalMenuService] GTK menu at {path} (deferring for DBusMenu)"
                                )
                                gtk_candidates.append((svc, path))
                            else:
                                logger.debug(
                                    f"[GlobalMenuService] {svc} {path}: no menu (interfaces: {re.findall(r'interface name=\"([^\"]+)\"', xml)})"
                                )
                        except Exception as e:
                            logger.debug(
                                f"[GlobalMenuService] {svc} {path}: introspection error: {e}"
                            )

                    # Also search the full object tree via DFS for GTK menus
                    all_dfs_paths = self._dfs_find_gtk_menus(svc)
                    for dfs_path in all_dfs_paths:
                        if dfs_path not in {p for _, p in gtk_candidates}:
                            gtk_candidates.append((svc, dfs_path))

                    # Validate each candidate — find one with actual menu items
                    for gsvc, gpath in gtk_candidates:
                        try:
                            test_client = GtkMenuClient(gsvc, gpath)
                            test_items = test_client.get_layout()
                            if test_items:
                                logger.info(
                                    f"[GlobalMenuService] GTK menu found: {gsvc} {gpath} ({len(test_items)} items)"
                                )
                                with self._registry_lock:
                                    self._registered_menus[gsvc] = (gsvc, gpath)
                                return test_client
                            else:
                                logger.debug(
                                    f"[GlobalMenuService] GTK menu {gpath} returned 0 items — trying next"
                                )
                        except Exception as e:
                            logger.debug(
                                f"[GlobalMenuService] GTK menu {gpath} validation failed: {e}"
                            )

                    logger.info(
                        f"[GlobalMenuService] No menu found for {svc} wm={wm_class}"
                    )

                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"[GlobalMenuService] Discovery failed: {e}")

        return None

    def _dfs_find_gtk_menus(
        self,
        service: str,
        path: str = "/",
        _depth: int = 0,
        _visited: Optional[set] = None,
    ) -> list[str]:
        """Bounded DFS returning ALL org.gtk.Menus paths in a service's object tree."""
        if _depth > 6 or (_visited is not None and path in _visited):
            return []
        if _visited is None:
            _visited = set()
        _visited.add(path)
        results: list[str] = []
        try:
            xml_res = _get_bus().call_sync(
                service,
                path,
                "org.freedesktop.DBus.Introspectable",
                "Introspect",
                None,
                GLib.VariantType("(s)"),
                Gio.DBusCallFlags.NONE,
                500,
                None,
            )
            xml = xml_res.get_child_value(0).get_string()
            if 'interface name="org.gtk.Menus"' in xml:
                results.append(path)
            for child in re.findall(r'<node name="([^"]+)"', xml):
                child_path = (
                    path.rstrip("/") + "/" + child if path != "/" else "/" + child
                )
                if not GLib.Variant.is_object_path(child_path):
                    continue
                results.extend(
                    self._dfs_find_gtk_menus(service, child_path, _depth + 1, _visited)
                )
        except Exception:
            pass
        return results

    def _is_same_app(self, pid1: int, pid2: int) -> bool:
        if pid1 == pid2:
            return True
        try:
            exe1 = os.path.realpath(f"/proc/{pid1}/exe")
            exe2 = os.path.realpath(f"/proc/{pid2}/exe")
            if exe1 and exe2 and exe1 == exe2:
                return True

            # Also allow: one pid is the direct parent of the other
            # (Qt apps register DBus under a child thread pid)
            def _ppid(p: int) -> int:
                try:
                    with open(f"/proc/{p}/stat") as f:
                        return int(f.read().split()[3])
                except Exception:
                    return 0

            if _ppid(pid1) == pid2 or _ppid(pid2) == pid1:
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

    def _extract_menu(self, wm_class: str, seq: int, target_pid: int = 0):
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

            with self._lock:
                # Only cache successful (non-empty) results.
                # Empty results are NOT cached so the next focus triggers a fresh discovery.
                if items:
                    self._client_cache[wm_class] = client
                    self._menu_cache[wm_class] = items
                    self._evict_cache_if_needed(wm_class)
                    logger.info(
                        f"[GlobalMenuService] Found menu for '{wm_class}': {len(items)} items"
                    )
                else:
                    # Clear any stale cached empty entry so next focus retries
                    self._client_cache.pop(wm_class, None)
                    self._menu_cache.pop(wm_class, None)
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
