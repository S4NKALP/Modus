from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.hyprland.widgets import HyprlandActiveWindow
from utils.wayland import WaylandWindow
from gi.repository import Gtk, GLib
from .menu_contents import get_default_menu_contents, get_app_specific_menu_contents
from .menu_actions import MenuActionHandler


class DropdownWindow(WaylandWindow):
    def __init__(self, x=0, y=0, parent_menubar=None, **kwargs):
        super().__init__(
            name="dropdown-window",
            title="Menu Dropdown",
            layer="overlay",  
            anchor="top left",  
            exclusivity="none",  
            margin=f"{y}px 0px 0px {x}px",  
            visible=False,  
            all_visible=True,  
            **kwargs
        )

        # Store reference to parent menubar for closing dropdown
        self.parent_menubar = parent_menubar

        self.content_box = Box(
            name="dropdown-content",
            orientation="v",
            spacing=2,
        )
        self.add(self.content_box)

        self.connect("enter-notify-event", self.on_mouse_enter)
        self.connect("leave-notify-event", self.on_mouse_leave)

        self.auto_close_timer = None

    def on_mouse_enter(self, widget, event):
        # Only handle if the event is for the main dropdown window, not child widgets
        if event.detail != 2:  # 2 = Gdk.NotifyType.INFERIOR (child widget)
            # Cancel auto-close timer when mouse enters
            if self.auto_close_timer:
                GLib.source_remove(self.auto_close_timer)
                self.auto_close_timer = None
        return False

    def on_mouse_leave(self, widget, event):
        # Only handle if actually leaving the dropdown window, not entering child widgets
        if event.detail != 2:  # 2 = Gdk.NotifyType.INFERIOR (child widget)
            # Start auto-close timer when mouse leaves
            if not self.auto_close_timer:
                self.auto_close_timer = GLib.timeout_add(300, self.auto_close_callback)  # 300ms delay
        return False

    def auto_close_callback(self):
        if self.parent_menubar:
            self.parent_menubar.hide_dropdown()
        self.auto_close_timer = None
        return False  


