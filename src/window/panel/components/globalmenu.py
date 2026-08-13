import os
import shutil
import sqlite3
import tempfile

from fabric.hyprland.widgets import HyprlandActiveWindow as ActiveWindow
from fabric.utils import FormattedString, GLib, exec_shell_command_async, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from gi.repository import Gtk

from shared.dialogs.about import AboutApp, get_about_window
from shared.window.dropdown import ModusDropdown, dropdown_option
from utils.app_name_resolver import format_window
from utils.gtk_utils import setup_cursor_hover
from utils.roam import modus_service
from window.globalmenu.service import get_global_menu_service
from window.settings.main import get_settings_window


def has_active_window():
    app_name = modus_service.current_active_app_name
    return app_name and app_name != "Modus"


_about_app_window = None


def _reset_about_app_window():
    global _about_app_window
    _about_app_window = None


def show_about_app(_=None):
    global _about_app_window
    if not has_active_window():
        return
    app_name = modus_service.current_active_app_name
    wmclass = getattr(modus_service, "current_active_wm_class", "")

    window = _about_app_window
    if window is None or getattr(window, "app_name", None) != app_name:
        if window is not None:
            window.destroy()
        window = AboutApp(app_name=app_name, wmclass=wmclass)
        window.connect("destroy", lambda *_: _reset_about_app_window())
        _about_app_window = window
    window.toggle(None)


# Menu factories
def _create_system_menu():
    return [
        dropdown_option(
            "About this PC", callback=lambda _: get_about_window().toggle()
        ),
        None,
        dropdown_option(
            "System Settings...",
            callback=lambda _: get_settings_window().toggle(),
        ),
        None,
        dropdown_option(
            "Force Quit",
            callback=lambda _: exec_shell_command_async(
                "hyprctl dispatch 'hl.dsp.window.kill()'", lambda *_: None
            ),
        ),
        None,
        dropdown_option(
            "Sleep",
            callback=lambda _: exec_shell_command_async(
                "systemctl suspend", lambda *_: None
            ),
        ),
        dropdown_option(
            "Restart",
            callback=lambda _: exec_shell_command_async(
                "systemctl reboot", lambda *_: None
            ),
        ),
        dropdown_option(
            "Shut Down",
            callback=lambda _: exec_shell_command_async(
                "shutdown now", lambda *_: None
            ),
        ),
        None,
        dropdown_option(
            "Lock Screen",
            "󰘳  +  CTRL  +  L",
            'fabric-cli exec modus "lock_screen.lock()"',
        ),
    ]


def _create_title_menu(app_name):
    menu = Gtk.Menu()
    for label, handler in [
        (f"About {app_name}", lambda *_: show_about_app()),
        (
            f"Quit {app_name}",
            lambda *_: exec_shell_command_async(
                "hyprctl dispatch 'hl.dsp.window.close()'", lambda *_: None
            ),
        ),
    ]:
        item = Gtk.MenuItem.new_with_label(label)
        item.connect("activate", handler)
        menu.append(item)
    menu.show_all()
    return menu


def _clean_label(label):
    return label.replace("_", "")


def _open_url(url):
    exec_shell_command_async(f"xdg-open {url}", lambda *_: None)


