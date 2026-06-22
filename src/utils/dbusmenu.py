"""
Universal DBus + GTK Global Menu Client
Supports:
- com.canonical.dbusmenu (KDE / Unity / XFCE)
- GTK appmenu-module DBusMenu
- GTK GMenuModel fallback (best-effort)
"""

import threading
from dataclasses import dataclass, field
from typing import List, Optional

from fabric.utils import Any, Gio, GLib, logger


@dataclass
class DBusMenuItem:
    id: int
    label: str = ""
    enabled: bool = True
    visible: bool = True
    type: str = "standard"
    shortcut: str = ""
    icon_name: str = ""
    has_submenu: bool = False
    children: List["DBusMenuItem"] = field(default_factory=list)

    # GtkMenu specific fields
    action_name: str = ""
    action_target: Optional[Any] = None  # FIX #1: any → Any


class DBusMenuClient:
    def __init__(self, service_name: str, object_path: str):
        self.service_name = service_name
        self.object_path = object_path
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        self._pid: Optional[int] = None
        self._cache: Optional[List[DBusMenuItem]] = None
        self._cache_valid = False
        self._hash_cache: Optional[str] = None

        # concurrency guard
        self._lock = threading.Lock()
        self._fetching = False

    def set_pid(self, pid: int):
        self._pid = pid

    def _call(self, method, params, reply_type=None):
        try:
            return self.bus.call_sync(
                self.service_name,
                self.object_path,
                "com.canonical.dbusmenu",
                method,
                params,
                reply_type,
                Gio.DBusCallFlags.NONE,
                3000,
                None,
            )
        except Exception:
            return None

    def get_layout(self, force_refresh=False):
        if self._cache and self._cache_valid and not force_refresh:
            return self._cache

        with self._lock:
            if self._fetching:
                return self._cache or []
            self._fetching = True

        try:
            return self._fetch()
        finally:
            with self._lock:
                self._fetching = False

    def _fetch(self):
        params = GLib.Variant("(iias)", (0, -1, []))
        res = self._call("GetLayout", params)

        if not res:
            gtk_menu = self._try_gtk_menu()
            if gtk_menu:
                parsed = self._parse_gtk_menu(gtk_menu)
                self._cache = parsed
                self._cache_valid = True
                return parsed
            return []

        try:
            layout = res.get_child_value(1)

            while layout.is_of_type(GLib.VariantType("v")):
                layout = layout.get_variant()

            parsed = self._parse_dbusmenu(layout).children

            # diff detection — FIX #5: use fast string hash instead of MD5
            h = self._hash(parsed)
            if h == self._hash_cache:
                return self._cache or parsed

            self._hash_cache = h
            self._cache = parsed
            self._cache_valid = True

            return parsed

        except Exception as e:
            logger.error(f"[Menu] parse error: {e}")
            return []

    def _hash(self, items) -> str:
        flat = []

        def walk(nodes):
            for n in nodes:
                flat.append(f"{n.id}:{n.label}:{n.enabled}")
                walk(n.children)

        walk(items)
        return str(hash("".join(flat)))

    # DBUSMENU PARSER (KDE / XFCE / Unity)
    def _parse_dbusmenu(self, node):
        item = DBusMenuItem(id=0)

        try:
            if node.n_children() != 3:
                return item

            item.id = node.get_child_value(0).get_int32()

            # props
            try:
                props = node.get_child_value(1).unpack()
            except Exception:
                props = {}

            item.label = props.get("label", "").replace("_", "")
            item.enabled = props.get("enabled", True)
            item.visible = props.get("visible", True)
            item.type = props.get("type", "standard")
            item.icon_name = props.get("icon-name", "")

            if props.get("children-display") == "submenu":
                item.has_submenu = True

            # shortcut
            sc = props.get("shortcut")
            if sc:
                try:
                    parts = []
                    if isinstance(sc, list):
                        flat = sc[0] if isinstance(sc[0], list) else sc

                        mapping = {
                            "Control": "Ctrl",
                            "Shift": "Shift",
                            "Alt": "Alt",
                            "Meta": "Super",
                        }

                        for s in flat:
                            parts.append(mapping.get(s, str(s).upper()))

                    item.shortcut = "+".join(parts)
                except Exception:
                    item.shortcut = ""

            # children
            children = node.get_child_value(2)

            for i in range(children.n_children()):
                c = children.get_child_value(i)

                if c.is_of_type(GLib.VariantType("v")):
                    c = c.get_variant()

                item.children.append(self._parse_dbusmenu(c))

            # lazy GTK submenu trigger
            if item.has_submenu and not item.children:
                try:
                    self.about_to_show(item.id)
                except Exception:
                    pass

        except Exception:
            pass

        return item

    # GTK FALLBACK (GMenuModel-style)
    def _try_gtk_menu(self):
        # Passing None caused silent failure. Start with group 0.
        try:
            res = self.bus.call_sync(
                self.service_name,
                self.object_path,
                "org.gtk.Menus",
                "Get",
                GLib.Variant("(au)", ([0],)),  # FIX #2: correct parameter
                None,
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )

            return res.get_child_value(0) if res else None

        except Exception:
            return None

    def _parse_gtk_menu(self, variant):
        items = []

        try:
            if not variant:
                return []

            if variant.is_container():
                for i in range(variant.n_children()):
                    c = variant.get_child_value(i)

                    item = DBusMenuItem(
                        id=i,
                        label="",
                        enabled=True,
                        visible=True,
                    )

                    try:
                        if c.n_children() > 0:
                            item.label = c.get_child_value(0).get_string()
                    except Exception:
                        pass

                    # Use n_children() - 1 explicitly.
                    n = c.n_children()
                    if n > 1:
                        sub = c.get_child_value(n - 1)
                        item.children = self._parse_gtk_menu(sub)
                        item.has_submenu = len(item.children) > 0

                    items.append(item)

        except Exception:
            pass

        return items

    # GTK / DBUS ACTIONS
    def about_to_show(self, item_id):
        try:
            res = self._call(
                "AboutToShow",
                GLib.Variant("(i)", (item_id,)),
                GLib.VariantType("(b)"),
            )
            return res.get_child_value(0).get_boolean() if res else False
        except Exception:
            return False

    def click_item(self, item_id):
        try:
            self._call(
                "Event",
                GLib.Variant(
                    "(isvu)",
                    (item_id, "clicked", GLib.Variant("s", ""), 0),
                ),
            )
            self.invalidate()
        except Exception:
            pass

    def invalidate(self):
        self._cache_valid = False

    def prefetch_async(self):
        # If already fetching, skip — get_layout's _fetching flag handles dedup.
        with self._lock:
            if self._fetching:
                return
            # Mark fetching now so a second call before the thread starts also bails out.
            self._fetching = True

        def worker():
            try:
                self._fetch()
            finally:
                with self._lock:
                    self._fetching = False

        threading.Thread(target=worker, daemon=True).start()

    def on_focus(self):
        self.prefetch_async()
