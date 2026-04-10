from fabric.hyprland.widgets import HyprlandActiveWindow as ActiveWindow
from fabric.utils import FormattedString, exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

from shared.dialogs.about import About, AboutApp
from shared.window.dropdown import ModusDropdown, dropdown_divider, dropdowns
from shared.window.mousecapture import DropDownMouseCapture
from utils.app_name_resolver import format_window
from utils.roam import modus_service
from utils.utils import setup_cursor_hover


def has_active_window():
    return (
        modus_service.current_active_app_name
        and modus_service.current_active_app_name != "Finder"
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


def create_dropdown_with_capture(dropdown_id, parent, dropdown_children, layer="top"):
    dropdown = ModusDropdown(
        dropdown_id=dropdown_id,
        parent=parent,
        dropdown_children=dropdown_children,
    )
    mouse_capture = DropDownMouseCapture(layer=layer, child_window=dropdown)
    return mouse_capture


def manage_button_style_classes(buttons, active_button=None, style_class="active"):
    for button in buttons:
        if button:  # Check if button exists (some might be None)
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
            dropdown.hide_via_mousecapture()
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


class SystemDropdown(ModusDropdown):
    def __init__(self, parent, **kwargs):
        super().__init__(
            dropdown_id="os-menu",
            parent=parent,
            dropdown_children=[
                dropdown_option(
                    "About this PC", on_clicked=lambda _: About().toggle(_)
                ),
                dropdown_divider("---------------------"),
                dropdown_option(
                    "System Settings...",
                    # TODO: Open Modus own setting
                    # on_click="xdg-open settings",
                ),
                dropdown_divider("---------------------"),
                dropdown_option("Force Quit", "", "hyprctl kill"),
                dropdown_divider("---------------------"),
                dropdown_option("Sleep", "", "systemctl suspend"),
                dropdown_option("Restart", "", "systemctl reboot"),
                dropdown_option("Shut Down", "", "shutdown now"),
                dropdown_divider("---------------------"),
                dropdown_option("Lock Screen", "󰘳     L", "hyprlock"),
            ],
            **kwargs,
        )


class GlobalMenuDropdowns:
    def __init__(self, parent):
        self.parent = parent

        self.system_dropdown = SystemDropdown(parent=parent)
        self.menu_button_dropdown = DropDownMouseCapture(
            layer="top", child_window=self.system_dropdown
        )
        self.menu_button = Button(
            label="Modus",
            name="global-menu",
            on_clicked=lambda _: self.menu_button_dropdown.toggle_mousecapture(),
        )
        self.menu_button_dropdown.child_window.set_pointing_to(self.menu_button)

        self.global_title_menu_about = dropdown_option(
            f"About {modus_service.current_active_app_name}",
            on_clicked=show_about_app,
        )
        self.global_menu_title = create_dropdown_with_capture(
            "global-menu-title",
            parent,
            [self.global_title_menu_about],
        )

        self.global_menu_view = create_dropdown_with_capture(
            "global-menu-view",
            parent,
            [
                dropdown_option(
                    "Enter Full Screen",
                    on_click="hyprctl dispatch fullscreen",
                ),
            ],
        )
        self.global_menu_window = create_dropdown_with_capture(
            "global-menu-window",
            parent,
            [
                dropdown_option(
                    "Zoom In",
                    "󰍉     +",
                    on_click="hyprctl -q keyword cursor:zoom_factor $(hyprctl getoption cursor:zoom_factor -j | jq '.float * 1.1')",
                ),
                dropdown_option(
                    "Zoom Out",
                    "󰍉     -",
                    on_click="hyprctl -q keyword cursor:zoom_factor $(hyprctl getoption cursor:zoom_factor -j | jq '(.float * 0.9) | if . < 1 then 1 else . end')",
                ),
                dropdown_divider("---------------------"),
                dropdown_option(
                    "Move Window to Left",
                    on_click="hyprctl dispatch movewindow l",
                ),
                dropdown_option(
                    "Move Window to Right",
                    on_click="hyprctl dispatch movewindow r",
                ),
                dropdown_option(
                    "Cycle Through Windows",
                    on_click="hyprctl dispatch cyclenext",
                ),
                dropdown_divider("---------------------"),
                dropdown_option("Float", on_click="hyprctl dispatch togglefloating"),
                dropdown_option("Quit", on_click="hyprctl dispatch killactive"),
                dropdown_option("Pseudo", on_click="hyprctl dispatch pseudo"),
                dropdown_option(
                    "Toggle Split", on_click="hyprctl dispatch togglesplit"
                ),
                dropdown_option("Center", on_click="hyprctl dispatch centerwindow"),
                dropdown_option("Group", on_click="hyprctl dispatch togglegroup"),
                dropdown_option(
                    "Pin",
                    on_clicked=lambda _: exec_shell_command_async(
                        "bash ~/.config/scripts/winpin.sh", lambda *_: None
                    ),
                ),
            ],
        )

        self.global_menu_help = create_dropdown_with_capture(
            "global-menu-help",
            parent,
            [
                dropdown_option(
                    "Modus",
                    on_click="xdg-open https://github.com/S4NKALP/Modus/issues",
                ),
                dropdown_divider("---------------------"),
                dropdown_option(
                    "Hyprland Wiki", on_click="xdg-open https://wiki.hyprland.org/"
                ),
            ],
        )

        modus_service.connect(
            "current-active-app-name-changed", self._on_active_app_changed
        )

        self.global_menu_button_title = Button(
            child=ActiveWindow(
                formatter=FormattedString(
                    "{ format_window(win_title, win_class) }",
                    format_window=format_window,
                )
            ),
            name="global-menu",
            on_clicked=self._on_title_button_clicked,
        )

        self.global_menu_title.child_window.set_pointing_to(
            self.global_menu_button_title
        )
        # File, Edit and Go buttons are placeholders - no dropdowns implemented yet
        self.global_menu_button_file = create_menu_button("File")
        self.global_menu_button_edit = create_menu_button("Edit")
        self.global_menu_button_go = create_menu_button("Go")

        self.global_menu_button_view = create_menu_button(
            "View",
            lambda _: self.global_menu_view.toggle_mousecapture(),
        )
        self.global_menu_view.child_window.set_pointing_to(self.global_menu_button_view)
        self.global_menu_button_window = create_menu_button(
            "Window",
            lambda _: self.global_menu_window.toggle_mousecapture(),
        )
        self.global_menu_window.child_window.set_pointing_to(
            self.global_menu_button_window
        )
        self.global_menu_button_help = create_menu_button(
            "Help",
            lambda _: self.global_menu_help.toggle_mousecapture(),
        )
        self.global_menu_help.child_window.set_pointing_to(self.global_menu_button_help)

        self.all_menu_buttons = [
            self.menu_button,
            self.global_menu_button_title,
            self.global_menu_button_file,
            self.global_menu_button_edit,
            self.global_menu_button_view,
            self.global_menu_button_go,
            self.global_menu_button_window,
            self.global_menu_button_help,
        ]

        self.dropdown_button_map = {
            "os-menu": self.menu_button,
            "global-menu-title": self.global_menu_button_title,
            "global-menu-file": self.global_menu_button_file,
            "global-menu-edit": self.global_menu_button_edit,
            "global-menu-view": self.global_menu_button_view,
            "global-menu-go": self.global_menu_button_go,
            "global-menu-window": self.global_menu_button_window,
            "global-menu-help": self.global_menu_button_help,
        }

        modus_service.connect("current-dropdown-changed", self.changed_dropdown)
        modus_service.connect("dropdowns-hide-changed", self.hide_dropdowns)

    def _on_title_button_clicked(self, _):
        if has_active_window():
            self.global_menu_title.toggle_mousecapture()

    def _on_active_app_changed(self, _, value):
        self.global_title_menu_about.set_property("label", f"About {value}")

    def hide_dropdowns(self, *_):
        manage_button_style_classes(self.all_menu_buttons)

    def changed_dropdown(self, _, dropdown_id):
        active_button = self.dropdown_button_map.get(dropdown_id)
        manage_button_style_classes(self.all_menu_buttons, active_button)


class GlobalMenu(Box):
    def __init__(self, parent_window=None, **kwargs):
        if parent_window is None:
            parent_window = kwargs.pop("parent_window", None)

        super().__init__(
            name="globalmenu", orientation="horizontal", spacing=0, **kwargs
        )

        self.dropdown_system = GlobalMenuDropdowns(parent=parent_window)

        self.children = [
            self.dropdown_system.global_menu_button_title,
            self.dropdown_system.global_menu_button_file,
            self.dropdown_system.global_menu_button_edit,
            self.dropdown_system.global_menu_button_view,
            self.dropdown_system.global_menu_button_go,
            self.dropdown_system.global_menu_button_window,
            self.dropdown_system.global_menu_button_help,
        ]

    def show_system_dropdown(self, imac_button):
        self.dropdown_system.menu_button_dropdown.child_window.set_pointing_to(
            imac_button
        )
        mouse_capture = self.dropdown_system.menu_button_dropdown
        mouse_capture.set_child_window_visible(not mouse_capture.is_visible())