def _get_firefox_bookmarks(pid, folder_label):
    """Read Firefox/ZeN bookmarks from local SQLite database."""
    try:
        exe = os.path.realpath(f"/proc/{pid}/exe")
        is_zen = "zen" in exe.lower()
        is_ff = "firefox" in exe.lower() or "firefox" in exe
        if not (is_zen or is_ff):
            return None
        config_dir = os.path.expanduser(
            "~/.config/zen" if is_zen else "~/.mozilla/firefox"
        )
        profiles_ini = os.path.join(config_dir, "profiles.ini")
        if not os.path.exists(profiles_ini):
            return None
        profile_path = None
        with open(profiles_ini) as f:
            for line in f:
                line = line.strip()
                if line.startswith("Default=") and "1" in line:
                    profile_path = None
                if line.startswith("Path="):
                    profile_path = line.split("=", 1)[1].strip()
        if not profile_path:
            return None
        if not os.path.isabs(profile_path):
            profile_path = os.path.join(config_dir, profile_path)
        places = os.path.join(profile_path, "places.sqlite")
        if not os.path.exists(places):
            return None
        folder_map = {"Bookmarks Toolbar": "toolbar", "Other Bookmarks": "unfiled"}
        sqlite_name = folder_map.get(folder_label)
        if not sqlite_name:
            return None
        tmp = os.path.join(tempfile.gettempdir(), f"places_{pid}.sqlite")
        try:
            shutil.copy2(places, tmp)
        except Exception:
            return None
        try:
            conn = sqlite3.connect(tmp)
            cur = conn.execute(
                "SELECT id FROM moz_bookmarks WHERE title=? AND type=2",
                (sqlite_name,),
            )
            row = cur.fetchone()
            if not row:
                return None
            parent_id = row[0]
            cur = conn.execute(
                "SELECT b.title, p.url FROM moz_bookmarks b "
                "JOIN moz_places p ON b.fk = p.id "
                "WHERE b.parent=? AND b.type=1",
                (parent_id,),
            )
            items = []
            for title, url in cur:
                label = title if title else url
                items.append(
                    type(
                        "",
                        (),
                        {
                            "_url": url,
                            "label": label,
                            "visible": True,
                            "enabled": True,
                            "type": "standard",
                            "has_submenu": False,
                            "children": [],
                            "id": 0,
                        },
                    )()
                )
            conn.close()
            return items if items else None
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[GlobalMenu] bookmarks fallback failed: {e}")
        return None


TRUNCATE_MENU_AT = 25

MAX_GLOBAL_MENU_ITEMS = 32


def _truncate_children(children):
    if len(children) <= TRUNCATE_MENU_AT:
        return children
    truncated = list(children[:TRUNCATE_MENU_AT])
    remaining = len(children) - TRUNCATE_MENU_AT
    more = type(
        "",
        (),
        {
            "_url": None,
            "label": f"\u2192 {remaining} more bookmarks\u2026",
            "visible": True,
            "enabled": False,
            "type": "standard",
            "has_submenu": False,
            "children": [],
            "id": 0,
        },
    )()
    truncated.append(more)
    return truncated


def _on_item_select(item, svc, child, click_handler):
    if getattr(item, "_lazy_loaded", False):
        return
    item._lazy_loaded = True
    try:
        logger.info(
            f"[GlobalMenu] load submenu id={child.id} label={getattr(child, 'label', '')}"
        )
        svc.about_to_show(child.id)
        entry, _ = svc._resolve_current_entry()
        children = None
        if entry and entry.importer and hasattr(entry.importer, "update_layout"):
            children = entry.importer.update_layout(
                child.id, getattr(entry, "revision", 0)
            )
        if not children and entry:
            logger.info(
                "[GlobalMenu] DBus empty, trying Firefox bookmark SQLite fallback"
            )
            children = _get_firefox_bookmarks(entry.pid, child.label)
            if children:
                children = _truncate_children(children)
        if children:
            logger.info(
                f"[GlobalMenu] got {len(children)} children for id={child.id}: "
                f"{[getattr(c, 'label', '?') for c in children[:5]]}"
            )
            new_menu = _build_gtk_menu_from_children(children, click_handler, svc)
            new_menu.show_all()
            item.set_submenu(new_menu)
        else:
            logger.info(f"[GlobalMenu] no children for id={child.id}")
    except Exception as e:
        logger.warning(f"[GlobalMenu] submenu load failed: {e}")


