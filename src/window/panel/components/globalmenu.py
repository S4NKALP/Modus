from fabric.hyprland.widgets import HyprlandActiveWindow as ActiveWindow
from fabric.utils import FormattedString, exec_shell_command_async, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

from shared.dialogs.about import AboutApp, get_about_window
from shared.window.dropdown import ModusDropdown, dropdown_divider, dropdowns
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


def create_menu_button(label, on_clicked=None):
    button_kwargs = {
        "label": label,
        "name": "global-menu",
    }

    if on_clicked is not None:
        button_kwargs["on_clicked"] = on_clicked

    button = Button(**button_kwargs)
    setup_cursor_hover(button, "pointer")
    return button


def create_dropdown_with_capture(dropdown_id, parent, dropdown_children):
    dropdown = ModusDropdown(
        dropdown_id=dropdown_id,
        parent=parent,
        dropdown_children=dropdown_children,
    )
    return dropdown


def manage_button_style_classes(buttons, active_button=None, style_class="active"):
    for button in buttons:
        if button:
            button.remove_style_class(style_class)

    if active_button:
        active_button.add_style_class(style_class)


def show_about_app(_=None):
    if not has_active_window():
        return

    app_name = modus_service.current_active_app_name
    wmclass = getattr(modus_service, "current_active_wm_class", "")
    about_window = AboutApp(app_name=app_name, wmclass=wmclass)
    about_window.toggle(None)


def on_click_subthread(button, on_clicked, on_click):
    if on_clicked:
        on_clicked(button)
    else:
        exec_shell_command_async(on_click, lambda *_: None)

    for dropdown in dropdowns:
        if dropdown.is_visible():
            dropdown.hide()
            break


def dropdown_option(
    label: str = "",
    keybind: str = "",
    on_click='echo "ModusPanelDropdown Action"',
    on_clicked=None,
):
    btn = Button(
        child=CenterBox(
            start_children=[
                Label(label=label, h_align="start", name="dropdown-option-label"),
            ],
            end_children=[
                Label(label=keybind, h_align="end", name="dropdown-option-keybind")
            ],
            orientation="horizontal",
            h_align="fill",
            h_expand=True,
            v_expand=True,
        ),
        name="dropdown-option",
        h_align="fill",
        on_clicked=lambda button: on_click_subthread(button, on_clicked, on_click),
        h_expand=True,
        v_expand=True,
    )
    setup_cursor_hover(btn, "pointer")
    return btn


def _make_menu_item_click(item_id):
    """Create a click handler for a menu item."""

    def handler(_, __=None):
        global_menu_svc = get_global_menu_service()
        if global_menu_svc:
            global_menu_svc.click_item(item_id)

    return handler


def _menu_item_to_dropdown(item):
    """Convert a DBusMenuItem to a dropdown_option widget."""
    if item.type == "separator":
        return dropdown_divider("---------------------")

    keybind = item.shortcut if item.shortcut else ""

    return dropdown_option(
        item.label if item.label else "",
        keybind,
        on_click=None,
        on_clicked=_make_menu_item_click(item.id),
    )


class SystemDropdown(ModusDropdown):
    def __init__(self, parent, **kwargs):
        super().__init__(
            dropdown_id="os-menu",
            parent=parent,
            dropdown_children=[
                dropdown_option(
                    "About this PC", on_clicked=lambda _: get_about_window().toggle()
                ),
                dropdown_divider("---------------------"),
                dropdown_option(
                    "System Settings...",
                    on_clicked=lambda _: get_settings_window().toggle(),
                ),
                dropdown_divider("---------------------"),
                dropdown_option(
                    "Force Quit", "", "hyprctl dispatch 'hl.dsp.window.kill()'"
                ),
                dropdown_divider("---------------------"),
                dropdown_option("Sleep", "", "systemctl suspend"),
                dropdown_option("Restart", "", "systemctl reboot"),
                dropdown_option("Shut Down", "", "shutdown now"),
                dropdown_divider("---------------------"),
                dropdown_option(
                    "Lock Screen",
                    "󰘳     L",
                    'fabric-cli exec modus "lock_screen.lock()"',
                ),
            ],
            **kwargs,
        )