class MenuBar(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="menubar",
            orientation="h",
            spacing=0,
            **kwargs,
        )

        self.active_window = HyprlandActiveWindow(name="hyprland-window")
        self.active_window.connect("window-activated", self.on_window_changed)

        self.current_window_class = None
        self.current_window_title = None

        self.current_dropdown = None
        self.dropdown_window = None

        self.action_handler = MenuActionHandler()

        # Menu items in macOS style order (excluding the first item which will be dynamic)
        self.static_menu_items = [
            "File",
            "Edit",
            "View",
            "Go",
            "Window",
            "Help"
        ]

        self.menu_contents = get_default_menu_contents()

        self.app_button = Button(
            name="menubar-button",
            child=Label(
                name="activewindow-label",
                label="Hyprland"
            ),
        )
        self.app_button.connect("clicked", lambda widget: self.toggle_dropdown("Hyprland", widget))
        self.add(self.app_button)

        self.menu_buttons = []
        for item in self.static_menu_items:
            button = Button(
                name="menubar-button",
                child=Label(
                    name="menubar-label",
                    label=item
                ),
            )

            button.connect("clicked", lambda widget, menu_item=item: self.on_menu_button_clicked(menu_item, widget))
            self.menu_buttons.append(button)
            self.add(button)

        self.update_menu_button_states()

        self.show_all()

    def get_button_for_item(self, menu_item):
        if menu_item == "Hyprland":
            return self.app_button

        for i, item in enumerate(self.static_menu_items):
            if item == menu_item:
                return self.menu_buttons[i]
        return None

    def on_menu_button_clicked(self, menu_item, button):
        # Check if we should allow this menu to be opened
        if not self.should_menu_be_active(menu_item):
            return

        # Menu is allowed, proceed with normal toggle
        self.toggle_dropdown(menu_item, button)

    def should_menu_be_active(self, menu_item):
        # These menus should only work when there's an active window
        context_dependent_menus = ["File", "Edit", "View", "Go"]

        if menu_item in context_dependent_menus:
            # Only allow if there's an active window (not just showing "Hyprland")
            has_active_window = (
                self.current_window_title and
                self.current_window_title.strip() and
                self.app_button.get_child().get_label() != "Hyprland"
            )
            return has_active_window

        # Window and Help menus are always available
        return True

    def update_menu_button_states(self):
        context_dependent_menus = ["File", "Edit", "View", "Go"]

        for i, menu_item in enumerate(self.static_menu_items):
            if menu_item in context_dependent_menus:
                button = self.menu_buttons[i]
                is_active = self.should_menu_be_active(menu_item)

                # Keep buttons sensitive for hovering, but add visual styling for inactive state
                # Don't use set_sensitive(False) as it prevents hovering
                if is_active:
                    button.get_style_context().remove_class("inactive")
                else:
                    button.get_style_context().add_class("inactive")

    def toggle_dropdown(self, menu_item, button):
        # If same menu is clicked and dropdown is visible, hide it
        if (self.current_dropdown == menu_item and
            self.dropdown_window and
            self.dropdown_window.get_visible()):
            self.hide_dropdown()
            return

        # (show_dropdown will handle hiding the previous one)
        self.show_dropdown(menu_item, button)

    def show_dropdown(self, menu_item, button):
        # Hide existing dropdown if any and wait for it to be completely hidden
        if self.dropdown_window:
            self.dropdown_window.set_visible(False)
            self.dropdown_window.destroy()
            self.dropdown_window = None
            # Wait a short moment to ensure the previous dropdown is completely gone
            GLib.timeout_add(150, self._create_and_show_dropdown, menu_item, button)
        else:
            # No existing dropdown, show immediately
            self._create_and_show_dropdown(menu_item, button)

    def _create_and_show_dropdown(self, menu_item, button):
        # Calculate position first
        x, y = self.calculate_dropdown_position(button)

        # Create new dropdown window at the calculated position
        self.dropdown_window = DropdownWindow(x=x, y=y, parent_menubar=self)

        # Get menu items for this menu
        menu_items = self.menu_contents.get(menu_item, [])

        # Add menu items to dropdown
        for item in menu_items:
            if item == "---":
                # Add separator
                separator = Box(
                    name="menu-separator",
                    size=(150, 1),
                    style="background-color: #444; margin: 2px 0;"
                )
                self.dropdown_window.content_box.add(separator)
            else:
                # Add menu item button
                menu_button = Button(
                    name="dropdown-item",
                    child=Label(
                        name="dropdown-label",
                        label=item,
                        h_align="start"  # Align text to the left
                    ),
                    on_clicked=lambda *_, action=item: self.on_menu_action(action)
                )
                self.dropdown_window.content_box.add(menu_button)

        self.dropdown_window.set_size_request(150, -1)

        self.current_dropdown = menu_item
        self.dropdown_window.set_visible(True)

        return False

    def calculate_dropdown_position(self, button):
        # Get button allocation
        allocation = button.get_allocation()

        print(f"Button allocation: x={allocation.x}, y={allocation.y}, width={allocation.width}, height={allocation.height}")

        # Use the exact button position for perfect alignment
        dropdown_x = allocation.x
        dropdown_y = allocation.y + 3  # 3px gap below button

        print(f"Perfect dropdown position: x={dropdown_x}, y={dropdown_y}")

        return dropdown_x, dropdown_y

    def hide_dropdown(self):
        if self.dropdown_window:
            self.dropdown_window.set_visible(False)
            self.dropdown_window.destroy()
            self.dropdown_window = None
        self.current_dropdown = None

    def on_menu_action(self, action):
        # Hide dropdown after action
        self.hide_dropdown()

        # Handle window management actions
        self.execute_menu_action(action)

    def execute_menu_action(self, action):
        self.action_handler.execute_action(action)

    def on_window_changed(self, widget, window_class, window_title):
        self.current_window_class = window_class
        self.current_window_title = window_title

        # Update the first button label and menu contents
        if window_title and window_title.strip():
            # Show the window title/app name when there's an active window
            display_name = window_class if window_class else window_title
            # Capitalize the first letter
            display_name = display_name.capitalize() if display_name else "Hyprland"
            self.app_button.get_child().set_label(display_name)

            # Update the app menu contents dynamically
            self.update_app_menu(display_name)
        else:
            # Show "Hyprland" when no active window
            self.app_button.get_child().set_label("Hyprland")
            self.update_app_menu("Hyprland")

        # Update menu button states based on new context
        self.update_menu_button_states()

    def update_app_menu(self, app_name):
        # Get app-specific menu contents (includes app-specific overrides if available)
        self.menu_contents = get_app_specific_menu_contents(app_name)

    def show_system_dropdown(self, button):
        # If same system dropdown is open, hide it (toggle behavior)
        if (self.current_dropdown == "System" and
            self.dropdown_window and
            self.dropdown_window.get_visible()):
            self.hide_dropdown()
            return

        # Hide existing dropdown if any and show system dropdown
        if self.dropdown_window:
            self.dropdown_window.set_visible(False)
            self.dropdown_window.destroy()
            self.dropdown_window = None
            # Wait a short moment to ensure the previous dropdown is completely gone
            GLib.timeout_add(150, self._create_and_show_system_dropdown, button)
        else:
            # No existing dropdown, show immediately
            self._create_and_show_system_dropdown(button)

    def _create_and_show_system_dropdown(self, button):
        # Calculate position first
        x, y = self.calculate_dropdown_position(button)

        # Create new dropdown window at the calculated position
        self.dropdown_window = DropdownWindow(x=x, y=y, parent_menubar=self)

        # System menu items
        system_menu_items = [
            "About This PC",
            "---",
            "Force Quit",
            "---",
            "Shutdown",
            "Restart",
            "Sleep",
            "Lock"
        ]

        # Add menu items to dropdown
        for item in system_menu_items:
            if item == "---":
                # Add separator
                separator = Box(
                    name="menu-separator",
                    size=(150, 1),
                    style="background-color: #444; margin: 2px 0;"
                )
                self.dropdown_window.content_box.add(separator)
            else:
                # Add menu item button
                menu_button = Button(
                    name="dropdown-item",
                    child=Label(
                        name="dropdown-label",
                        label=item,
                        h_align="start"  # Align text to the left
                    ),
                    on_clicked=lambda *_, action=item: self.on_menu_action(action)
                )
                self.dropdown_window.content_box.add(menu_button)

        # Set dropdown window size
        self.dropdown_window.set_size_request(150, -1)

        # Show the dropdown without animations
        self.current_dropdown = "System"
        # Use set_visible(True) for immediate display without animations
        self.dropdown_window.set_visible(True)

        # Return False to stop the timeout
        return False
