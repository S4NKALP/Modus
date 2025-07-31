import os
import subprocess

from fabric.hyprland.widgets import HyprlandActiveWindow as ActiveWindow
from fabric.utils import FormattedString
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

from modules.about import About
from utils.roam import modus_service
from widgets.dropdown import ModusDropdown, dropdown_divider
from widgets.mousecapture import DropDownMouseCapture


class AppName:
    def __init__(self, path="/usr/share/applications"):
        self.files = os.listdir(path) if os.path.exists(path) else []
        self.path = path

    def get_app_name(self, wmclass):
        desktop_file = ""
        for f in self.files:
            if f.startswith(wmclass + ".desktop"):
                desktop_file = f

        desktop_app_name = wmclass

        if desktop_file == "":
            return wmclass
        try:
            with open(os.path.join(self.path, desktop_file), "r") as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith("Name="):
                        desktop_app_name = line.split("=")[1].strip()
                        break
        except:
            return wmclass
        return desktop_app_name

    def format_app_name(self, title, wmclass, update=False):
        name = wmclass
        if name == "":
            name = title

        # Try to get the proper app name from desktop file
        name = self.get_app_name(wmclass=wmclass)

        # Smart title formatting (capitalize first letter)
        name = str(name).title()
        if "." in name:
            name = name.split(".")[-1]

        if update:
            modus_service.current_active_app_name = name
        return name


app_name_class = AppName()


def format_window(title, wmclass):
    name = app_name_class.format_app_name(title, wmclass, True)
    if not name or name == "":
        return "Desktop"
    return name


def dropdown_option(
    label: str = "",
    keybind: str = "",
    on_click='echo "ModusPanelDropdown Action"',
    on_clicked=None,
):
    def on_click_subthread(button):
        # Execute the action first
        if on_clicked:
            on_clicked(button)
        else:
            subprocess.Popen(
                f"nohup {on_click} &",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Hide dropdown by finding the current visible dropdown and calling its hide method
        from widgets.dropdown import dropdowns

        for dropdown in dropdowns:
            if dropdown.is_visible() and hasattr(dropdown, "hide_via_mousecapture"):
                dropdown.hide_via_mousecapture()
                break

    return Button(
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
        on_clicked=on_click_subthread,
        h_expand=True,
        v_expand=True,
    )


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
                dropdown_option("Restart...", "", "systemctl reboot"),
                dropdown_option("Shut Down...", "", "shutdown now"),
                dropdown_divider("---------------------"),
                dropdown_option("Lock Screen", "󰘳     L", "hyprlock"),
            ],
            **kwargs,
        )


