import re
from typing import List, Optional

from fabric.utils import Gio, GLib, logger

from utils.dbusmenu import DBusMenuItem, _get_bus

_SUBMENU_RE = re.compile(r"submenu")


class GtkMenuClient:
    __slots__ = ("service_name", "object_path", "_action_path", "_cached_items")

    def __init__(self, service_name: str, object_path: str):
        self.service_name = service_name
        self.object_path = object_path
        # Actions live at the parent of /menus/...
        self._action_path = (
            object_path.split("/menus/")[0] if "/menus/" in object_path else object_path
        )
        self._cached_items: List[DBusMenuItem] = []

    def _call(self, interface, method, params, reply_type=None, path=None):
        try:
            return _get_bus().call_sync(
                self.service_name,
                path or self.object_path,
                interface,
                method,
                params,
                reply_type,
                Gio.DBusCallFlags.NONE,
                3000,
                None,
            )
        except Exception as e:
            logger.debug(f"[GtkMenuClient] {method} failed: {e}")
            return None

    def get_layout(self, parent_id: int = 0) -> List[DBusMenuItem]:
        items = self._fetch_menu(parent_id)
        self._cached_items = items
        return items

    def _find_item(
        self, item_id: int, items: Optional[List[DBusMenuItem]] = None
    ) -> Optional[DBusMenuItem]:
        if items is None:
            items = self._cached_items
        for item in items:
            if item.id == item_id:
                return item
            if item.children:
                found = self._find_item(item_id, item.children)
                if found:
                    return found
        return None

    def _fetch_menu(
        self, menu_id: int, _depth: int = 0, _visited: Optional[set] = None
    ) -> List[DBusMenuItem]:
        if _depth > 10:
            return []
        if _visited is None:
            _visited = set()
        if menu_id in _visited:
            return []
        _visited.add(menu_id)
        res = self._call(
            "org.gtk.Menus",
            "Start",
            GLib.Variant("(au)", ([menu_id],)),
            GLib.VariantType("(a(uuaa{sv}))"),
        )
        if not res:
            return []

        try:
            data = res.get_child_value(0).unpack()
            if not data:
                return []

            entry_map = {}
            for entry in data:
                gid, mid, sections = entry
                entry_map[(gid, mid)] = sections

            items: List[DBusMenuItem] = []

            def resolve(sections, visited=None):
                if visited is None:
                    visited = set()
                for props in sections:
                    if not isinstance(props, dict):
                        continue
                    if ":section" in props:
                        ref = props[":section"]
                        if isinstance(ref, (list, tuple)) and len(ref) == 2:
                            key = (int(ref[0]), int(ref[1]))
                            if key not in visited:
                                visited.add(key)
                                child = entry_map.get(key)
                                if child is not None:
                                    resolve(child, visited)
                        continue
                    if not props.get("label") and not any(
                        k in props for k in ("action", ":submenu", "submenu")
                    ):
                        continue
                    item = DBusMenuItem(id=hash((menu_id, len(items))))
                    item.label = props.get("label", "").replace("_", "")
                    item.enabled = props.get("enabled", True)
                    item.visible = props.get("visible", True)
                    sub_ref = props.get(":submenu") or props.get("submenu")
                    if (
                        sub_ref
                        and isinstance(sub_ref, (list, tuple))
                        and len(sub_ref) == 2
                    ):
                        item.has_submenu = True
                        item.children = self._fetch_menu(
                            int(sub_ref[0]), _depth + 1, _visited
                        )
                    if "action" in props:
                        item.action_name = props["action"]
                    if "target" in props:
                        try:
                            item.action_target = GLib.Variant.new_variant(
                                GLib.Variant("v", props["target"])
                            )
                        except Exception:
                            pass
                    items.append(item)

            if data:
                resolve(data[0][2])

            return items
        except Exception as e:
            logger.error(f"[GtkMenuClient] Parse error: {e}")
            return []

    def about_to_show(self, item_id: int) -> bool:
        return False

    def click_item(
        self, item_id: int, action_name: str = "", action_target=None
    ) -> None:
        if not action_name:
            item = self._find_item(item_id)
            if item and item.action_name:
                action_name = item.action_name
                action_target = item.action_target
        if not action_name:
            return
        # Strip the unity. prefix added by appmenu-gtk-module
        if action_name.startswith("unity."):
            action_name = action_name[6:]
        try:
            params_arr = [action_target] if action_target is not None else []
            # Try menu path first (Thunar), fall back to action path (LibreOffice)
            for act_path in (self.object_path, self._action_path):
                try:
                    self._call(
                        "org.gtk.Actions",
                        "Activate",
                        GLib.Variant("(sava{sv})", (action_name, params_arr, {})),
                        path=act_path,
                    )
                    return
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"[GtkMenuClient] click failed: {e}")
