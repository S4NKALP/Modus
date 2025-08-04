"""
Enhanced System Tray Icon Handling

This module provides enhanced icon loading capabilities for system tray items,
including fallback mechanisms for file paths and common icon locations.
It also adds dropdown menu functionality for system tray items.
"""

import os

from gi.repository import GdkPixbuf, Gtk
from fabric.widgets.label import Label

from fabric.system_tray.widgets import SystemTrayItem
from widgets.dropdown import ModusDropdown, dropdown_divider
from widgets.mousecapture import DropDownMouseCapture

# FIX: the tooltip should show application names instead of unknown


def patched_do_update_properties(self, *_):
    # Try default GTK theme first
    icon_name = self._item.icon_name
    attention_icon_name = self._item.attention_icon_name

    if self._item.status == "NeedsAttention" and attention_icon_name:
        preferred_icon_name = attention_icon_name
    else:
        preferred_icon_name = icon_name

    # Try to load from default GTK theme
    if preferred_icon_name:
        try:
            default_theme = Gtk.IconTheme.get_default()
            if default_theme.has_icon(preferred_icon_name):
                pixbuf = default_theme.load_icon(
                    preferred_icon_name, self._icon_size, Gtk.IconLookupFlags.FORCE_SIZE
                )
                if pixbuf:
                    self._image.set_from_pixbuf(pixbuf)
                    # Set tooltip
                    tooltip = self._item.tooltip
                    self.set_tooltip_markup(
                        tooltip.description or tooltip.title or self._item.title.title()
                        if self._item.title
                        else "Unknown"
                    )
                    return
        except:
            pass

        # Enhanced fallback handling for file paths
        if preferred_icon_name and self._try_load_icon_from_path(preferred_icon_name):
            return

    # Fallback to original implementation
    original_do_update_properties(self, *_)


def _try_load_icon_from_path(self, icon_path):
    try:
        # Check if it's a file path and handle it directly
        if os.path.isabs(icon_path) or "/" in icon_path:
            # Try to load as SVG from the original path if it exists
            if os.path.exists(icon_path):
                if icon_path.lower().endswith(".svg"):
                    # Load SVG directly
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        icon_path, self._icon_size, self._icon_size
                    )
                    if pixbuf:
                        self._image.set_from_pixbuf(pixbuf)
                        self._set_tooltip()
                        return True
                else:
                    # Load other image formats
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        icon_path, self._icon_size, self._icon_size
                    )
                    if pixbuf:
                        self._image.set_from_pixbuf(pixbuf)
                        self._set_tooltip()
                        return True

            # If it's a file path, try to extract just the filename for theme lookup
            filename = os.path.basename(icon_path)
            if filename:
                # Remove extension for theme lookup
                name_without_ext = os.path.splitext(filename)[0]
                default_theme = Gtk.IconTheme.get_default()

                # Try filename without extension
                if default_theme.has_icon(name_without_ext):
                    pixbuf = default_theme.load_icon(
                        name_without_ext,
                        self._icon_size,
                        Gtk.IconLookupFlags.FORCE_SIZE,
                    )
                    if pixbuf:
                        self._image.set_from_pixbuf(pixbuf)
                        self._set_tooltip()
                        return True

                # Try full filename
                if default_theme.has_icon(filename):
                    pixbuf = default_theme.load_icon(
                        filename, self._icon_size, Gtk.IconLookupFlags.FORCE_SIZE
                    )
                    if pixbuf:
                        self._image.set_from_pixbuf(pixbuf)
                        self._set_tooltip()
                        return True

            # If it looks like a file path but doesn't exist, try common icon locations
            if os.path.isabs(icon_path):
                common_icon_dirs = [
                    "/usr/share/icons",
                    "/usr/share/pixmaps",
                    "/usr/local/share/icons",
                    "/usr/local/share/pixmaps",
                    os.path.expanduser("~/.local/share/icons"),
                    os.path.expanduser("~/.icons"),
                ]

                filename = os.path.basename(icon_path)
                for icon_dir in common_icon_dirs:
                    potential_path = os.path.join(icon_dir, filename)
                    if os.path.exists(potential_path):
                        try:
                            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                                potential_path, self._icon_size, self._icon_size
                            )
                            if pixbuf:
                                self._image.set_from_pixbuf(pixbuf)
                                self._set_tooltip()
                                return True
                        except:
                            continue

    except Exception:
        pass

    return False


