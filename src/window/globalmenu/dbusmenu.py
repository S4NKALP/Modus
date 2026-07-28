"""
Universal DBus + GTK Global Menu Client
Supports:
- com.canonical.dbusmenu (KDE / Unity / XFCE)
- GTK appmenu-module DBusMenu
- GTK GMenuModel fallback (best-effort)
- Incremental updates via DBusMenu signals
"""

import threading
from typing import Callable, Dict, List, Optional, Tuple

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


class DBusMenuItem:
    __slots__ = (
        "action_name",
        "action_target",
        "children",
        "enabled",
        "has_submenu",
        "icon_name",
        "id",
        "label",
        "parent_id",
        "shortcut",
        "type",
        "visible",
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
        parent_id: int = -1,
    ):
        self.id = id
        self.label = label
        self.enabled = enabled
        self.visible = visible
        self.type = type
        self.shortcut = shortcut
        self.icon_name = icon_name
        self.has_submenu = has_submenu
        self.children: List[DBusMenuItem] = children if children is not None else []
        self.action_name = action_name
        self.action_target = action_target
        self.parent_id = parent_id


class DBusMenuClient:
    __slots__ = (
        "_cache",
        "_cache_valid",
        "_fetching",
        "_hash_cache",
        "_lock",
        "_on_item_activated_cb",
        "_on_items_updated_cb",
        "_on_layout_updated_cb",
        "_revision",
        "_signal_ids",
        "object_path",
        "service_name",
    )

    def __init__(self, service_name: str, object_path: str):
        self.service_name = service_name
        self.object_path = object_path

        self._cache: Optional[List[DBusMenuItem]] = None
        self._cache_valid = False
        self._hash_cache: Optional[str] = None
        self._revision: int = 0

        self._lock = threading.Lock()
        self._fetching = False
        self._signal_ids: List[int] = []
        self._on_layout_updated_cb: Optional[Callable] = None
        self._on_items_updated_cb: Optional[Callable] = None
        self._on_item_activated_cb: Optional[Callable] = None

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
        except Exception as e:
            logger.warning(
                f"[dbusmenu] return _get_bus().call_sync( self.service_name, self.obje... failed: {e}"
            )
            return None

    def get_layout(self, force_refresh=False):
        with self._lock:
            if self._cache and self._cache_valid and not force_refresh:
                return self._cache
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
            return []

        try:
            revision = res.get_child_value(0).get_uint32()
            self._revision = revision

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

    def _hash(self, items):
        flat: List[str] = []

        def walk(nodes):
            for n in nodes:
                flat.append(f"{n.id}:{n.label}:{n.enabled}")
                walk(n.children)

        walk(items)
        return str(hash("".join(flat)))

    def _parse_dbusmenu(self, node, _depth: int = 0, _parent_id: int = -1):
        if _depth > 20:
            return DBusMenuItem(id=0)
        item = DBusMenuItem(id=0)

        try:
            if node.n_children() != 3:
                return item

            item.id = node.get_child_value(0).get_int32()
            item.parent_id = _parent_id

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
                if _depth >= 20:
                    break
                c = children.get_child_value(i)
                if c.is_of_type(GLib.VariantType("v")):
                    c = c.get_variant()
                item.children.append(self._parse_dbusmenu(c, _depth + 1, item.id))

            if item.has_submenu and not item.children:
                try:
                    self.about_to_show(item.id)
                except Exception as e:
                    logger.warning(
                        f"[dbusmenu] self.about_to_show(item.id) failed: {e}"
                    )

        except Exception as e:
            logger.warning(
                f"[dbusmenu] if node.n_children() != 3: return item failed: {e}"
            )

        return item

    def about_to_show(self, item_id):
        try:
            res = self._call(
                "AboutToShow",
                GLib.Variant("(i)", (item_id,)),
                GLib.VariantType("(b)"),
            )
            return res.get_child_value(0).get_boolean() if res else False
        except Exception as e:
            logger.warning(
                f"[dbusmenu] res = self._call( 'AboutToShow', GLib.Variant('(i)', (ite... failed: {e}"
            )
            return False

    def click_item(self, item_id, pid=0):
        logger.debug(
            f"[dbusmenu] click_item: item_id={item_id}, "
            f"service={self.service_name}, path={self.object_path}"
        )
        try:
            self._call(
                "Event",
                GLib.Variant("(isvu)", (item_id, "clicked", GLib.Variant("s", ""), 0)),
            )
            self.invalidate()
        except Exception as e:
            logger.warning(
                f"[dbusmenu] click_item: Event call failed for item_id={item_id}: {e}"
            )

        self._try_gtk_actions_fallback(item_id, pid)

    def _try_gtk_actions_fallback(self, item_id, pid=0):
        item = None
        if self._cache:
            item = self._find_in_cache(item_id)
        if not item or not item.action_name:
            return
        bus = _get_bus()
        action_name = item.action_name
        for path in (self.object_path,):
            try:
                desc = bus.call_sync(
                    self.service_name,
                    path,
                    "org.gtk.Actions",
                    "Describe",
                    GLib.Variant("(s)", (action_name,)),
                    GLib.VariantType("(bgav)"),
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None,
                )
                if not desc:
                    continue
                enabled, param_type_v, state_v = desc.unpack()
                if not enabled:
                    continue
                has_state = state_v and state_v.n_children() > 0
                if has_state:
                    st = state_v.get_child_value(0)
                    state_type = st.get_type_string() if st else ""
                    new_val = (
                        not st.get_boolean() if state_type == "b" else st.get_value()
                    )
                    bus.call_sync(
                        self.service_name,
                        path,
                        "org.gtk.Actions",
                        "ChangeState",
                        GLib.Variant(
                            "(sv)",
                            (action_name, GLib.Variant(state_type, new_val)),
                        ),
                        None,
                        Gio.DBusCallFlags.NONE,
                        1000,
                        None,
                    )
                else:
                    param_type = str(param_type_v) if param_type_v else ""
                    params = GLib.Variant("av", [])
                    if param_type and param_type != "()":
                        pt = GLib.VariantType(param_type)
                        params = GLib.Variant(
                            "av", [GLib.Variant.new_tuple(GLib.Variant(pt, None))]
                        )
                    bus.call_sync(
                        self.service_name,
                        path,
                        "org.gtk.Actions",
                        "Activate",
                        GLib.Variant("(sava{sv})", (action_name, params, {})),
                        None,
                        Gio.DBusCallFlags.NONE,
                        1000,
                        None,
                    )
                self.invalidate()
                return
            except Exception:
                continue

    def _find_in_cache(self, item_id):
        def walk(items):
            for i in items:
                if i.id == item_id:
                    return i
                found = walk(i.children)
                if found:
                    return found
            return None

        return walk(self._cache) if self._cache else None

    def invalidate(self):
        self._cache_valid = False

    def prefetch_async(self):
        if self._fetching:
            return
        threading.Thread(
            target=self.get_layout, kwargs={"force_refresh": True}, daemon=True
        ).start()

    def connect_signals(
        self,
        on_layout_updated: Optional[Callable] = None,
        on_items_updated: Optional[Callable] = None,
        on_item_activated: Optional[Callable] = None,
    ):
        self._on_layout_updated_cb = on_layout_updated
        self._on_items_updated_cb = on_items_updated
        self._on_item_activated_cb = on_item_activated

        bus = _get_bus()

        def handle_layout_updated(
            _connection, _sender, _path, _iface, _signal, params, _user_data=None
        ):
            try:
                parent_id, revision, properties = params.unpack()
                self._revision = revision
                if self._on_layout_updated_cb:
                    self._on_layout_updated_cb(parent_id, revision, properties)
            except Exception as e:
                logger.debug(f"[DBusMenuClient] LayoutUpdated handler error: {e}")

        def handle_items_properties_updated(
            _connection, _sender, _path, _iface, _signal, params, _user_data=None
        ):
            try:
                updated_props, removed_ids = params.unpack()
                if self._on_items_updated_cb:
                    self._on_items_updated_cb(updated_props, removed_ids)
                self._cache_valid = False
            except Exception as e:
                logger.debug(f"[DBusMenuClient] ItemsPropertiesUpdated error: {e}")

        def handle_item_activation_requested(
            _connection, _sender, _path, _iface, _signal, params, _user_data=None
        ):
            try:
                item_id, timestamp = params.unpack()
                if self._on_item_activated_cb:
                    self._on_item_activated_cb(item_id, timestamp)
            except Exception as e:
                logger.debug(f"[DBusMenuClient] ItemActivationRequested error: {e}")

        for sig_name, handler in [
            ("LayoutUpdated", handle_layout_updated),
            ("ItemsPropertiesUpdated", handle_items_properties_updated),
            ("ItemActivationRequested", handle_item_activation_requested),
        ]:
            sid = bus.signal_subscribe(
                self.service_name,
                "com.canonical.dbusmenu",
                sig_name,
                self.object_path,
                None,
                Gio.DBusCallFlags.NONE,
                handler,
                None,
            )
            if sid:
                self._signal_ids.append(sid)

    def disconnect_signals(self):
        if not self._signal_ids:
            return
        bus = _get_bus()
        for sid in self._signal_ids:
            try:
                bus.signal_unsubscribe(sid)
            except Exception as e:
                logger.warning(f"[dbusmenu] bus.signal_unsubscribe(sid) failed: {e}")
        self._signal_ids.clear()

    def update_layout(
        self, parent_id: int, revision: int
    ) -> Optional[List[DBusMenuItem]]:
        self._revision = revision
        params = GLib.Variant("(iias)", (parent_id, revision, []))
        res = self._call("GetLayout", params)
        if not res:
            return None
        try:
            layout = res.get_child_value(1)
            while layout.is_of_type(GLib.VariantType("v")):
                layout = layout.get_variant()
            parsed = self._parse_dbusmenu(layout).children
            if parent_id == 0:
                with self._lock:
                    self._hash_cache = self._hash(parsed)
                    self._cache = parsed
                    self._cache_valid = True
            return parsed
        except Exception as e:
            logger.error(f"[Menu] update_layout error: {e}")
            return None

    def apply_items_update(
        self, updated_props: List[Tuple[int, Dict]], removed_ids: List[int]
    ):
        if not self._cache:
            return
        removed_set = set(removed_ids)

        def walk(items):
            result = []
            for item in items:
                if item.id in removed_set:
                    continue
                for uid, props in updated_props:
                    if item.id == uid:
                        if "label" in props:
                            item.label = str(props["label"]).replace("_", "")
                        if "enabled" in props:
                            item.enabled = bool(props["enabled"])
                        if "visible" in props:
                            item.visible = bool(props["visible"])
                        if "type" in props:
                            item.type = str(props["type"])
                item.children = walk(item.children)
                result.append(item)
            return result

        with self._lock:
            self._cache = walk(self._cache)
            self._hash_cache = None
