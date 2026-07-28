"""Global Menu Service — event-driven, persistent importer architecture."""

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional, Union

from fabric.core.service import Property, Service, Signal
from fabric.utils import (
    Gio,
    GLib,
    exec_shell_command,
    idle_add,
    logger,
    os,
)

from window.globalmenu.dbusmenu import DBusMenuClient, DBusMenuItem, _get_bus
from window.globalmenu.environment import setup_global_menu_environment
from window.globalmenu.gtkmenu import ActionMenuClient, GtkMenuClient
from window.globalmenu.registrar import Registrar

_NODE_NAME_RE = re.compile(r'<node name="([^"]+)"')

_DBUS_TIMEOUT_INTROSPECT = 500
_DBUS_TIMEOUT_PID = 200
_DBUS_TIMEOUT_FAST = 100

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

_MenuClient = Union[DBusMenuClient, GtkMenuClient, ActionMenuClient]


class _IntrospectionCache:
    """Caches DBus Introspect XML per service+path to avoid redundant round-trips."""

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, service: str, path: str, bus, timeout: int) -> str:
        if not path or not GLib.Variant.is_object_path(path):
            return ""
        key = f"{service}:{path}"
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        xml = _dbus_introspect(bus, service, path, timeout)
        with self._lock:
            self._cache[key] = xml
        return xml

    def invalidate(self, service: str):
        prefix = f"{service}:"
        with self._lock:
            self._cache = {
                k: v for k, v in self._cache.items() if not k.startswith(prefix)
            }


@dataclass
class AppServiceInfo:
    service_name: str
    object_path: str = ""
    pid: int = 0
    executable: str = ""
    wm_class: str = ""
    app_id: str = ""
    importer: Optional[_MenuClient] = None
    revision: int = 0
    connected_signals: bool = False


def _resolve_executable(pid: int) -> str:
    try:
        return os.path.realpath(f"/proc/{pid}/exe")
    except Exception as e:
        logger.warning(
            f"[service] return os.path.realpath(f'/proc/(pid)/exe') failed: {e}"
        )
        return ""


def _dbus_introspect(bus, service: str, path: str, timeout: int) -> str:
    if not path or not GLib.Variant.is_object_path(path):
        return ""
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
    except Exception as e:
        logger.debug(f"[service] introspect {service}:{path} failed: {e}")
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
    except Exception as e:
        logger.debug(f"[service] GetConnectionUnixProcessID for {service} failed: {e}")
        return 0