def _build_gtk_menu_from_children(children, click_handler, svc=None):
    menu = Gtk.Menu()

    for child in children:
        if not getattr(child, "visible", True):
            continue

        child_type = getattr(child, "type", "standard")
        if child_type == "separator":
            menu.append(Gtk.SeparatorMenuItem())
            continue

        label = getattr(child, "label", "")
        if not label:
            continue

        cleaned = _clean_label(label)
        enabled = getattr(child, "enabled", True)
        sub_children = child.children if child.children else []
        has_sub = getattr(child, "has_submenu", False) or bool(sub_children)

        if has_sub:
            item = Gtk.MenuItem.new_with_label(f"{cleaned}  \u25b8")
            sub_menu = _build_gtk_menu_from_children(sub_children, click_handler, svc)
            sub_menu.show_all()
            item.set_submenu(sub_menu)

            if svc and getattr(child, "id", None) is not None:
                item.connect("select", _on_item_select, svc, child, click_handler)
        else:
            item = Gtk.MenuItem.new_with_label(cleaned)
            if not enabled:
                item.set_sensitive(False)
            url = getattr(child, "_url", None)
            if url:
                item.connect("activate", lambda *_: _open_url(url))
            else:
                item.connect("activate", click_handler, child.id)

        menu.append(item)

    menu.show_all()
    return menu


