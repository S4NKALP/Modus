"""Pure Python DBusMenu extractor using Gio.DBus."""

from dataclasses import dataclass, field
from typing import List, Optional

from fabric.utils import Gio, GLib, logger


@dataclass
class DBusMenuItem:
    id: int
    label: str = ""
    enabled: bool = True
    visible: bool = True
    type: str = "standard"  # standard, separator
    shortcut: str = ""
    icon_name: str = ""
    has_submenu: bool = False
    children: List["DBusMenuItem"] = field(default_factory=list)


class DBusMenuClient:
    def __init__(self, service_name: str, object_path: str):
        self.service_name = service_name
        self.object_path = object_path
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def _call_method(
        self,
        method: str,
        params: Optional[GLib.Variant],
        reply_type: Optional[GLib.VariantType],
    ) -> Optional[GLib.Variant]:
        try:
            return self.bus.call_sync(
                self.service_name,
                self.object_path,
                "com.canonical.dbusmenu",
                method,
                params,
                reply_type,
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
        except Exception as e:
            logger.debug(f"[DBusMenuClient] Call to {method} failed: {e}")
            return None

    def get_layout(
        self, parent_id: int = 0, recursion_depth: int = -1
    ) -> List[DBusMenuItem]:
        """Fetches and parses the full menu layout."""
        # Signature: iias -> u(ia{sv}av)
        params = GLib.Variant("(iias)", (parent_id, recursion_depth, []))
        res = self._call_method("GetLayout", params, None)
        if not res:
            return []

        try:
            # Result is usually a tuple: (u, (i, a{sv}, av)) or (u, v) depending on the DBus implementation
            # We bypass the strict type by unpacking the child
            if res.n_children() < 2:
                return []

            layout_var = res.get_child_value(1)
            if layout_var.is_of_type(GLib.VariantType("v")):
                layout_var = layout_var.get_variant()

            return self._parse_node(layout_var).children
        except Exception as e:
            logger.error(f"[DBusMenuClient] Error parsing GetLayout: {e}")
            return []

    def _parse_node(self, node: GLib.Variant) -> DBusMenuItem:
        """Parses a layout node (ia{sv}av) into a DBusMenuItem."""
        item = DBusMenuItem(id=0)

        try:
            # node is a struct with 3 elements: id (i), properties (a{sv}), children (av)
            if node.n_children() != 3:
                return item

            item.id = node.get_child_value(0).get_int32()

            props_dict = node.get_child_value(1).unpack()

            # Map properties
            item.label = props_dict.get("label", "").replace("_", "")
            item.enabled = props_dict.get("enabled", True)
            item.visible = props_dict.get("visible", True)
            item.type = props_dict.get("type", "standard")
            item.icon_name = props_dict.get("icon-name", "")

            # Submenus
            if props_dict.get("children-display") == "submenu":
                item.has_submenu = True

            # Shortcut parsing (usually a nested list of strings)
            shortcut_data = props_dict.get("shortcut")
            if (
                shortcut_data
                and isinstance(shortcut_data, list)
                and len(shortcut_data) > 0
            ):
                parts = []
                for s in shortcut_data[0]:
                    if s == "Control":
                        parts.append("Ctrl")
                    elif s == "Shift":
                        parts.append("Shift")
                    elif s == "Alt":
                        parts.append("Alt")
                    else:
                        parts.append(s.upper())
                item.shortcut = "+".join(parts)

            # Parse children
            children_array = node.get_child_value(2)
            for i in range(children_array.n_children()):
                child_var = children_array.get_child_value(i)
                if child_var.is_of_type(GLib.VariantType("v")):
                    child_var = child_var.get_variant()
                child_item = self._parse_node(child_var)
                if child_item.visible:
                    item.children.append(child_item)

        except Exception as e:
            logger.debug(f"[DBusMenuClient] Error parsing node: {e}")

        return item

    def about_to_show(self, item_id: int) -> bool:
        """Tells the app to populate a dynamic submenu."""
        # Signature: i -> b
        res = self._call_method(
            "AboutToShow", GLib.Variant("(i)", (item_id,)), GLib.VariantType("(b)")
        )
        if res:
            return res.get_child_value(0).get_boolean()
        return False

    def click_item(self, item_id: int) -> None:
        """Triggers the activation event on a menu item."""
        # Signature: isvu -> nothing
        # Event(id, eventId, data, timestamp)
        params = GLib.Variant("(isvu)", (item_id, "clicked", GLib.Variant("s", ""), 0))
        self._call_method("Event", params, None)
