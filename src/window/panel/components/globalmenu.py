from fabric.hyprland.widgets import HyprlandActiveWindow as ActiveWindow
from fabric.utils import FormattedString, exec_shell_command_async, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from gi.repository import Gtk

from shared.dialogs.about import AboutApp, get_about_window
from utils.app_name_resolver import format_window
from utils.gtk_utils import setup_cursor_hover
from utils.roam import modus_service
from window.globalmenu.service import get_global_menu_service
from window.settings.main import get_settings_window


def has_active_window():
    return (
        modus_service.current_active_app_name
        and modus_service.current_active_app_name != "Modus"
    )


def show_about_app(_=None):
    if not has_active_window():
        return
    app_name = modus_service.current_active_app_name
    wmclass = getattr(modus_service, "current_active_wm_class", "")
    about_window = AboutApp(app_name=app_name, wmclass=wmclass)
    about_window.toggle(None)


def _clean_label(label):
    return label.replace("_", "")


def _make_menu_item_click(item_id):
    def handler(_, __=None):
        svc = get_global_menu_service()
        if svc:
            svc.click_item(item_id)

    return handler


def _on_click_action(
    menu_item, on_clicked=None, on_click='echo "ModusPanelDropdown Action"'
):
    if on_clicked:
        on_clicked(menu_item)
    else:
        exec_shell_command_async(on_click, lambda *_: None)
    from shared.window.dropdown import dropdowns

    for dd in dropdowns:
        if dd.is_visible():
            dd.hide()
            break


# ========== GtkMenu builder ==========


def _build_gtk_menu_from_children(children):
    """Recursively build a Gtk.Menu from DBusMenuItem children."""
    menu = Gtk.Menu()
    menu.set_name("dropdown-options")

    for child in children:
        if not getattr(child, "visible", True):
            continue

        child_type = getattr(child, "type", "standard")
        if child_type == "separator":
            sep = Gtk.SeparatorMenuItem()
            sep.set_name("dropdown-divider")
            menu.append(sep)
            continue

        label = getattr(child, "label", "")
        if not label:
            continue

        cleaned = _clean_label(label)
        enabled = getattr(child, "enabled", True)
        sub_children = child.children if child.children else []
        has_sub = getattr(child, "has_submenu", False) or bool(sub_children)

        if has_sub and sub_children:
            item = Gtk.MenuItem.new_with_label(f"{cleaned}  ▸")
            item.set_name("dropdown-option")
            sub_menu = _build_gtk_menu_from_children(sub_children)
            sub_menu.show_all()
            item.set_submenu(sub_menu)
        else:
            item = Gtk.MenuItem.new_with_label(cleaned)
            item.set_name("dropdown-option")
            if not enabled:
                item.set_sensitive(False)
            item.connect("activate", _make_menu_item_click(child.id))

        menu.append(item)

    return menu


def _make_simple_gtk_menu(items):
    """Build a simple Gtk.Menu from a list of (label, on_activate, sensitive) tuples."""
    menu = Gtk.Menu()
    menu.set_name("dropdown-options")

    for entry in items:
        if entry is None:
            sep = Gtk.SeparatorMenuItem()
            sep.set_name("dropdown-divider")
            menu.append(sep)
            continue

        label, on_activate, *rest = entry
        sensitive = rest[0] if rest else True
        item = Gtk.MenuItem.new_with_label(label)
        item.set_name("dropdown-option")
        if not sensitive:
            item.set_sensitive(False)
        else:
            item.connect("activate", on_activate)
        menu.append(item)

    return menu


# ========== GlobalMenuDropdowns ==========