class GlobalMenuDropdowns:
    def __init__(self, parent, menu_box=None):
        self.parent = parent
        self._menu_box = menu_box  # The GlobalMenu Box widget to update
        self._imac_button = None

        # Get the global menu service
        self._global_menu_svc = get_global_menu_service()
        self._has_extracted_menu = False

        self.system_dropdown = SystemDropdown(parent=parent)

        self.global_title_menu_about = dropdown_option(
            f"About {modus_service.current_active_app_name}",
            on_clicked=show_about_app,
        )
        self.global_title_menu_quit = dropdown_option(
            f"Quit {modus_service.current_active_app_name}",
            on_click="hyprctl dispatch 'hl.dsp.window.close()'",
        )
        self.global_menu_title = create_dropdown_with_capture(
            "global-menu-title",
            parent,
            [self.global_title_menu_about, self.global_title_menu_quit],
        )

        # Dynamic menu dropdowns (populated from extracted app menus)
        self._dynamic_dropdowns: list[ModusDropdown] = []

        modus_service.connect(
            "current-active-app-name-changed", self._on_active_app_changed
        )

        # Connect to global menu service signals (Moved to the bottom of __init__)

        self.global_menu_button_title = ActiveWindow(
            formatter=FormattedString(
                "{ format_window(win_title, win_class) }",
                format_window=format_window,
            ),
            name="global-menu",
            on_clicked=self._on_title_button_clicked,
        )
        setup_cursor_hover(self.global_menu_button_title, "pointer")

        self.global_menu_title.set_pointing_to(self.global_menu_button_title)

        # Start with only title
        self.all_menu_buttons = [
            self.global_menu_button_title,
        ]

        self.dropdown_button_map = {
            "global-menu-title": self.global_menu_button_title,
            "os-menu": None,
        }

        modus_service.connect("current-dropdown-changed", self.changed_dropdown)
        modus_service.connect("dropdowns-hide-changed", self.hide_dropdowns)

        # Connect to global menu service signals
        if self._global_menu_svc:
            self._global_menu_svc.connect("menu-changed", self._on_menu_changed)

    def set_imac_button(self, button):
        self._imac_button = button
        self.dropdown_button_map["os-menu"] = button

    def _get_all_buttons(self):
        buttons = list(self.all_menu_buttons)
        if self._imac_button and self._imac_button not in buttons:
            buttons.append(self._imac_button)
        return buttons

    def hide_dropdowns(self, *_):
        manage_button_style_classes(self._get_all_buttons())

    def changed_dropdown(self, _, dropdown_id):
        active_button = self.dropdown_button_map.get(dropdown_id)
        manage_button_style_classes(self._get_all_buttons(), active_button)

    def _on_title_button_clicked(self, _):
        if has_active_window():
            self.global_menu_title.toggle()

    def _on_active_app_changed(self, _, value):
        logger.info(f"[GlobalMenu] Active app changed: {value}")
        try:
            self.global_title_menu_about.get_child().get_start_children()[0].set_label(
                f"About {value}"
            )
            self.global_title_menu_quit.get_child().get_start_children()[0].set_label(
                f"Quit {value}"
            )
        except Exception as e:
            logger.warning(
                f"[globalmenu] self.global_title_menu_about.get_child().get_start_childr... failed: {e}"
            )

        # Notify the global menu service about the active window change
        if self._global_menu_svc:
            wm_class = getattr(modus_service, "current_active_wm_class", "")
            logger.info(
                f"[GlobalMenu] Calling update_active_window('{value}', '{wm_class}')"
            )
            self._global_menu_svc.update_active_window(value, wm_class)

    def _on_menu_changed(self, _, menu_items: list):
        """Handle menu changes from the GlobalMenuService."""
        self._rebuild_dynamic_menus(menu_items)

    def _rebuild_dynamic_menus(self, menu_items: list):
        """Rebuild the menu bar buttons based on extracted menu items.

        If the app has a menu bar → show extracted menus (File, Edit, etc.)
        If not → show fallback Hyprland window controls (View, Window, Help)
        """
        logger.info(f"[GlobalMenu] _rebuild_dynamic_menus: {len(menu_items)} items")

        # Destroy old buttons to prevent massive GTK memory leaks
        if hasattr(self, "all_menu_buttons"):
            for btn in self.all_menu_buttons:
                if btn not in (self.global_menu_button_title,):
                    try:
                        if btn.get_parent():
                            btn.get_parent().remove(btn)
                        btn.destroy()
                    except Exception as e:
                        logger.warning(
                            f"[globalmenu] if btn.get_parent(): btn.get_parent().remove(btn) failed: {e}"
                        )

        # Clean up any previous dynamic dropdowns
        for dd in self._dynamic_dropdowns:
            try:
                dd.destroy()
            except Exception as e:
                logger.warning(f"[globalmenu] dd.destroy() failed: {e}")
        self._dynamic_dropdowns.clear()

        # Filter to visible top-level menu items only
        top_level = [
            item
            for item in menu_items
            if hasattr(item, "label") and item.label and getattr(item, "visible", True)
        ]
        logger.info(f"[GlobalMenu] top_level after filter: {len(top_level)} items")

        if not top_level:
            # No extracted menu → show only title button
            self._has_extracted_menu = False
            self.all_menu_buttons = [
                self.global_menu_button_title,
            ]
        else:
            # Has extracted menu → build dynamic buttons
            self._has_extracted_menu = True
            new_buttons = [
                self.global_menu_button_title,
            ]

            for item in top_level:
                is_action = not item.has_submenu and not item.children

                if is_action:
                    # Top-level item without children (e.g., VLC Play/Stop)
                    btn = create_menu_button(
                        item.label,
                        _make_menu_item_click(item.id),
                    )
                    new_buttons.append(btn)
                else:
                    # Build initial children for this dropdown
                    dropdown_children = []
                    for child in item.children if item.children else []:
                        if not getattr(child, "visible", True):
                            continue
                        dropdown_children.append(_menu_item_to_dropdown(child))

                    if not dropdown_children:
                        dropdown_children = [
                            dropdown_option(f"No items in {item.label}")
                        ]

                    dropdown_id = f"global-menu-{item.label.lower()}"
                    dropdown = create_dropdown_with_capture(
                        dropdown_id, self.parent, dropdown_children
                    )

                    btn = create_menu_button(
                        item.label,
                        lambda _, dd=dropdown: dd.toggle(),
                    )
                    dropdown.set_pointing_to(btn)

                    # Dynamically fetch submenu on hover
                    def make_on_enter(menu_item, dd):
                        def on_enter(widget, event):
                            if not menu_item.has_submenu:
                                return False
                            svc = get_global_menu_service()
                            if svc:
                                svc.about_to_show(menu_item.id)
                                new_menu = svc.refresh_menu_sync()
                                if new_menu:
                                    # find the updated item
                                    new_item = next(
                                        (i for i in new_menu if i.id == menu_item.id),
                                        None,
                                    )
                                    if new_item:
                                        children = []
                                        for child in (
                                            new_item.children
                                            if new_item.children
                                            else []
                                        ):
                                            if not getattr(child, "visible", True):
                                                continue
                                            children.append(
                                                _menu_item_to_dropdown(child)
                                            )
                                        if not children:
                                            children = [
                                                dropdown_option(
                                                    f"No items in {new_item.label}"
                                                )
                                            ]
                                        dd.dropdown.children = children
                            return False

                        return on_enter

                    btn.connect("enter-notify-event", make_on_enter(item, dropdown))

                    self._dynamic_dropdowns.append(dropdown)
                    self.dropdown_button_map[dropdown_id] = btn
                    new_buttons.append(btn)

            self.all_menu_buttons = new_buttons

        # Update the panel (the actual GTK Box widget)
        if self._menu_box is not None:
            self._menu_box.children = self.all_menu_buttons

    def destroy(self):
        """Clean up all dropdowns and signal connections"""
        try:
            modus_service.disconnect_by_func(self._on_active_app_changed)
            modus_service.disconnect_by_func(self.changed_dropdown)
            modus_service.disconnect_by_func(self.hide_dropdowns)
        except Exception as e:
            logger.error(f"An error occurred: {e}")

        # Disconnect global menu service
        if self._global_menu_svc:
            try:
                self._global_menu_svc.disconnect_by_func(self._on_menu_changed)
            except Exception as e:
                logger.warning(
                    f"[globalmenu] self._global_menu_svc.disconnect_by_func(self._on_menu_ch... failed: {e}"
                )

        # Destroy dynamic dropdowns
        for dd in self._dynamic_dropdowns:
            try:
                dd.destroy()
            except Exception as e:
                logger.error(f"An error occurred: {e}")
        self._dynamic_dropdowns.clear()

        # Destroy static dropdown captures
        dropdown_captures = [
            getattr(self, "system_dropdown", None),
            getattr(self, "global_menu_title", None),
        ]
        for capture in dropdown_captures:
            try:
                if capture and hasattr(capture, "destroy"):
                    capture.destroy()
            except Exception as e:
                logger.error(f"An error occurred: {e}")

        super().destroy()


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
        self.dropdown_system.system_dropdown.set_pointing_to(imac_button)
        self.dropdown_system.system_dropdown.toggle()

    def destroy(self):
        """Clean up the global menu and its dropdowns"""
        if hasattr(self, "dropdown_system") and self.dropdown_system:
            try:
                self.dropdown_system.destroy()
            except Exception as e:
                logger.error(f"An error occurred: {e}")
        super().destroy()
