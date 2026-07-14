from typing import Any, Dict, List, Optional

from fabric.utils import Gio, GLib, logger

from window.globalmenu.dbusmenu import DBusMenuItem, _get_bus


def atspi_activate_menu_item(pid: int, label: str) -> bool:
    """Activate a menu item by label via AT-SPI accessibility interface.

    Used as a fallback when D-Bus org.gtk.Actions.Activate doesn't reach the
    app's real menu item handler (common with appmenu-gtk-module on Wayland
    where gdk_threads_add_idle_full dispatch may not fire).
    """
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError) as e:
        logger.warning(f"[gtkmenu] import gi failed: {e}")
        return False

    try:
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app is None:
                continue
            try:
                app_pid = app.get_process_id()
            except Exception as e:
                logger.warning(f"[gtkmenu] app_pid = app.get_process_id() failed: {e}")
                continue
            if app_pid != pid:
                continue

            def _find_menubar(obj, depth=0):
                if depth > 8:
                    return None
                try:
                    if obj.get_role_name() == "menu bar":
                        return obj
                    for j in range(obj.get_child_count()):
                        result = _find_menubar(obj.get_child_at_index(j), depth + 1)
                        if result:
                            return result
                except Exception as e:
                    logger.warning(
                        f"[gtkmenu] if obj.get_role_name() == 'menu bar': return obj failed: {e}"
                    )
                return None

            def _find_frame(obj, depth=0):
                if depth > 4:
                    return None
                try:
                    if obj.get_role_name() == "frame":
                        return obj
                    for j in range(obj.get_child_count()):
                        result = _find_frame(obj.get_child_at_index(j), depth + 1)
                        if result:
                            return result
                except Exception as e:
                    logger.warning(
                        f"[gtkmenu] if obj.get_role_name() == 'frame': return obj failed: {e}"
                    )
                return None

            frame = _find_frame(app)
            if not frame:
                continue
            menubar = _find_menubar(frame)
            if not menubar:
                continue

            label_lower = label.lower().strip()
            for j in range(menubar.get_child_count()):
                item = menubar.get_child_at_index(j)
                if item is None:
                    continue
                try:
                    item_name = (item.get_name() or "").lower().strip()
                except Exception as e:
                    logger.warning(
                        f"[gtkmenu] item_name = (item.get_name() or '').lower().strip() failed: {e}"
                    )
                    continue
                if item_name == label_lower or label_lower in item_name:
                    try:
                        n_actions = item.get_n_actions()
                        if n_actions > 0:
                            result = item.do_action(0)
                            if result:
                                logger.debug(
                                    f"[ATSPI] Activated menu item '{label}' "
                                    f"via do_action on pid {pid}"
                                )
                                return True
                    except Exception as e:
                        logger.debug(f"[ATSPI] do_action failed: {e}")
                    return False
            break
    except Exception as e:
        logger.debug(f"[ATSPI] activate_menu_item error: {e}")
    return False


class _ActionInfo:
    __slots__ = ("enabled", "parameter_type", "state", "state_type")

    def __init__(
        self,
        enabled: bool = True,
        parameter_type: str = "",
        state: Optional[Any] = None,
        state_type: str = "",
    ):
        self.enabled = enabled
        self.parameter_type = parameter_type
        self.state = state
        self.state_type = state_type


