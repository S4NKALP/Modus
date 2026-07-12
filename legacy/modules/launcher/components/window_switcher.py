import subprocess
import json
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.image import Image
from fabric.utils import idle_add, remove_handler, exec_shell_command_async
from utils import IconResolver
from gi.repository import GLib, Gdk, Gtk
import utils.icons as icons
import config.data as data

class WindowSwitcher(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="window-switcher",
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.launcher = kwargs["launcher"]
        self.selected_index = -1  # Track the selected item index
        self.icon_resolver = IconResolver()

        self.viewport = Box(name="viewport", spacing=4, orientation="v")
        self.search_entry = Entry(
            name="search-entry",
            placeholder="Search Windows...",
            h_expand=True,
            notify_text=lambda entry, *_: self.handle_search(entry.get_text()),
            on_activate=lambda entry, *_: self.handle_search(entry.get_text()),
            on_key_press_event=self.on_entry_key_press,
        )
        self.search_entry.props.xalign = 0.5
        self.scrolled_window = ScrolledWindow(
            name="scrolled-window",
            spacing=10,
            min_content_size=(450, 305),
            max_content_size=(450, 305),
            child=self.viewport,
        )

        self.header_box = Box(
            name="header_box",
            spacing=10,
            orientation="h",
            children=[
                self.search_entry,
            ],
        )

        self.window_switcher_box = Box(
            name="window-switcher-box",
            spacing=10,
            h_expand=True,
            orientation="v",
            children=[
                self.header_box,
                self.scrolled_window,
            ],
        )

        self.add(self.window_switcher_box)
        self.show_all()

    def close_switcher(self):
        """Close the window switcher"""
        self.viewport.hide()
        self.selected_index = -1  # Reset selection
        self.launcher.close()

    def open_switcher(self):
        """Open the window switcher and refresh windows"""
        self.refresh_windows()
        self.search_entry.set_text("")
        self.search_entry.grab_focus()
        self.viewport.show()

    def refresh_windows(self):
        """Get Hyprland windows and populate the viewport"""
        remove_handler(self._arranger_handler) if hasattr(self, '_arranger_handler') else None
        self.viewport.children = []
        self.selected_index = -1  # Clear selection when viewport changes

        # Get Hyprland windows
        windows = self.get_hyprland_windows()
        if not windows:
            # Create a container box to better center the message
            container = Box(
                name="no-windows-container",
                orientation="v",
                h_align="center",
                v_align="center",
                h_expand=True,
                v_expand=True
            )
            
            # Show a message if no windows
            label = Label(
                name="no-windows",
                markup=icons.window,
                h_align="center",
                v_align="center",
            )
            
            container.add(label)
            
            self.viewport.add(container)
            return

        # Add window slots to viewport
        for window in windows:
            self.viewport.add(self.create_window_slot(window))

    def get_hyprland_windows(self):
        """Get list of windows from Hyprland"""
        try:
            # Get clients info from Hyprland
            result = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True,
                text=True,
                check=True
            )
            clients = json.loads(result.stdout)
            
            # Filter out special windows and sort by workspace
            windows = []
            for client in clients:
                if client.get("class") and not client.get("class").startswith("special"):
                    windows.append(client)
            
            # Sort windows by workspace number
            windows.sort(key=lambda x: int(x.get("workspace", {}).get("id", 0)))
            return windows
            
        except Exception as e:
            print(f"Error getting Hyprland windows: {e}")
            return []

    def create_window_slot(self, window):
        """Create a button slot for a window"""
        # Get window title or class as fallback
        title = window.get("title", window.get("class", "Unknown"))
        workspace = window.get("workspace", {}).get("id", 0)
        window_class = window.get("class", "")
        
        # Get window icon using IconResolver
        icon = self.get_window_icon(window_class)
        
        # Create the button with window info
        button = Button(
            name="slot-button",
            child=Box(
                name="window-slot-box",
                orientation="h",
                spacing=10,
                children=[
                    Image(
                        name="window-icon",
                        pixbuf=icon,
                        h_align="start",
                    ),
                    Label(
                        name="workspace-label",
                        label=f"Workspace {workspace}",
                        h_align="start",
                    ),
                    Label(
                        name="window-title",
                        label=title,
                        ellipsization="end",
                        v_align="center",
                        h_align="center",
                    ),
                ],
            ),
            on_clicked=lambda *_: self.focus_window(window.get("address")),
            on_key_press_event=lambda btn, event, addr=window.get("address"): self.on_slot_key_press(btn, event, addr),
        )
        return button

    def get_window_icon(self, window_class):
        """Get the appropriate icon for a window class using IconResolver"""
        try:
            # Try to get icon from IconResolver
            icon = self.icon_resolver.get_icon_pixbuf(window_class, size=24)
            if icon:
                return icon
        except Exception as e:
            print(f"Error resolving icon for {window_class}: {e}")
            
        # Fallback to default window icon if resolution fails
        return icons.window

    def focus_window(self, address):
        """Focus a window by its address"""
        try:
            subprocess.run(
                ["hyprctl", "dispatch", "focuswindow", f"address:{address}"],
                check=True
            )
            self.close_switcher()
        except Exception as e:
            print(f"Error focusing window: {e}")

    def handle_search(self, query):
        """Handle search input"""
        if not query:
            self.refresh_windows()
            return

        # Filter windows based on search query
        windows = self.get_hyprland_windows()
        filtered_windows = [
            window for window in windows
            if query.lower() in window.get("title", "").lower() or
               query.lower() in window.get("class", "").lower()
        ]

        # Update viewport with filtered results
        self.viewport.children = []
        self.selected_index = -1

        for window in filtered_windows:
            self.viewport.add(self.create_window_slot(window))

    def on_entry_key_press(self, widget, event):
        """Handle key presses on the search entry"""
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.selected_index != -1:
                children = self.viewport.get_children()
                if 0 <= self.selected_index < len(children):
                    children[self.selected_index].clicked()
            return True
        elif event.keyval == Gdk.KEY_Down:
            self.move_selection(1)
            return True
        elif event.keyval == Gdk.KEY_Up:
            self.move_selection(-1)
            return True
        elif event.keyval == Gdk.KEY_Escape:
            self.close_switcher()
            return True
        return False

    def on_slot_key_press(self, button, event, address):
        """Handle key presses on window slots"""
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.focus_window(address)
            return True
        elif event.keyval == Gdk.KEY_Escape:
            self.close_switcher()
            return True
        return False

    def move_selection(self, direction):
        """Move the selection up or down"""
        children = self.viewport.get_children()
        if not children:
            return

        new_index = self.selected_index + direction
        if 0 <= new_index < len(children):
            self.update_selection(new_index)

    def update_selection(self, new_index):
        """Update the selected item"""
        # Unselect current
        if self.selected_index != -1 and self.selected_index < len(self.viewport.get_children()):
            current_button = self.viewport.get_children()[self.selected_index]
            current_button.get_style_context().remove_class("selected")
        
        # Select new
        if new_index != -1 and new_index < len(self.viewport.get_children()):
            new_button = self.viewport.get_children()[new_index]
            new_button.get_style_context().add_class("selected")
            self.selected_index = new_index
            self.scroll_to_selected(new_button)
        else:
            self.selected_index = -1

    def scroll_to_selected(self, button):
        """Scroll to ensure the selected button is visible"""
        def scroll():
            adj = self.scrolled_window.get_vadjustment()
            alloc = button.get_allocation()
            if alloc.height == 0:
                return False  # Retry if allocation isn't ready

            y = alloc.y
            height = alloc.height
            page_size = adj.get_page_size()
            current_value = adj.get_value()

            # Calculate visible boundaries
            visible_top = current_value
            visible_bottom = current_value + page_size

            if y < visible_top:
                # Item above viewport - align to top
                adj.set_value(y)
            elif y + height > visible_bottom:
                # Item below viewport - align to bottom
                new_value = y + height - page_size
                adj.set_value(new_value)
            # No action if already fully visible
            return False
        GLib.idle_add(scroll) 