class MenuBarDropdowns:
    def __init__(self, parent):
        self.parent = parent

        # System dropdown
        self.system_dropdown = SystemDropdown(parent=parent)
        self.menu_button_dropdown = DropDownMouseCapture(
            layer="bottom", child_window=self.system_dropdown
        )
        self.menu_button = Button(
            label="Modus",
            name="menu-button",
            style_classes="button",
            on_clicked=lambda _: self.menu_button_dropdown.toggle_mousecapture(),
        )
        self.menu_button_dropdown.child_window.set_pointing_to(self.menu_button)

        # Global menu dropdowns
        self.global_title_menu_about = dropdown_option(
            f"About {modus_service.current_active_app_name}"
        )
        self.global_menu_title = DropDownMouseCapture(
            layer="bottom",
            child_window=ModusDropdown(
                dropdown_id="global-menu-title",
                parent=parent,
                dropdown_children=[self.global_title_menu_about],
            ),
        )

        self.global_menu_file = None
        self.global_menu_edit = None
        self.global_menu_view = DropDownMouseCapture(
            layer="bottom",
            child_window=ModusDropdown(
                dropdown_id="global-menu-view",
                parent=parent,
                dropdown_children=[
                    dropdown_option(
                        "Enter Full Screen",
                        on_click="hyprctl dispatch fullscreen",
                    ),
                ],
            ),
        )
        self.global_menu_go = None
        self.global_menu_window = DropDownMouseCapture(
            layer="bottom",
            child_window=ModusDropdown(
                dropdown_id="global-menu-window",
                parent=parent,
                dropdown_children=[
                    dropdown_option(
                        "Zoom",
                        on_clicked=lambda _: subprocess.run(
                            "bash ~/.config/scripts/zoomer.sh", shell=True
                        ),
                    ),
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
                    dropdown_option(
                        "Float", on_click="hyprctl dispatch togglefloating"
                    ),
                    dropdown_option("Quit", on_click="hyprctl dispatch killactive"),
                    dropdown_option("Pseudo", on_click="hyprctl dispatch pseudo"),
                    dropdown_option(
                        "Toggle Split", on_click="hyprctl dispatch togglesplit"
                    ),
                    dropdown_option("Center", on_click="hyprctl dispatch centerwindow"),
                    dropdown_option("Group", on_click="hyprctl dispatch togglegroup"),
                    dropdown_option(
                        "Pin",
                        on_clicked=lambda _: subprocess.run(
                            "bash ~/.config/scripts/winpin.sh", shell=True
                        ),
                    ),
                ],
            ),
        )

        self.global_menu_help = DropDownMouseCapture(
            layer="bottom",
            child_window=ModusDropdown(
                dropdown_id="global-menu-help",
                parent=parent,
                dropdown_children=[
                    dropdown_option(
                        "Modus",
                        on_click="xdg-open https://github.com/S4NKALP/Modus/issues",
                    ),
                    dropdown_divider("---------------------"),
                    dropdown_option(
                        "Hyprland Wiki", on_click="xdg-open https://wiki.hyprland.org/"
                    ),
                ],
            ),
        )

        # Create menu buttons
        modus_service.connect(
            "current-active-app-name-changed",
            lambda _, value: self.global_title_menu_about.set_property(
                "label", f"About {value}"
            ),
        )
        self.global_menu_button_title = Button(
            child=ActiveWindow(
                formatter=FormattedString(
                    "{ format_window('None', 'Hyprland') if win_title == '' and win_class == '' else format_window(win_title, win_class) }",
                    format_window=format_window,
                )
            ),
            name="global-title-button",
            style_classes="button",
            on_clicked=lambda _: self.global_menu_title.toggle_mousecapture(),
        )
        self.global_menu_title.child_window.set_pointing_to(
            self.global_menu_button_title
        )

        self.global_menu_button_file = Button(
            label="File", name="global-menu-button-file", style_classes="button"
        )
        self.global_menu_button_edit = Button(
            label="Edit", name="global-menu-button-edit", style_classes="button"
        )
        self.global_menu_button_view = Button(
            label="View",
            name="global-menu-button-view",
            style_classes="button",
            on_clicked=lambda _: self.global_menu_view.toggle_mousecapture(),
        )
        self.global_menu_view.child_window.set_pointing_to(self.global_menu_button_view)
        self.global_menu_button_go = Button(
            label="Go", name="global-menu-button-go", style_classes="button"
        )
        self.global_menu_button_window = Button(
            label="Window",
            name="global-menu-button-window",
            style_classes="button",
            on_clicked=lambda _: self.global_menu_window.toggle_mousecapture(),
        )
        self.global_menu_window.child_window.set_pointing_to(
            self.global_menu_button_window
        )
        self.global_menu_button_help = Button(
            label="Help",
            name="global-menu-button-help",
            style_classes="button",
            on_clicked=lambda _: self.global_menu_help.toggle_mousecapture(),
        )
        self.global_menu_help.child_window.set_pointing_to(self.global_menu_button_help)

        modus_service.connect("current-dropdown-changed", self.changed_dropdown)
        modus_service.connect("dropdowns-hide-changed", self.hide_dropdowns)

    def hide_dropdowns(self, *_):
        self.menu_button.remove_style_class("active")
        self.global_menu_button_edit.remove_style_class("active")
        self.global_menu_button_file.remove_style_class("active")
        self.global_menu_button_go.remove_style_class("active")
        self.global_menu_button_help.remove_style_class("active")
        self.global_menu_button_title.remove_style_class("active")
        self.global_menu_button_view.remove_style_class("active")
        self.global_menu_button_window.remove_style_class("active")

    def changed_dropdown(self, _, dropdown_id):
        self.hide_dropdowns(_, True)
        match dropdown_id:
            case "os-menu":
                self.menu_button.add_style_class("active")
            case "global-menu-edit":
                self.global_menu_button_edit.add_style_class("active")
            case "global-menu-file":
                self.global_menu_button_file.add_style_class("active")
            case "global-menu-go":
                self.global_menu_button_go.add_style_class("active")
            case "global-menu-help":
                self.global_menu_button_help.add_style_class("active")
            case "global-menu-title":
                self.global_menu_button_title.add_style_class("active")
            case "global-menu-view":
                self.global_menu_button_view.add_style_class("active")
            case "global-menu-window":
                self.global_menu_button_window.add_style_class("active")
            case _:
                pass


class MenuBar(Box):
    """Main MenuBar widget that contains all menu buttons"""

    def __init__(self, parent_window=None, **kwargs):
        # Extract parent_window from kwargs if not provided as parameter
        if parent_window is None:
            parent_window = kwargs.pop("parent_window", None)

        super().__init__(name="menubar", orientation="horizontal", spacing=0, **kwargs)

        # Create the dropdown system
        self.dropdown_system = MenuBarDropdowns(parent=parent_window)

        # Add all the menu buttons to the menubar
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
        if mouse_capture.is_visible():
            mouse_capture.set_child_window_visible(False)
        else:
            mouse_capture.set_child_window_visible(True)