def _set_tooltip(self):
    tooltip = self._item.tooltip
    self.set_tooltip_markup(
        tooltip.description or tooltip.title or self._item.title.title()
        if self._item.title
        else "Unknown"
    )


def dropdown_option(label: str = "", on_click=None):
    """Create a dropdown option for system tray items"""
    from fabric.widgets.button import Button
    from fabric.widgets.centerbox import CenterBox

    def on_click_handler(_):
        if on_click:
            on_click()
        # Hide dropdown after action
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
            orientation="horizontal",
            h_align="fill",
            h_expand=True,
            v_expand=True,
        ),
        name="dropdown-option",
        h_align="fill",
        on_clicked=on_click_handler,
        h_expand=True,
        v_expand=True,
    )


def extract_menu_items(menu, tray_item):
    """Recursively extract menu items from a DbusmenuGtk3.Menu"""
    options = []

    try:
        if hasattr(menu, 'get_children'):
            children = menu.get_children()
            for child in children:
                try:
                    # Get menu item properties
                    label = ""
                    if hasattr(child, 'property_get'):
                        label = child.property_get("label") or ""
                    elif hasattr(child, 'get_label'):
                        label = child.get_label() or ""

                    # Skip empty labels and separators
                    if not label or label.strip() == "":
                        if hasattr(child, 'property_get') and child.property_get("type") == "separator":
                            options.append(dropdown_divider(""))
                        continue

                    # Create action for this menu item
                    def create_menu_action(menu_child):
                        def action():
                            try:
                                if hasattr(menu_child, 'handle_event'):
                                    menu_child.handle_event("clicked", None, 0)
                                elif hasattr(menu_child, 'activate'):
                                    menu_child.activate()
                            except Exception:
                                pass
                        return action

                    options.append(dropdown_option(
                        label.replace("_", ""),  # Remove mnemonics
                        on_click=create_menu_action(child)
                    ))

                    # Handle submenus
                    if hasattr(child, 'get_submenu'):
                        submenu = child.get_submenu()
                        if submenu:
                            sub_options = extract_menu_items(submenu, tray_item)
                            if sub_options:
                                options.extend(sub_options)

                except Exception:
                    continue

    except Exception:
        pass

    return options


def get_tray_menu_options(tray_item):
    """Extract menu options from the system tray item's native menu"""
    options = []
    app_name = tray_item._item.title or tray_item._item.identifier or "Unknown App"

    # Create unique functions for this specific tray item to avoid closure issues
    def activate_app():
        try:
            tray_item._item.activate_for_event(None)
        except Exception:
            pass

    def show_native_menu():
        try:
            tray_item._item.invoke_menu_for_event(None)
        except Exception:
            pass

    try:
        # Try to get the actual menu items from the tray item
        menu = None
        if hasattr(tray_item._item, 'menu'):
            menu = tray_item._item.menu
        elif hasattr(tray_item._item, 'get_menu'):
            menu = tray_item._item.get_menu()

        menu_extraction_successful = False

        if menu is not None:
            # Extract actual menu items
            extracted_options = extract_menu_items(menu, tray_item)
            if extracted_options:
                # Add dividers after each option (except the last one)
                for i, option in enumerate(extracted_options):
                    options.append(option)
                    # Add divider after each option except the last one
                    if i < len(extracted_options) - 1:
                        options.append(dropdown_divider(""))

                menu_extraction_successful = True

        # Only add fallback options if menu extraction was not successful
        if not menu_extraction_successful:
            if menu is not None:
                # Menu exists but extraction failed, show native menu option
                options.append(dropdown_option(
                    f"Show {app_name} Menu",
                    on_click=show_native_menu
                ))
            else:
                # No menu available, just add basic activation
                options.append(dropdown_option(
                    f"Open {app_name}",
                    on_click=activate_app
                ))
                options.append(dropdown_divider(""))
                options.append(dropdown_option(
                    "Show Context Menu",
                    on_click=show_native_menu
                ))

    except Exception:
        # Fallback to basic options if anything fails
        options = [
            dropdown_option(
                f"Open {app_name}",
                on_click=activate_app
            ),
            dropdown_divider(""),
            dropdown_option(
                "Show Context Menu",
                on_click=show_native_menu
            ),
        ]

    return options