class GtkMenuClient:
    __slots__ = (
        "_action_cache",
        "_action_path",
        "_cached_items",
        "object_path",
        "service_name",
    )

    def __init__(self, service_name: str, object_path: str):
        self.service_name = service_name
        self.object_path = object_path
        self._action_path = (
            object_path.split("/menus/")[0] if "/menus/" in object_path else object_path
        )
        self._cached_items: List[DBusMenuItem] = []
        self._action_cache: Dict[str, _ActionInfo] = {}

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

    def get_layout(
        self, parent_id: int = 0, force_refresh: bool = False
    ) -> List[DBusMenuItem]:
        self._refresh_action_cache()
        if force_refresh or not self._cached_items:
            items = self._fetch_menu(parent_id)
            self._cached_items = items
        return self._cached_items

    def _refresh_action_cache(self):
        for path in dict.fromkeys([self._action_path, self.object_path]):
            try:
                res = self._call(
                    "org.gtk.Actions",
                    "DescribeAll",
                    None,
                    GLib.VariantType("(a{s(bgav)})"),
                    path=path,
                )
                if not res:
                    continue
                data = res.get_child_value(0).unpack()
                self._action_cache.clear()
                for name, (enabled, param_type_v, state_v) in data.items():
                    param_type = str(param_type_v) if param_type_v else ""
                    state = (
                        state_v.unpack()
                        if state_v and state_v.n_children() > 0
                        else None
                    )
                    state_type = ""
                    if state_v and state_v.n_children() > 0:
                        st = state_v.get_child_value(0)
                        state_type = st.get_type_string() if st else ""
                    self._action_cache[name] = _ActionInfo(
                        enabled=enabled,
                        parameter_type=param_type,
                        state=state,
                        state_type=state_type,
                    )
                return
            except Exception as e:
                logger.debug(f"[GtkMenuClient] DescribeAll cache error: {e}")

    def _describe_action(self, action_name: str) -> Optional[_ActionInfo]:
        cached = self._action_cache.get(action_name)
        if cached is not None:
            return cached
        for path in dict.fromkeys([self._action_path, self.object_path]):
            try:
                res = self._call(
                    "org.gtk.Actions",
                    "Describe",
                    GLib.Variant("(s)", (action_name,)),
                    GLib.VariantType("(bgav)"),
                    path=path,
                )
                if res:
                    enabled, param_type_v, state_v = res.unpack()
                    param_type = str(param_type_v) if param_type_v else ""
                    state = (
                        state_v.unpack()
                        if state_v and state_v.n_children() > 0
                        else None
                    )
                    state_type = ""
                    if state_v and state_v.n_children() > 0:
                        st = state_v.get_child_value(0)
                        state_type = st.get_type_string() if st else ""
                    info = _ActionInfo(enabled, param_type, state, state_type)
                    self._action_cache[action_name] = info
                    return info
            except Exception as e:
                logger.debug(f"[GtkMenuClient] Describe error for {action_name}: {e}")
        return None

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
                        item.action_target = props["target"]
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
        self,
        item_id: int,
        action_name: str = "",
        action_target=None,
        pid: int = 0,
    ) -> None:
        item_label = ""
        if not action_name:
            item = self._find_item(item_id)
            if item and item.action_name:
                action_name = item.action_name
                action_target = item.action_target
                item_label = item.label or ""
        if not action_name:
            return
        if action_name.startswith("unity."):
            action_name = action_name[6:]

        action_info = self._describe_action(action_name)
        use_change_state = False
        if action_info and action_info.state is not None:
            if action_info.state_type == "b" or action_info.parameter_type:
                use_change_state = True

        try:
            for act_path in (self.object_path, self._action_path):
                try:
                    if (
                        use_change_state
                        and action_info
                        and action_info.state is not None
                    ):
                        new_state = (
                            not action_info.state
                            if action_info.state_type == "b"
                            else action_info.state
                        )
                        self._call(
                            "org.gtk.Actions",
                            "ChangeState",
                            GLib.Variant(
                                "(sv)",
                                (
                                    action_name,
                                    GLib.Variant(action_info.state_type, new_state),
                                ),
                            ),
                            path=act_path,
                        )
                        return
                    else:
                        params_arr = self._build_activate_params(
                            action_info, action_target
                        )
                        self._call(
                            "org.gtk.Actions",
                            "Activate",
                            GLib.Variant("(sava{sv})", (action_name, params_arr, {})),
                            path=act_path,
                        )
                        if pid and item_label:
                            atspi_activate_menu_item(pid, item_label)
                        return
                except Exception as e:
                    logger.warning(
                        f"[gtkmenu] if ( use_change_state and action_info and action_info.sta... failed: {e}"
                    )
                    continue
        except Exception as e:
            logger.error(f"[GtkMenuClient] click failed: {e}")

        if not use_change_state and pid and item_label:
            atspi_activate_menu_item(pid, item_label)

    @staticmethod
    def _build_activate_params(action_info, action_target):
        """Build the parameters array for Activate call."""
        if action_target is not None:
            try:
                return GLib.Variant("av", [action_target])
            except Exception as e:
                logger.warning(
                    f"[gtkmenu] return GLib.Variant('av', [action_target]) failed: {e}"
                )
        if action_info and action_info.parameter_type:
            param_type_str = action_info.parameter_type
            if param_type_str and param_type_str != "()":
                try:
                    param_type = GLib.VariantType(param_type_str)
                    default_val = GLib.Variant.new_tuple(GLib.Variant(param_type, None))
                    return GLib.Variant("av", [default_val])
                except Exception as e:
                    logger.warning(
                        f"[gtkmenu] param_type = GLib.VariantType(param_type_str) failed: {e}"
                    )
        return GLib.Variant("av", [])