class GlobalMenuService(Service):
    """Service that extracts and provides application menus for the global menu bar."""

    @Signal
    def menu_changed(self, menu_items: object) -> None: ...

    @Signal
    def active_app_changed(self, app_name: str, wm_class: str) -> None: ...

    @Property(object, flags="read-write")
    def current_menu(self) -> Optional[list[DBusMenuItem]]:
        return self._current_menu

    def __init__(self):
        super().__init__()
        self._current_menu: Optional[list[DBusMenuItem]] = None
        self._current_app: str = ""
        self._current_wm_class: str = ""
        self._current_pid: int = 0

        self._service_registry: dict[str, AppServiceInfo] = {}
        self._pid_to_service: dict[int, str] = {}

        self._introspection_cache = _IntrospectionCache()

        self._seq_lock = threading.Lock()
        self._extraction_seq = 0
        self._extracting_in_flight: set[str] = set()

        self._inflight_lock = threading.Lock()
        self._registry_lock = threading.Lock()
        self._state_lock = threading.Lock()

        Registrar.get_instance().start()
        self._subscribe_name_owner_changed()
        threading.Thread(target=self._setup_environment, daemon=True).start()
        threading.Thread(target=self._scan_initial_services, daemon=True).start()

        logger.info("[GlobalMenuService] Initialized event-driven registry")

    def _subscribe_name_owner_changed(self):
        try:
            bus = _get_bus()
            bus.signal_subscribe(
                "org.freedesktop.DBus",
                "org.freedesktop.DBus",
                "NameOwnerChanged",
                "/org/freedesktop/DBus",
                None,
                Gio.DBusCallFlags.NONE,
                self._on_name_owner_changed,
            )
            logger.debug("[GlobalMenuService] Subscribed to NameOwnerChanged")
        except Exception as e:
            logger.error(
                f"[GlobalMenuService] Failed to subscribe NameOwnerChanged: {e}"
            )

    def _on_name_owner_changed(
        self,
        _connection,
        _sender_name,
        _object_path,
        _interface_name,
        _signal_name,
        parameters,
    ):
        try:
            name, old_owner, new_owner = parameters.unpack()
        except Exception as e:
            logger.warning(
                f"[service] name, old_owner, new_owner = parameters.unpack() failed: {e}"
            )
            return

        if not name or name.startswith(":") or name == "org.freedesktop.DBus":
            return

        if new_owner and not old_owner:
            threading.Thread(
                target=self._on_service_appeared,
                args=(name,),
                daemon=True,
            ).start()
        elif not new_owner:
            self._on_service_disappeared(name)

    def _on_service_appeared(self, service_name: str):
        try:
            bus = _get_bus()
            pid = _dbus_get_pid(bus, service_name, _DBUS_TIMEOUT_FAST)
            if pid <= 0:
                return
            executable = _resolve_executable(pid)
            self._register_new_service(service_name, pid, executable)
            self._introspection_cache.invalidate(service_name)
            logger.debug(
                f"[GlobalMenuService] Registered new service: {service_name} pid={pid}"
            )
        except Exception as e:
            logger.debug(
                f"[GlobalMenuService] Failed to register new service {service_name}: {e}"
            )

    def _on_service_disappeared(self, service_name: str):
        with self._registry_lock:
            entry = self._service_registry.pop(service_name, None)
            if entry is None:
                return
            if entry.pid:
                self._pid_to_service.pop(entry.pid, None)
            if isinstance(entry.importer, DBusMenuClient):
                try:
                    entry.importer.disconnect_signals()
                except Exception as e:
                    logger.warning(
                        f"[service] entry.importer.disconnect_signals() failed: {e}"
                    )

        self._introspection_cache.invalidate(service_name)

        with self._state_lock:
            if entry.wm_class and entry.wm_class == self._current_wm_class:
                self._current_menu = None

        logger.debug(
            f"[GlobalMenuService] Cleaned up disappeared service: {service_name}"
        )

    def _setup_environment(self):
        setup_global_menu_environment()

    def _uid(self, wm_class: str, pid: int) -> str:
        return f"{wm_class}:{pid}"

    def _resolve_current_entry(self) -> tuple[Optional[AppServiceInfo], int]:
        """Return the registry entry and PID for the currently active window."""
        with self._state_lock:
            pid = self._current_pid
        if pid == 0:
            logger.warning(
                "[GlobalMenuService] _resolve_current_entry: _current_pid is 0"
            )
            return None, 0
        with self._registry_lock:
            svc = self._pid_to_service.get(pid)
            entry = self._service_registry.get(svc) if svc else None
        if not svc:
            logger.warning(
                f"[GlobalMenuService] _resolve_current_entry: no service for pid {pid}"
            )
        elif not entry:
            logger.warning(
                f"[GlobalMenuService] _resolve_current_entry: no entry for service '{svc}' (pid {pid})"
            )
        elif not entry.importer:
            logger.warning(
                f"[GlobalMenuService] _resolve_current_entry: importer is None for '{svc}' (pid {pid})"
            )
        return entry, pid

    def _register_new_service(
        self, service_name: str, pid: int, executable: str = ""
    ) -> None:
        """Add a newly discovered service to the registry if not already present."""
        with self._registry_lock:
            if service_name in self._service_registry:
                return
            self._service_registry[service_name] = AppServiceInfo(
                service_name=service_name,
                pid=pid,
                executable=executable,
            )
            if pid:
                self._pid_to_service[pid] = service_name

    def update_active_window(self, app_name: str, wm_class: str):
        target_pid = 0
        try:
            out = exec_shell_command("hyprctl activewindow -j")
            if out:
                data = json.loads(out)
                target_pid = data.get("pid", 0)
        except Exception as e:
            logger.warning(
                f"[service] out = exec_shell_command('hyprctl activewindow -j') failed: {e}"
            )

        with self._state_lock:
            same_class = wm_class == self._current_wm_class
            same_pid = target_pid != 0 and target_pid == self._current_pid

        if same_class and same_pid:
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

        with self._registry_lock:
            svc_name = self._pid_to_service.get(target_pid) if target_pid else None
            registered_entry = (
                self._service_registry.get(svc_name) if svc_name else None
            )

        if registered_entry and registered_entry.importer:
            cached_menu = getattr(registered_entry.importer, "_cached_items", None)
            if cached_menu is not None and len(cached_menu) > 0:
                with self._state_lock:
                    self._current_menu = cached_menu
                logger.info(f"[GlobalMenuService] Registry cache hit for '{wm_class}'")
                self.menu_changed(cached_menu)
                return
            thread = threading.Thread(
                target=self._extract_from_importer,
                args=(wm_class, seq, registered_entry.importer, ""),
                daemon=True,
            )
            thread.start()
            return

        with self._state_lock:
            self._current_menu = None
        self.menu_changed([])

        inflight_key = self._uid(wm_class, target_pid)
        with self._inflight_lock:
            if inflight_key in self._extracting_in_flight:
                logger.debug(
                    f"[GlobalMenuService] Extraction in-flight for '{inflight_key}' — skipping"
                )
                return
            self._extracting_in_flight.add(inflight_key)

        logger.info(
            f"[GlobalMenuService] Starting extraction for '{wm_class}' pid={target_pid}"
        )
        thread = threading.Thread(
            target=self._extract_menu,
            args=(wm_class, seq, target_pid, inflight_key),
            daemon=True,
        )
        thread.start()

    def _connect_importer_signals(self, entry: AppServiceInfo):
        if entry.connected_signals or not isinstance(entry.importer, DBusMenuClient):
            return

        svc_name = entry.service_name

        def on_layout_updated(parent_id, revision, _properties):
            threading.Thread(
                target=self._handle_layout_updated,
                args=(svc_name, parent_id, revision),
                daemon=True,
            ).start()

        def on_items_updated(updated_props, removed_ids):
            threading.Thread(
                target=self._handle_items_updated,
                args=(svc_name, updated_props, removed_ids),
                daemon=True,
            ).start()

        entry.importer.connect_signals(
            on_layout_updated=on_layout_updated,
            on_items_updated=on_items_updated,
            on_item_activated=lambda item_id, _ts: logger.debug(
                f"[GlobalMenuService] Item activated: {item_id}"
            ),
        )
        entry.connected_signals = True
        logger.debug(f"[GlobalMenuService] Connected signals for {entry.service_name}")

    def _handle_layout_updated(self, svc_name: str, parent_id: int, revision: int):
        with self._registry_lock:
            entry = self._service_registry.get(svc_name)
            if not entry or not entry.importer:
                return
            entry.revision = revision
        subtree = entry.importer.update_layout(parent_id, revision)
        if subtree is None:
            return
        if parent_id == 0:
            with self._state_lock:
                if entry.wm_class == self._current_wm_class:
                    self._current_menu = subtree
                    with self._seq_lock:
                        self._extraction_seq += 1
                        seq = self._extraction_seq
                    idle_add(self._emit_menu_changed, subtree, seq)

    def _handle_items_updated(
        self,
        svc_name: str,
        updated_props: list[tuple[int, dict]],
        removed_ids: list[int],
    ):
        with self._registry_lock:
            entry = self._service_registry.get(svc_name)
            if (
                not entry
                or not entry.importer
                or not isinstance(entry.importer, DBusMenuClient)
            ):
                return
        entry.importer.apply_items_update(updated_props, removed_ids)
        with self._state_lock:
            if entry.wm_class == self._current_wm_class:
                self._current_menu = entry.importer.get_layout()

    def _extract_from_importer(
        self,
        wm_class: str,
        seq: int,
        client: _MenuClient,
        inflight_key: str,
    ):
        try:
            with self._seq_lock:
                if seq != self._extraction_seq:
                    return

            items = client.get_layout() or []

            with self._seq_lock:
                current_seq = self._extraction_seq

            if seq != current_seq:
                return

            with self._state_lock:
                if wm_class == self._current_wm_class:
                    self._current_menu = items

            idle_add(self._emit_menu_changed, items, current_seq)
        except Exception as e:
            logger.error(
                f"[GlobalMenuService] Error extracting from importer for '{wm_class}': {e}"
            )
        finally:
            if inflight_key:
                with self._inflight_lock:
                    self._extracting_in_flight.discard(inflight_key)

    def _scan_initial_services(self):
        try:
            bus = _get_bus()
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
            if not res:
                return
            names = res.get_child_value(0).unpack()
            for name in names:
                if name.startswith(":"):
                    continue
                pid = _dbus_get_pid(bus, name, _DBUS_TIMEOUT_FAST)
                if pid <= 0:
                    continue
                executable = _resolve_executable(pid)
                self._register_new_service(name, pid, executable)
            logger.debug(
                f"[GlobalMenuService] Initial scan: registered {len(names)} services"
            )
        except Exception as e:
            logger.debug(f"[GlobalMenuService] Initial scan error: {e}")

    def _discover_dbus_client(
        self, wm_class: str, target_pid: int = 0
    ) -> Optional[_MenuClient]:
        try:
            if target_pid <= 0:
                out = exec_shell_command("hyprctl activewindow -j")
                if not out:
                    return None
                target_pid = json.loads(out).get("pid", 0)
            if target_pid <= 0:
                return None

            strategies = [
                self._find_registry,
                self._find_registrar,
                self._find_fallback_scan,
            ]

            for strategy in strategies:
                result = strategy(wm_class, target_pid)
                if result is not None:
                    return result
        except Exception as e:
            logger.debug(f"[GlobalMenuService] Discovery failed: {e}")
        return None

    def _find_registry(self, wm_class: str, target_pid: int) -> Optional[_MenuClient]:
        with self._registry_lock:
            svc_name = self._pid_to_service.get(target_pid)
            entry = self._service_registry.get(svc_name) if svc_name else None
            if entry and entry.importer:
                logger.info(f"[GlobalMenuService] Registry match: {svc_name}")
                return entry.importer
        return None

    def _find_registrar(self, wm_class: str, target_pid: int) -> Optional[_MenuClient]:
        bus = _get_bus()
        registrar = Registrar.get_instance()
        registered = registrar.get_all_registrations()
        for window_id, reg in registered.items():
            service, path = reg.bus_name, reg.object_path
            try:
                pid = _dbus_get_pid(bus, service, _DBUS_TIMEOUT_FAST)
                if pid == target_pid or self._is_same_app(pid, target_pid):
                    logger.info(
                        f"[GlobalMenuService] Registrar match: {service} {path}"
                    )
                    client = DBusMenuClient(service, path)
                    if client.get_layout():
                        self._cache_discovery(service, path, pid, wm_class, client)
                        return client
                    gtk_client = GtkMenuClient(service, path)
                    if gtk_client.get_layout():
                        self._cache_discovery(service, path, pid, wm_class, gtk_client)
                        return gtk_client
                    self._cache_discovery(service, path, pid, wm_class, client)
                    return client
            except Exception as e:
                if "NameHasNoOwner" in str(e):
                    registrar.unregister_window(window_id)
        return None

    def _find_fallback_scan(
        self, wm_class: str, target_pid: int
    ) -> Optional[_MenuClient]:
        bus = _get_bus()
        try:
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
            if not res:
                return None
            names = res.get_child_value(0).unpack()
        except Exception as e:
            logger.warning(
                f"[service] res = bus.call_sync( 'org.freedesktop.DBus', '/org/freede... failed: {e}"
            )
            return None

        services = [
            n
            for n in names
            if n != "org.freedesktop.DBus" and not n.startswith("org.freedesktop.DBus")
        ]

        for svc in services:
            try:
                pid = _dbus_get_pid(bus, svc, _DBUS_TIMEOUT_PID)
                if not (pid == target_pid or self._is_same_app(pid, target_pid)):
                    continue

                registrar = Registrar.get_instance()
                reg_entry = registrar.get_menu_for_bus_name(svc)
                if reg_entry:
                    logger.info(
                        f"[GlobalMenuService] Found Registrar path {reg_entry.object_path} for {svc}"
                    )
                    client = DBusMenuClient(reg_entry.bus_name, reg_entry.object_path)
                    self._cache_discovery(
                        svc, reg_entry.object_path, pid, wm_class, client
                    )
                    return client

                _safe_cls = re.sub(r"[^A-Za-z0-9_]", "", wm_class) if wm_class else ""
                _safe_cap = _safe_cls.capitalize() if _safe_cls else ""

                dynamic_bases = self._build_dynamic_bases(svc, _safe_cls, _safe_cap)
                fallback_paths, _seen_fallback = self._introspect_paths(
                    bus, svc, dynamic_bases
                )

                for path in fallback_paths:
                    xml = self._introspection_cache.get(
                        svc, path, bus, _DBUS_TIMEOUT_INTROSPECT
                    )
                    if "com.canonical.dbusmenu" in xml:
                        logger.info(f"[GlobalMenuService] DBusMenu found: {svc} {path}")
                        client = DBusMenuClient(svc, path)
                        self._cache_discovery(svc, path, pid, wm_class, client)
                        return client

                gtk_candidates = []
                for path in fallback_paths:
                    xml = self._introspection_cache.get(
                        svc, path, bus, _DBUS_TIMEOUT_INTROSPECT
                    )
                    if "org.gtk.Menus" in xml:
                        gtk_candidates.append((svc, path))

                existing_gtk_paths = {p for _, p in gtk_candidates}
                for dfs_path in self._dfs_find_interface(svc, "org.gtk.Menus"):
                    if dfs_path not in existing_gtk_paths:
                        gtk_candidates.append((svc, dfs_path))
                        existing_gtk_paths.add(dfs_path)

                for gsvc, gpath in gtk_candidates:
                    try:
                        test_client = GtkMenuClient(gsvc, gpath)
                        test_items = test_client.get_layout()
                        if not test_items:
                            for _ in range(4):
                                time.sleep(0.05)
                                if test_items := test_client.get_layout():
                                    break
                        if test_items:
                            logger.info(
                                f"[GlobalMenuService] GTK menu found: {gsvc} {gpath} ({len(test_items)} items)"
                            )
                            self._cache_discovery(
                                gsvc, gpath, pid, wm_class, test_client
                            )
                            return test_client
                    except Exception as e:
                        logger.warning(
                            f"[service] test_client = GtkMenuClient(gsvc, gpath) failed: {e}"
                        )

                action_candidates = self._build_action_candidates(
                    svc, _safe_cls, _safe_cap
                )
                action_candidates.extend(
                    self._dfs_find_interface(svc, "org.gtk.Actions")
                )

                for act_base in action_candidates:
                    xml = self._introspection_cache.get(
                        svc, act_base, bus, _DBUS_TIMEOUT_FAST
                    )
                    if 'interface name="org.gtk.Actions"' in xml:
                        test_client = ActionMenuClient(svc, act_base)
                        if test_items := test_client.get_layout():
                            logger.info(
                                f"[GlobalMenuService] Action menu: {svc} {act_base} ({len(test_items)} items)"
                            )
                            self._cache_discovery(
                                svc, act_base, pid, wm_class, test_client
                            )
                            return test_client

                logger.info(
                    f"[GlobalMenuService] No menu found for {svc} wm={wm_class}"
                )
            except Exception as e:
                logger.warning(
                    f"[service] pid = _dbus_get_pid(bus, svc, _DBUS_TIMEOUT_PID) failed: {e}"
                )
                continue
        return None

    def _build_action_candidates(
        self, svc: str, safe_cls: str, safe_cap: str
    ) -> list[str]:
        candidates = ["/"]
        name_path = "/" + svc.replace(".", "/") if not svc.startswith(":") else ""
        if name_path and GLib.Variant.is_object_path(name_path):
            candidates.append(name_path)
        candidates.append("/org/gtk/Application")

        if safe_cls:
            cls_lower = safe_cls.lower()
            candidates.extend([f"/org/{cls_lower}/{safe_cap}", f"/org/{cls_lower}"])
            for ns in [*_DE_NAMESPACES, cls_lower]:
                for app_part in (safe_cap, safe_cls):
                    p = f"/org/{ns}/{app_part}"
                    if GLib.Variant.is_object_path(p):
                        candidates.append(p)

        return candidates

    def _build_dynamic_bases(self, svc: str, _safe_cls: str, _safe_cap: str) -> list:
        static_paths = [
            "/MenuBar",
            "/com/canonical/menu",
            "/org/appmenu/gtk/window/menus/menubar",
            "/org/appmenu/gtk/window/menus/appmenu",
            "/org/appmenu/gtk/window",
            "/org/gtk/Application/menus",
            "/org/gtk/Application",
            "/org/xfce",
            "/org/cinnamon",
            "/org/libreoffice",
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

        svc_path = "/" + svc.replace(".", "/") if not svc.startswith(":") else ""
        if svc_path and GLib.Variant.is_object_path(svc_path):
            static_paths.append(svc_path)

        if _safe_cls:
            cls_lower = _safe_cls.lower()
            for ns in [*_DE_NAMESPACES, cls_lower]:
                for app_part in (_safe_cap, _safe_cls):
                    for suffix in ("menus/menubar", "menus/appmenu", "menus"):
                        p = f"/org/{ns}/{app_part}/{suffix}"
                        if GLib.Variant.is_object_path(p):
                            static_paths.append(p)
        return static_paths

    def _introspect_paths(self, bus, svc: str, bases: list) -> tuple[list, set]:
        fallback_paths = list(bases)
        seen_fallback = set(fallback_paths)

        def _add_paths(parent_path, xml_str):
            for child in _NODE_NAME_RE.findall(xml_str):
                child_path = f"{parent_path}/{child}"
                if (
                    GLib.Variant.is_object_path(child_path)
                    and child_path not in seen_fallback
                ):
                    seen_fallback.add(child_path)
                    fallback_paths.insert(0, child_path)
                    yield child_path

        for base in bases:
            if not GLib.Variant.is_object_path(base):
                continue
            xml_text = self._introspection_cache.get(
                svc, base, bus, _DBUS_TIMEOUT_INTROSPECT
            )
            for child_path in _add_paths(base, xml_text):
                cxml_text = self._introspection_cache.get(
                    svc, child_path, bus, _DBUS_TIMEOUT_FAST
                )
                list(_add_paths(child_path, cxml_text))

        return fallback_paths, seen_fallback

    def _cache_discovery(
        self,
        service: str,
        path: str,
        pid: int,
        wm_class: str,
        client: _MenuClient,
    ):
        with self._registry_lock:
            if service not in self._service_registry:
                entry = AppServiceInfo(
                    service_name=service,
                    object_path=path,
                    pid=pid,
                    wm_class=wm_class,
                    importer=client,
                )
                self._service_registry[service] = entry
                if pid:
                    self._pid_to_service[pid] = service
            else:
                entry = self._service_registry[service]
                entry.importer = client
                entry.object_path = path
                entry.wm_class = wm_class
                if pid and not entry.pid:
                    entry.pid = pid
                    self._pid_to_service[pid] = service

            self._connect_importer_signals(entry)

    def _dfs_find_interface(
        self,
        service: str,
        interface: str,
        path: str = "/",
        _depth: int = 0,
        _visited: Optional[set] = None,
        _node_count: Optional[list[int]] = None,
    ) -> list[str]:
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
            xml = self._introspection_cache.get(
                service, path, _get_bus(), _DBUS_TIMEOUT_INTROSPECT
            )
            if not xml:
                return results

            if f'interface name="{interface}"' in xml:
                results.append(path)

            for child in _NODE_NAME_RE.findall(xml):
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
        except Exception as e:
            logger.warning(
                f"[service] xml = self._introspection_cache.get( service, path, _get_... failed: {e}"
            )
        return results

    def _is_same_app(self, pid1: int, pid2: int) -> bool:
        if pid1 == pid2:
            return True
        try:
            exe1 = os.path.realpath(f"/proc/{pid1}/exe")
            exe2 = os.path.realpath(f"/proc/{pid2}/exe")
            if exe1 and exe2 and exe1 == exe2:
                return True
            try:
                with open(f"/proc/{pid1}/comm") as f:
                    comm1 = f.read().strip()
                with open(f"/proc/{pid2}/comm") as f:
                    comm2 = f.read().strip()
                if comm1 and comm2 and comm1 == comm2:
                    return True
            except OSError as e:
                logger.warning(
                    f"[service] with open(f'/proc/(pid1)/comm') as f: comm1 = f.read().st... failed: {e}"
                )

            def _ppid(p: int) -> int:
                try:
                    with open(f"/proc/{p}/stat") as f:
                        parts = f.read().split()
                        return int(parts[3]) if len(parts) > 4 else 0
                except Exception as e:
                    logger.warning(
                        f"[service] with open(f'/proc/(p)/stat') as f: parts = f.read().split... failed: {e}"
                    )
                    return 0

            if _ppid(pid1) == pid2 or _ppid(pid2) == pid1:
                return True
        except (OSError, PermissionError, FileNotFoundError) as e:
            logger.warning(
                f"[service] exe1 = os.path.realpath(f'/proc/(pid1)/exe') failed: {e}"
            )
        return False

    def _extract_menu(
        self, wm_class: str, seq: int, target_pid: int = 0, inflight_key: str = ""
    ):
        try:
            with self._seq_lock:
                if seq != self._extraction_seq:
                    return

            client = self._discover_dbus_client(wm_class, target_pid)
            items = []

            if client:
                items = client.get_layout()

            if items:
                logger.info(
                    f"[GlobalMenuService] Found menu for '{wm_class}': {len(items)} items"
                )
            else:
                logger.info(f"[GlobalMenuService] No DBus menu found for '{wm_class}'")

            with self._seq_lock:
                current_seq = self._extraction_seq

            if seq != current_seq:
                return

            with self._state_lock:
                if wm_class == self._current_wm_class:
                    self._current_menu = items

            idle_add(self._emit_menu_changed, items, current_seq)

        except Exception as e:
            logger.error(
                f"[GlobalMenuService] Error extracting menu for '{wm_class}': {e}"
            )
        finally:
            if inflight_key:
                with self._inflight_lock:
                    self._extracting_in_flight.discard(inflight_key)

    def _emit_menu_changed(self, items: list[DBusMenuItem], seq: int = 0):
        if seq:
            with self._seq_lock:
                if seq != self._extraction_seq:
                    return False
        with self._state_lock:
            self._current_menu = items
        self.menu_changed(items)
        return False

    def click_item(self, item_id: int) -> bool:
        entry, pid = self._resolve_current_entry()
        if entry and entry.importer:
            logger.debug(
                f"[GlobalMenuService] click_item: item_id={item_id}, "
                f"service={entry.service_name}, importer={type(entry.importer).__name__}"
            )
            entry.importer.click_item(item_id, pid=pid)
            return True
        logger.warning(
            f"[GlobalMenuService] click_item FAILED: item_id={item_id}, entry={entry}, pid={pid}"
        )
        return False

    def get_current_dbusmenu_info(self) -> tuple[Optional[str], Optional[str]]:
        """Return (unique_bus_name, object_path) for the current app if it has a DBusMenu server."""
        entry, _pid = self._resolve_current_entry()
        if entry and entry.importer and isinstance(entry.importer, DBusMenuClient):
            unique_name = self._resolve_unique_name(entry.importer.service_name)
            return unique_name, entry.importer.object_path
        return None, None

    def _resolve_unique_name(self, well_known_name: str) -> Optional[str]:
        """Resolve a well-known D-Bus name to its unique name (e.g. :1.123)."""
        try:
            bus = _get_bus()
            res = bus.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "GetNameOwner",
                GLib.Variant("(s)", (well_known_name,)),
                GLib.VariantType("(s)"),
                Gio.DBusCallFlags.NONE,
                _DBUS_TIMEOUT_FAST,
                None,
            )
            return res.get_child_value(0).get_string() if res else well_known_name
        except Exception as e:
            logger.warning(f"[service] GetNameOwner failed for {well_known_name}: {e}")
            return well_known_name

    def about_to_show(self, item_id: int) -> bool:
        entry, _pid = self._resolve_current_entry()
        if entry and entry.importer:
            return entry.importer.about_to_show(item_id)
        return False

    def refresh_menu_sync(self) -> list[DBusMenuItem]:
        entry, pid = self._resolve_current_entry()
        if not (entry and entry.importer):
            return []
        items = entry.importer.get_layout(force_refresh=True)
        with self._state_lock:
            if pid == self._current_pid:
                self._current_menu = items
        return items


_global_menu_svc_instance = None


def get_global_menu_service() -> GlobalMenuService:
    global _global_menu_svc_instance
    if _global_menu_svc_instance is None:
        _global_menu_svc_instance = GlobalMenuService()
    return _global_menu_svc_instance