def create_system_tray_dropdown(tray_item, parent=None):
    """Create a dropdown menu for a system tray item"""
    dropdown_children = get_tray_menu_options(tray_item)

    # Create unique ID using both identifier and object id to ensure uniqueness
    unique_id = f"systray-{tray_item._item.identifier}-{id(tray_item)}"

    dropdown = ModusDropdown(
        parent=parent,
        dropdown_id=unique_id,
        dropdown_children=dropdown_children,
    )

    dropdown_menu = DropDownMouseCapture(
        layer="bottom",
        child_window=dropdown
    )

    # Custom positioning for system tray items
    def custom_get_coords_for_widget(widget):
        """Custom coordinate calculation for system tray items"""
        if not ((toplevel := widget.get_toplevel()) and toplevel.is_toplevel()):
            return 0, 0

        # Get the widget's allocation and position
        allocation = widget.get_allocation()

        # Try to get absolute position on screen
        try:
            # Get widget position relative to toplevel - this should give us the correct coordinates
            widget_x, widget_y = widget.translate_coordinates(toplevel, 0, 0) or (0, 0)

            # Position the dropdown below the tray item
            # Don't divide by 2 like the original method does - that's causing the positioning issue
            return widget_x, widget_y + allocation.height

        except Exception:
            # Fallback to basic positioning
            return 0, allocation.height

    # Override the get_coords_for_widget method for this specific dropdown window
    # Store the original method in case we need it
    dropdown._original_get_coords_for_widget = dropdown.get_coords_for_widget

    # Replace with our custom method
    def bound_custom_get_coords(widget):
        return custom_get_coords_for_widget(widget)

    dropdown.get_coords_for_widget = bound_custom_get_coords

    dropdown_menu.child_window.set_pointing_to(tray_item)

    return dropdown_menu



def patched_on_clicked(self, widget, event):
    """Enhanced click handler that adds dropdown functionality"""
    # Right click shows our custom dropdown instead of native menu
    if event.button == 3:
        if not hasattr(self, '_dropdown_capture'):
            # Try to find the parent window by traversing up the widget hierarchy
            parent = self.get_toplevel()
            self._dropdown_capture = create_system_tray_dropdown(self, parent)

        # Toggle the dropdown (positioning is handled by custom positioning function)
        self._dropdown_capture.toggle_mousecapture()
        return True

    # For left clicks and other buttons, use original behavior
    return original_on_clicked(self, widget, event)


def apply_enhanced_system_tray():
    # Store original methods
    global original_do_update_properties, original_on_clicked
    original_do_update_properties = SystemTrayItem.do_update_properties
    original_on_clicked = SystemTrayItem.on_clicked

    # Attach helper methods to SystemTrayItem class
    SystemTrayItem._try_load_icon_from_path = _try_load_icon_from_path
    SystemTrayItem._set_tooltip = _set_tooltip

    # Replace the methods
    SystemTrayItem.do_update_properties = patched_do_update_properties
    SystemTrayItem.on_clicked = patched_on_clicked


# Store references to original methods
original_do_update_properties = None
original_on_clicked = None
