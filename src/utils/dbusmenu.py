"""
Universal DBus + GTK Global Menu Client
Supports:
- com.canonical.dbusmenu (KDE / Unity / XFCE)
- GTK appmenu-module DBusMenu
- GTK GMenuModel fallback (best-effort)
"""

import threading
from typing import List, Optional

from fabric.utils import Any, Gio, GLib, logger

# SHARED BUS — one connection for the entire process
_SESSION_BUS: Optional[Gio.DBusConnection] = None
_BUS_LOCK = threading.Lock()


def _get_bus() -> Gio.DBusConnection:
    global _SESSION_BUS
    if _SESSION_BUS is None:
        with _BUS_LOCK:
            if _SESSION_BUS is None:
                _SESSION_BUS = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return _SESSION_BUS


# DATA MODEL — __slots__ cuts ~200 bytes per instance
class DBusMenuItem:
    __slots__ = (
        "id",
        "label",
        "enabled",
        "visible",
        "type",
        "shortcut",
        "icon_name",
        "has_submenu",
        "children",
        "action_name",
        "action_target",
    )

    def __init__(
        self,
        id: int,
        label: str = "",
        enabled: bool = True,
        visible: bool = True,
        type: str = "standard",
        shortcut: str = "",
        icon_name: str = "",
        has_submenu: bool = False,
        children: Optional[List["DBusMenuItem"]] = None,
        action_name: str = "",
        action_target: Optional[Any] = None,
    ):
        self.id = id
        self.label = label
        self.enabled = enabled
        self.visible = visible
        self.type = type
        self.shortcut = shortcut
        self.icon_name = icon_name
        self.has_submenu = has_submenu
        self.children: List["DBusMenuItem"] = children if children is not None else []
        self.action_name = action_name
        self.action_target = action_target


# MAIN CLIENT
class DBusMenuClient:
    __slots__ = (
        "service_name",
        "object_path",
        "_cache",
        "_cache_valid",
        "_hash_cache",
        "_lock",
        "_fetching",
    )

    def __init__(self, service_name: str, object_path: str):
        self.service_name = service_name
        self.object_path = object_path

        self._cache: Optional[List[DBusMenuItem]] = None
        self._cache_valid = False
        self._hash_cache: Optional[str] = None

        self._lock = threading.Lock()
        self._fetching = False

    # DBUS CALL — uses shared session bus
    def _call(self, method, params, reply_type=None):
        try:
            return _get_bus().call_sync(
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

    # PUBLIC ENTRY
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

    # CORE FETCH LOGIC
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

    # HASH DIFF SYSTEM
    def _hash(self, items):
        flat: List[str] = []

        def walk(nodes):
            for n in nodes:
                flat.append(f"{n.id}:{n.label}:{n.enabled}")
                walk(n.children)

        walk(items)
        return str(hash("".join(flat)))

    # DBUSMENU PARSER
    def _parse_dbusmenu(self, node):
        item = DBusMenuItem(id=0)

        try:
            if node.n_children() != 3:
                return item

            item.id = node.get_child_value(0).get_int32()

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

            children = node.get_child_value(2)
            for i in range(children.n_children()):
                c = children.get_child_value(i)
                if c.is_of_type(GLib.VariantType("v")):
                    c = c.get_variant()
                item.children.append(self._parse_dbusmenu(c))

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
        try:
            res = _get_bus().call_sync(
                self.service_name,
                self.object_path,
                "org.gtk.Menus",
                "Start",
                GLib.Variant("(au)", ([0],)),
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
                    item = DBusMenuItem(id=i)
                    try:
                        if c.n_children() > 0:
                            item.label = c.get_child_value(0).get_string()
                    except Exception:
                        pass
                    if c.n_children() > 1:
                        sub = c.get_child_value(c.n_children() - 1)
                        item.children = self._parse_gtk_menu(sub)
                        item.has_submenu = bool(item.children)
                    items.append(item)
        except Exception:
            pass
        return items

    # ACTIONS
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
                GLib.Variant("(isvu)", (item_id, "clicked", GLib.Variant("s", ""), 0)),
            )
            self.invalidate()
        except Exception:
            pass

    # CACHE CONTROL
    def invalidate(self):
        self._cache_valid = False

    def prefetch_async(self):
        if self._fetching:
            return
        threading.Thread(
            target=self.get_layout, kwargs={"force_refresh": True}, daemon=True
        ).start()

    def on_focus(self):
        self.prefetch_async()