class ActionMenuClient:
    __slots__ = (
        "_action_cache",
        "_action_map",
        "_action_path",
        "_cached_items",
        "object_path",
        "service_name",
    )

    def __init__(self, service_name: str, object_path: str):
        self.service_name = service_name
        self.object_path = object_path
        self._action_path = object_path
        self._cached_items: List[DBusMenuItem] = []
        self._action_map: Dict[int, str] = {}
        self._action_cache: Dict[str, _ActionInfo] = {}

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
            logger.warning(
                f"[gtkmenu] return _get_bus().call_sync( self.service_name, path or s... failed: {e}"
            )
            return None

    def _refresh_action_cache(self):
        try:
            res = self._call(
                "org.gtk.Actions",
                "DescribeAll",
                None,
                GLib.VariantType("(a{s(bgav)})"),
            )
            if not res:
                return
            data = res.get_child_value(0).unpack()
            self._action_cache.clear()
            for name, (enabled, param_type_v, state_v) in data.items():
                param_type = str(param_type_v) if param_type_v else ""
                state = (
                    state_v.unpack() if state_v and state_v.n_children() > 0 else None
                )
                state_type = ""
                if state_v and state_v.n_children() > 0:
                    st = state_v.get_child_value(0)
                    state_type = st.get_type_string() if st else ""
                self._action_cache[name] = _ActionInfo(
                    enabled=enabled,
                    parameter_type=param_type,
                    state=state,
                    state_type=state_type,
                )
        except Exception as e:
            logger.debug(f"[ActionMenuClient] DescribeAll cache error: {e}")

    def _describe_action(self, action_name: str) -> Optional[_ActionInfo]:
        cached = self._action_cache.get(action_name)
        if cached is not None:
            return cached
        try:
            res = self._call(
                "org.gtk.Actions",
                "Describe",
                GLib.Variant("(s)", (action_name,)),
                GLib.VariantType("(bgav)"),
            )
            if res:
                enabled, param_type_v, state_v = res.unpack()
                param_type = str(param_type_v) if param_type_v else ""
                state = (
                    state_v.unpack() if state_v and state_v.n_children() > 0 else None
                )
                state_type = ""
                if state_v and state_v.n_children() > 0:
                    st = state_v.get_child_value(0)
                    state_type = st.get_type_string() if st else ""
                info = _ActionInfo(enabled, param_type, state, state_type)
                self._action_cache[action_name] = info
                return info
        except Exception as e:
            logger.debug(f"[ActionMenuClient] Describe error for {action_name}: {e}")
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
                        item.action_target = props["target"]
                    items.append(item)

            if data:
                resolve(data[0][2])

            return items
        except Exception as e:
            logger.error(f"[ActionMenuClient] Parse error: {e}")
            return []

    def get_layout(
        self, parent_id: int = 0, force_refresh: bool = False
    ) -> List[DBusMenuItem]:
        if parent_id != 0:
            return []
        self._refresh_action_cache()

        menu_items = self._fetch_menu(0)
        if menu_items:
            self._cached_items = menu_items
            return menu_items

        res = self._call(
            "org.gtk.Actions",
            "DescribeAll",
            None,
            GLib.VariantType("(a{s(bgav)})"),
        )
        if not res:
            return self._cached_items

        try:
            data = res.get_child_value(0).unpack()
            items: List[DBusMenuItem] = []
            self._action_map = {}
            for i, (name, (enabled, param_type_v, state_v)) in enumerate(data.items()):
                label = name.replace("-", " ").replace("_", " ").strip().title()
                param_type = str(param_type_v) if param_type_v else ""
                state = None
                state_type = ""
                if state_v and state_v.n_children() > 0:
                    st = state_v.get_child_value(0)
                    state_type = st.get_type_string() if st else ""
                    try:
                        state = st.get_value()
                    except Exception:
                        state = state_v.unpack() if state_v else None
                self._action_cache[name] = _ActionInfo(
                    enabled, param_type, state, state_type
                )
                item = DBusMenuItem(id=hash((0, i)))
                item.action_name = name
                item.visible = not bool(param_type) or param_type == "b"
                can_activate = not bool(param_type)
                item.enabled = enabled if can_activate else False
                item.label = label
                if param_type == "b":
                    item.type = "toggle"
                    item.enabled = enabled
                self._action_map[item.id] = name
                items.append(item)
            self._cached_items = items
            return items
        except Exception as e:
            logger.error(f"[ActionMenuClient] parse error: {e}")
            return self._cached_items

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

    def about_to_show(self, item_id: int) -> bool:
        return False

    def invalidate(self):
        self._cached_items = []
        self._action_map = {}
        self._action_cache.clear()

    def click_item(
        self,
        item_id: int,
        action_name: str = "",
        action_target=None,
        pid: int = 0,
    ) -> None:
        item_label = ""
        if not action_name:
            item = self._find_item(item_id)
            if item and item.action_name:
                action_name = item.action_name
                action_target = item.action_target
                item_label = item.label or ""
        if not action_name:
            return

        action_info = self._describe_action(action_name)
        use_change_state = False
        if action_info and action_info.state is not None:
            if action_info.state_type == "b" or action_info.parameter_type:
                use_change_state = True

        try:
            if use_change_state and action_info and action_info.state is not None:
                new_state = (
                    not action_info.state
                    if action_info.state_type == "b"
                    else action_info.state
                )
                self._call(
                    "org.gtk.Actions",
                    "ChangeState",
                    GLib.Variant(
                        "(sv)",
                        (action_name, GLib.Variant(action_info.state_type, new_state)),
                    ),
                )
                return
            else:
                params_arr = self._build_activate_params(action_info, action_target)
                self._call(
                    "org.gtk.Actions",
                    "Activate",
                    GLib.Variant("(sava{sv})", (action_name, params_arr, {})),
                )
                if pid and item_label:
                    atspi_activate_menu_item(pid, item_label)
                return
        except Exception as e:
            logger.error(f"[ActionMenuClient] click failed: {e}")

        if not use_change_state and pid and item_label:
            atspi_activate_menu_item(pid, item_label)

    @staticmethod
    def _build_activate_params(action_info, action_target):
        """Build the parameters array for Activate call."""
        if action_target is not None:
            try:
                return GLib.Variant("av", [action_target])
            except Exception as e:
                logger.warning(
                    f"[gtkmenu] return GLib.Variant('av', [action_target]) failed: {e}"
                )
        if action_info and action_info.parameter_type:
            param_type_str = action_info.parameter_type
            if param_type_str and param_type_str != "()":
                try:
                    param_type = GLib.VariantType(param_type_str)
                    default_val = GLib.Variant.new_tuple(GLib.Variant(param_type, None))
                    return GLib.Variant("av", [default_val])
                except Exception as e:
                    logger.warning(
                        f"[gtkmenu] param_type = GLib.VariantType(param_type_str) failed: {e}"
                    )
        return GLib.Variant("av", [])