class GlobalMenuDropdowns:
    def __init__(self, parent, menu_box=None):
        self.parent = parent
        self._menu_box = menu_box
        self._imac_button = None

        self._global_menu_svc = get_global_menu_service()
        self._has_extracted_menu = False

        self._gtk_menu_buttons: list[Gtk.MenuButton] = []
        self._gtk_menus: list[Gtk.Menu] = []

        # System dropdown (imac button)
        self._system_menu = _make_simple_gtk_menu(
            [
                ("About this PC", lambda _: get_about_window().toggle()),
                None,
                ("System Settings...", lambda _: get_settings_window().toggle()),
                None,
                (
                    "Force Quit",
                    lambda _: exec_shell_command_async(
                        "hyprctl dispatch 'hl.dsp.window.kill()'", lambda *_: None
                    ),
                ),
                None,
                (
                    "Sleep",
                    lambda _: exec_shell_command_async(
                        "systemctl suspend", lambda *_: None
                    ),
                ),
                (
                    "Restart",
                    lambda _: exec_shell_command_async(
                        "systemctl reboot", lambda *_: None
                    ),
                ),
                (
                    "Shut Down",
                    lambda _: exec_shell_command_async("shutdown now", lambda *_: None),
                ),
                None,
                (
                    "Lock Screen",
                    lambda _: exec_shell_command_async(
                        'fabric-cli exec modus "lock_screen.lock()"', lambda *_: None
                    ),
                ),
            ]
        )
        self._system_menu.show_all()

        # Title dropdown (About / Quit app)
        self._title_menu = _make_simple_gtk_menu(
            [
                (
                    f"About {modus_service.current_active_app_name}",
                    lambda _: show_about_app(),
                ),
                (
                    f"Quit {modus_service.current_active_app_name}",
                    lambda _: exec_shell_command_async(
                        "hyprctl dispatch 'hl.dsp.window.close()'", lambda *_: None
                    ),
                ),
            ]
        )
        self._title_menu.show_all()

        # Active window title (clickable)
        self.global_menu_button_title = Gtk.MenuButton(name="global-menu")
        self.global_menu_button_title.set_popup(self._title_menu)
        self.global_menu_button_title.show_all()
        setup_cursor_hover(self.global_menu_button_title, "pointer")

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

    def _get_all_buttons(self):
        buttons = list(self.all_menu_buttons)
        if self._imac_button and self._imac_button not in buttons:
            buttons.append(self._imac_button)
        return buttons

    def _on_active_app_changed(self, _, value):
        logger.info(f"[GlobalMenu] Active app changed: {value}")

        # Rebuild title menu with new app name
        old_menu = self._title_menu
        self._title_menu = _make_simple_gtk_menu(
            [
                (f"About {value}", lambda _: show_about_app()),
                (
                    f"Quit {value}",
                    lambda _: exec_shell_command_async(
                        "hyprctl dispatch 'hl.dsp.window.close()'", lambda *_: None
                    ),
                ),
            ]
        )
        self._title_menu.show_all()
        self.global_menu_button_title.set_popup(self._title_menu)
        if old_menu:
            old_menu.destroy()

        if self._global_menu_svc:
            wm_class = getattr(modus_service, "current_active_wm_class", "")
            self._global_menu_svc.update_active_window(value, wm_class)

    def _on_menu_changed(self, _, menu_items: list):
        self._rebuild_dynamic_menus(menu_items)

    def _cleanup_dynamic(self):
        for btn in self.all_menu_buttons:
            if btn not in (self.global_menu_button_title,):
                try:
                    if btn.get_parent():
                        btn.get_parent().remove(btn)
                    btn.destroy()
                except Exception as e:
                    logger.warning(f"[globalmenu] cleanup failed: {e}")

        for mb in self._gtk_menu_buttons:
            try:
                mb.destroy()
            except Exception:
                pass
        self._gtk_menu_buttons.clear()

        for m in self._gtk_menus:
            try:
                m.destroy()
            except Exception:
                pass
        self._gtk_menus.clear()

    def _rebuild_dynamic_menus(self, menu_items: list):
        logger.info(f"[GlobalMenu] _rebuild_dynamic_menus: {len(menu_items)} items")

        self._cleanup_dynamic()

        top_level = [
            item
            for item in menu_items
            if hasattr(item, "label") and item.label and getattr(item, "visible", True)
        ]

        if not top_level:
            self._has_extracted_menu = False
            self.all_menu_buttons = [self.global_menu_button_title]
        else:
            self._has_extracted_menu = True
            new_buttons = [self.global_menu_button_title]

            for item in top_level:
                children = getattr(item, "children", None) or []
                has_children = getattr(item, "has_submenu", False) or bool(children)

                if not has_children:
                    btn = Button(label=item.label, name="global-menu")
                    setup_cursor_hover(btn, "pointer")
                    btn.connect("clicked", _make_menu_item_click(item.id))
                    new_buttons.append(btn)
                else:
                    menu_btn = Gtk.MenuButton(label=item.label, name="global-menu")
                    menu_btn.get_style_context().add_class("global-menu")
                    setup_cursor_hover(menu_btn, "pointer")

                    gtk_menu = _build_gtk_menu_from_children(children)
                    gtk_menu.show_all()
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
        except Exception as e:
            logger.error(f"[globalmenu] disconnect failed: {e}")

        if self._global_menu_svc:
            try:
                self._global_menu_svc.disconnect_by_func(self._on_menu_changed)
            except Exception as e:
                logger.warning(f"[globalmenu] svc disconnect failed: {e}")

        self._cleanup_dynamic()

        for name in ("_system_menu", "_title_menu"):
            obj = getattr(self, name, None)
            if obj:
                try:
                    obj.destroy()
                except Exception as e:
                    logger.error(f"[globalmenu] destroy failed: {e}")


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
            except Exception as e:
                logger.error(f"[globalmenu] destroy failed: {e}")
        super().destroy()
