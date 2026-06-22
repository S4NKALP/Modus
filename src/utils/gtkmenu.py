from typing import List, Optional
from gi.repository import Gio, GLib
from fabric.utils import logger
from utils.dbusmenu import DBusMenuItem


class GtkMenuClient:
    def __init__(self, service_name: str, object_path: str):
        self.service_name = service_name
        self.object_path = object_path
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._action_group_path = self._guess_action_group_path(object_path)

    def _guess_action_group_path(self, menu_path: str) -> str:
        # Menus are usually /org/appmenu/gtk/window/menus/menubar/10
        # Actions are usually /org/appmenu/gtk/window/10
        if "/menus/" in menu_path:
            return menu_path.split("/menus/")[0]
        # Some apps export actions at the exact same path
        return menu_path

    def _call_method(
        self,
        interface: str,
        method: str,
        params: Optional[GLib.Variant],
        reply_type: Optional[GLib.VariantType],
        path_override: Optional[str] = None,
    ) -> Optional[GLib.Variant]:
        try:
            return self.bus.call_sync(
                self.service_name,
                path_override or self.object_path,
                interface,
                method,
                params,
                reply_type,
                Gio.DBusCallFlags.NONE,
                3000,
                None,
            )
        except Exception as e:
            logger.debug(f"[GtkMenuClient] Call to {method} failed: {e}")
            return None

    def get_layout(self, parent_id: int = 0) -> List[DBusMenuItem]:
        return self._fetch_menu(parent_id)

    def _fetch_menu(self, menu_id: int) -> List[DBusMenuItem]:
        params = GLib.Variant("(au)", ([menu_id],))
        res = self._call_method(
            "org.gtk.Menus", "Start", params, GLib.VariantType("(a(uuaa{sv}))")
        )
        if not res:
            return []

        try:
            # Unpack the response
            # res is a tuple containing one element: the array
            data = res.get_child_value(0).unpack()

            if not data or len(data) == 0:
                return []

            # data[0] is (subscription_id, menu_id, groups)
            groups = data[0][2]

            items = []
            # each group is an array of dicts (items)
            for group_idx, group in enumerate(groups):
                # insert separator between groups
                if group_idx > 0 and len(items) > 0 and len(group) > 0:
                    items.append(DBusMenuItem(id=-1, type="separator"))

                for idx, props in enumerate(group):
                    item_id = hash(f"{menu_id}_{group_idx}_{idx}")
                    item = DBusMenuItem(id=item_id)

                    item.label = props.get("label", "").replace("_", "")

                    if "submenu" in props:
                        item.has_submenu = True
                        submenu_id = props["submenu"]
                        item.children = self._fetch_menu(submenu_id)

                    if "action" in props:
                        item.action_name = props["action"]
                    if "target" in props:
                        # Variant target
                        item.action_target = GLib.Variant.new_variant(
                            GLib.Variant("v", props["target"])
                        )

                    items.append(item)

            return items
        except Exception as e:
            logger.error(f"[GtkMenuClient] Parse error: {e}")
            return []

    def about_to_show(self, item_id: int) -> bool:
        # org.gtk.Menus doesn't have AboutToShow
        return False

    def click_item(
        self, item_id: int, action_name: str = "", action_target: GLib.Variant = None
    ) -> None:
        if not action_name:
            return

        try:
            # Action activation
            # Signature: Activate (sava{sv})
            # s: action_name
            # av: parameter (array of variants, empty if no target)
            # a{sv}: platform data

            params_arr = []
            if action_target is not None:
                params_arr = [action_target]

            params = GLib.Variant("(sava{sv})", (action_name, params_arr, {}))

            self._call_method(
                "org.gtk.Actions",
                "Activate",
                params,
                None,
                path_override=self._action_group_path,
            )
        except Exception as e:
            logger.error(f"[GtkMenuClient] Failed to click item: {e}")