# GlobalMenuDropdowns
class GlobalMenuDropdowns:
    def __init__(self, parent, menu_box=None):
        self.parent = parent
        self._menu_box = menu_box
        self._imac_button = None

        self._global_menu_svc = get_global_menu_service()

        self._gtk_menu_buttons: list[Gtk.MenuButton] = []
        self._gtk_menus: list[Gtk.Menu] = []

        self._system_dropdown = ModusDropdown(items=_create_system_menu())
        self._system_menu = self._system_dropdown.menu

        self._title_menu = None

        self.global_menu_button_title = Gtk.MenuButton(name="global-menu")
        self.global_menu_button_title.get_style_context().add_class("flat")
        self.global_menu_button_title.show_all()
        setup_cursor_hover(self.global_menu_button_title, "pointer")

        self._set_title_menu(modus_service.current_active_app_name)

        self._active_window_ref = ActiveWindow(
            formatter=FormattedString(
                "{ format_window(win_title, win_class) }",
                format_window=format_window,
            ),
            name="global-menu",
        )
        self._active_window_ref.connect(
            "window_activated", self._on_window_label_update
        )
        self._active_window_ref.do_initialize()

        self.all_menu_buttons = [
            self.global_menu_button_title,
        ]

        modus_service.connect(
            "current-active-app-name-changed", self._on_active_app_changed
        )

        if self._global_menu_svc:
            self._global_menu_svc.connect("menu-changed", self._on_menu_changed)

    def _on_window_label_update(self, _, win_class, win_title):
        label = format_window(win_title, win_class)
        self.global_menu_button_title.set_label(label or "")

    def set_imac_button(self, button):
        self._imac_button = button
        self._system_menu.show_all()
        button.set_popup(self._system_menu)

    def _make_click_handler(self, _, item_id):
        if self._global_menu_svc:
            self._global_menu_svc.click_item(item_id)

    def _set_title_menu(self, app_name: str):
        old_menu = self._title_menu
        if app_name and app_name != "Modus":
            self._title_menu = _create_title_menu(app_name)
            self.global_menu_button_title.set_popup(self._title_menu)
        else:
            self._title_menu = None
            self.global_menu_button_title.set_popup(None)
        if old_menu is not None:
            GLib.idle_add(old_menu.destroy)

    def _on_active_app_changed(self, _, value):
        logger.info(f"[GlobalMenu] Active app changed: {value}")

        self._set_title_menu(value)

        if self._global_menu_svc:
            wm_class = getattr(modus_service, "current_active_wm_class", "")
            self._global_menu_svc.update_active_window(value, wm_class)

    def _on_menu_changed(self, _, menu_items: list):
        self._rebuild_dynamic_menus(menu_items)

    def _destroy_widgets(self, widgets):
        for widget in widgets:
            try:
                widget.destroy()
            except Exception:
                logger.exception("[globalmenu] widget destroy failed")

    def _cleanup_dynamic(self):
        for btn in self.all_menu_buttons:
            if btn is self.global_menu_button_title:
                continue
            try:
                if btn.get_parent():
                    btn.get_parent().remove(btn)
                btn.destroy()
            except Exception:
                logger.exception("[globalmenu] cleanup failed")

        self._gtk_menu_buttons.clear()

        self._destroy_widgets(self._gtk_menus)
        self._gtk_menus.clear()

    def _rebuild_dynamic_menus(self, menu_items: list):
        logger.info(f"[GlobalMenu] _rebuild_dynamic_menus: {len(menu_items)} items")

        self._cleanup_dynamic()

        top_level = [
            item for item in menu_items if item.label and getattr(item, "visible", True)
        ]

        if len(top_level) > MAX_GLOBAL_MENU_ITEMS:
            logger.warning(
                f"[GlobalMenu] truncating top-level menu to {MAX_GLOBAL_MENU_ITEMS} "
                f"items (from {len(top_level)})"
            )
            top_level = top_level[:MAX_GLOBAL_MENU_ITEMS]

        if not top_level:
            self.all_menu_buttons = [self.global_menu_button_title]
        else:
            new_buttons = [self.global_menu_button_title]

            for item in top_level:
                children = getattr(item, "children", None) or []
                has_children = getattr(item, "has_submenu", False) or bool(children)

                if not has_children:
                    btn = Button(label=item.label, name="global-menu")
                    setup_cursor_hover(btn, "pointer")
                    btn.connect("clicked", self._make_click_handler, item.id)
                    new_buttons.append(btn)
                else:
                    menu_btn = Gtk.MenuButton(label=item.label, name="global-menu")
                    menu_btn.get_style_context().add_class("global-menu")
                    setup_cursor_hover(menu_btn, "pointer")

                    gtk_menu = _build_gtk_menu_from_children(
                        children, self._make_click_handler, self._global_menu_svc
                    )
                    menu_btn.set_popup(gtk_menu)
                    menu_btn.show_all()

                    self._gtk_menu_buttons.append(menu_btn)
                    self._gtk_menus.append(gtk_menu)
                    new_buttons.append(menu_btn)

            self.all_menu_buttons = new_buttons

        if self._menu_box is not None:
            self._menu_box.children = self.all_menu_buttons
            self._menu_box.show_all()

    def destroy(self):
        try:
            modus_service.disconnect_by_func(self._on_active_app_changed)
        except Exception:
            logger.exception("[globalmenu] disconnect failed")

        if self._global_menu_svc:
            try:
                self._global_menu_svc.disconnect_by_func(self._on_menu_changed)
            except Exception:
                logger.exception("[globalmenu] svc disconnect failed")

        self._cleanup_dynamic()

        for name in ("_system_menu", "_title_menu"):
            obj = getattr(self, name, None)
            if obj:
                try:
                    obj.destroy()
                except Exception:
                    logger.exception(f"[globalmenu] {name} destroy failed")


class GlobalMenu(Box):
    def __init__(self, parent_window=None, **kwargs):
        if parent_window is None:
            parent_window = kwargs.pop("parent_window", None)

        super().__init__(
            name="globalmenu", orientation="horizontal", spacing=0, **kwargs
        )

        self.dropdown_system = GlobalMenuDropdowns(parent=parent_window, menu_box=self)
        self.children = self.dropdown_system.all_menu_buttons

    def set_imac_button(self, button):
        self.dropdown_system.set_imac_button(button)

    def show_system_dropdown(self, imac_button):
        self.dropdown_system.set_imac_button(imac_button)

    def destroy(self):
        if hasattr(self, "dropdown_system") and self.dropdown_system:
            try:
                self.dropdown_system.destroy()
            except Exception:
                logger.exception("[globalmenu] destroy failed")
        super().destroy()
