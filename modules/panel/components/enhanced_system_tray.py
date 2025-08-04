"""
Enhanced System Tray Icon Handling

This module provides enhanced icon loading capabilities for system tray items,
including fallback mechanisms for file paths and common icon locations.
It also adds dropdown menu functionality for system tray items with:

- Dynamic menu state tracking (checkboxes, radio buttons)
- Real-time menu refresh on each right-click
- Proper toggle state visualization (✓ for checked, ● for radio selected)
- Enhanced error handling and debugging
- Support for enabled/disabled menu items
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


def dropdown_option(label: str = "", on_click=None, submenu_items=None, has_native_submenu=False, native_menu_item=None):
    """Create a dropdown option for system tray items with optional submenu"""
    from fabric.widgets.button import Button
    from fabric.widgets.centerbox import CenterBox
    from fabric.widgets.box import Box

    # If this has native submenu (like NetworkManager WiFi list), create special expandable option
    if has_native_submenu and native_menu_item:
        from fabric.widgets.revealer import Revealer

        # State for submenu expansion
        submenu_expanded = False

        def toggle_native_submenu(_):
            nonlocal submenu_expanded
            submenu_expanded = not submenu_expanded
            submenu_revealer.set_reveal_child(submenu_expanded)

            # Update the arrow indicator
            arrow_label = "▼" if submenu_expanded else "▶"
            main_button.get_child().get_start_children()[0].set_label(f"{label} {arrow_label}")

            print(f"[DEBUG] Native submenu {'expanded' if submenu_expanded else 'collapsed'}")

        def show_native_menu(_):
            """Show the native context menu for this item"""
            try:
                print(f"[DEBUG] Showing native menu for '{label}'")

                # Hide our dropdown first
                from widgets.dropdown import dropdowns
                for dropdown in dropdowns:
                    if dropdown.is_visible() and hasattr(dropdown, "hide_via_mousecapture"):
                        dropdown.hide_via_mousecapture()
                        break

                # Try to activate the native menu item
                if hasattr(native_menu_item, 'activate'):
                    native_menu_item.activate()
                elif hasattr(native_menu_item, 'handle_event'):
                    native_menu_item.handle_event("clicked", None, 0)

            except Exception as e:
                print(f"[DEBUG] Failed to show native menu for '{label}': {e}")

        # Create main button with arrow indicator
        main_button = Button(
            child=CenterBox(
                start_children=[
                    Label(label=f"{label} ▶", h_align="start", name="dropdown-option-label"),
                ],
                orientation="horizontal",
                h_align="fill",
                h_expand=True,
                v_expand=True,
            ),
            name="dropdown-option",
            h_align="fill",
            on_clicked=toggle_native_submenu,
            h_expand=True,
            v_expand=True,
        )

        # Create submenu with native menu option
        native_submenu_items = [
            Button(
                child=CenterBox(
                    start_children=[
                        Label(label="  Show Native Menu", h_align="start", name="dropdown-option-label"),
                    ],
                    orientation="horizontal",
                    h_align="fill",
                    h_expand=True,
                    v_expand=True,
                ),
                name="dropdown-option",
                h_align="fill",
                on_clicked=show_native_menu,
                h_expand=True,
                v_expand=True,
            ),
            Button(
                child=CenterBox(
                    start_children=[
                        Label(label="  (Hover over tray icon for full menu)", h_align="start", name="dropdown-option-label"),
                    ],
                    orientation="horizontal",
                    h_align="fill",
                    h_expand=True,
                    v_expand=True,
                ),
                name="dropdown-option",
                h_align="fill",
                sensitive=False,  # Disabled info text
                h_expand=True,
                v_expand=True,
            )
        ]

        # Create revealer for submenu
        submenu_revealer = Revealer(
            child=Box(
                children=native_submenu_items,
                orientation="vertical",
                name="submenu-items",
            ),
            reveal_child=False,
            transition_type="slide-down",
            transition_duration=200,
        )

        # Return container with main button and submenu
        return Box(
            children=[main_button, submenu_revealer],
            orientation="vertical",
            name="dropdown-option-with-submenu",
        )

    # If this has submenu items, create an expandable option
    elif submenu_items:
        from fabric.widgets.revealer import Revealer

        # State for submenu expansion
        submenu_expanded = False

        def toggle_submenu(_):
            nonlocal submenu_expanded
            submenu_expanded = not submenu_expanded
            submenu_revealer.set_reveal_child(submenu_expanded)

            # Update the arrow indicator
            arrow_label = "▼" if submenu_expanded else "▶"
            main_button.get_child().get_start_children()[0].set_label(f"{label} {arrow_label}")

            print(f"[DEBUG] Submenu {'expanded' if submenu_expanded else 'collapsed'}")

        # Create main button with arrow indicator
        main_button = Button(
            child=CenterBox(
                start_children=[
                    Label(label=f"{label} ▶", h_align="start", name="dropdown-option-label"),
                ],
                orientation="horizontal",
                h_align="fill",
                h_expand=True,
                v_expand=True,
            ),
            name="dropdown-option",
            h_align="fill",
            on_clicked=toggle_submenu,
            h_expand=True,
            v_expand=True,
        )

        # Create submenu items with indentation
        indented_submenu_items = []
        for item in submenu_items:
            # Add indentation to submenu items
            if hasattr(item, 'get_child') and hasattr(item.get_child(), 'get_start_children'):
                original_label = item.get_child().get_start_children()[0]
                if hasattr(original_label, 'get_label'):
                    original_text = original_label.get_label()
                    original_label.set_label(f"  {original_text}")  # Add indentation
            indented_submenu_items.append(item)

        # Create revealer for submenu
        submenu_revealer = Revealer(
            child=Box(
                children=indented_submenu_items,
                orientation="vertical",
                name="submenu-items",
            ),
            reveal_child=False,
            transition_type="slide-down",
            transition_duration=200,
        )

        # Return container with main button and submenu
        return Box(
            children=[main_button, submenu_revealer],
            orientation="vertical",
            name="dropdown-option-with-submenu",
        )

    # Regular option without submenu
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


# Note: Submenu functionality is now handled inline within dropdown_option
# using Revealer widgets for expandable menu sections


def extract_menu_items(menu, tray_item):
    """Recursively extract menu items from a DbusmenuGtk3.Menu with state tracking"""
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

                    # Check for toggle state and other properties
                    toggle_type = None
                    toggle_state = None
                    enabled = True
                    visible = True

                    if hasattr(child, 'property_get'):
                        toggle_type = child.property_get("toggle-type")
                        toggle_state = child.property_get("toggle-state")
                        enabled = child.property_get("enabled")
                        visible = child.property_get("visible")

                        # Handle different property formats
                        if enabled is None:
                            enabled = True
                        if visible is None:
                            visible = True

                        # Debug output for complex menu items
                        if toggle_type or toggle_state is not None:
                            print(f"[DEBUG] Menu item '{label}': toggle_type={toggle_type}, toggle_state={toggle_state}, enabled={enabled}")

                    # Skip invisible items
                    if not visible:
                        continue

                    # Format label based on toggle state
                    display_label = label.replace("_", "")  # Remove mnemonics

                    if toggle_type == "checkmark" and toggle_state is not None:
                        # Add checkmark for checked items
                        if toggle_state == 1 or toggle_state is True:  # Checked
                            display_label = f"✓ {display_label}"
                        else:  # Unchecked
                            display_label = f"  {display_label}"
                    elif toggle_type == "radio" and toggle_state is not None:
                        # Add radio button indicator
                        if toggle_state == 1 or toggle_state is True:  # Selected
                            display_label = f"● {display_label}"
                        else:  # Not selected
                            display_label = f"○ {display_label}"

                    # Create action for this menu item
                    def create_menu_action(menu_child):
                        def action():
                            try:
                                if hasattr(menu_child, 'handle_event'):
                                    menu_child.handle_event("clicked", None, 0)
                                elif hasattr(menu_child, 'activate'):
                                    menu_child.activate()
                                else:
                                    print(f"[DEBUG] No activation method found for menu item: {label}")
                            except Exception as e:
                                print(f"[DEBUG] Failed to activate menu item '{label}': {e}")
                        return action

                    # Handle submenus
                    submenu_items = None
                    has_native_submenu = False

                    if hasattr(child, 'get_submenu'):
                        submenu = child.get_submenu()
                        if submenu:
                            submenu_items = extract_menu_items(submenu, tray_item)
                            if submenu_items:
                                print(f"[DEBUG] Found submenu for '{label}' with {len(submenu_items)} items")

                    # Check for potential native submenus (common patterns)
                    if not submenu_items and hasattr(child, 'property_get'):
                        # Check for indicators that this might have a native submenu
                        item_type = child.property_get("type") or ""
                        children_display = child.property_get("children-display") or ""

                        # Common patterns for items that show native submenus on hover
                        submenu_indicators = [
                            "WiFi Networks" in label,
                            "Available Networks" in label,
                            "Connect to" in label,
                            "Bluetooth" in label and ("Device" in label or "Connect" in label),
                            "Audio" in label and ("Device" in label or "Output" in label),
                            "VPN" in label and "Connect" in label,
                            children_display == "submenu",
                            item_type == "submenu",
                            # Additional patterns for common system tray items
                            label.endswith("...") and ("Network" in label or "Audio" in label or "Bluetooth" in label),
                            "Select" in label and ("Device" in label or "Network" in label),
                        ]

                        if any(submenu_indicators):
                            has_native_submenu = True
                            print(f"[DEBUG] Detected potential native submenu for '{label}'")

                    # Create dropdown option with proper state indication and submenu
                    option = dropdown_option(
                        display_label,
                        on_click=create_menu_action(child) if not submenu_items and not has_native_submenu else None,
                        submenu_items=submenu_items,
                        has_native_submenu=has_native_submenu,
                        native_menu_item=child if has_native_submenu else None
                    )

                    # Disable option if not enabled
                    if not enabled:
                        option.set_sensitive(False)

                    options.append(option)

                except Exception as e:
                    print(f"[DEBUG] Error processing menu item: {e}")
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
        except Exception as e:
            print(f"[DEBUG] Failed to activate {app_name}: {e}")

    def show_native_menu():
        try:
            tray_item._item.invoke_menu_for_event(None)
        except Exception as e:
            print(f"[DEBUG] Failed to show native menu for {app_name}: {e}")

    try:
        # Try to get the actual menu items from the tray item
        menu = None
        if hasattr(tray_item._item, 'menu'):
            menu = tray_item._item.menu
        elif hasattr(tray_item._item, 'get_menu'):
            menu = tray_item._item.get_menu()

        menu_extraction_successful = False

        if menu is not None:
            print(f"[DEBUG] Extracting menu for {app_name}, menu type: {type(menu)}")
            # Extract actual menu items
            extracted_options = extract_menu_items(menu, tray_item)
            if extracted_options:
                print(f"[DEBUG] Successfully extracted {len(extracted_options)} menu items for {app_name}")
                # Add dividers after each option (except the last one)
                for i, option in enumerate(extracted_options):
                    options.append(option)
                    # Add divider after each option except the last one
                    if i < len(extracted_options) - 1:
                        options.append(dropdown_divider(""))

                menu_extraction_successful = True
            else:
                print(f"[DEBUG] No menu items extracted for {app_name}")

        # Only add fallback options if menu extraction was not successful
        if not menu_extraction_successful:
            if menu is not None:
                # Menu exists but extraction failed, show native menu option
                print(f"[DEBUG] Menu exists but extraction failed for {app_name}, adding fallback")
                options.append(dropdown_option(
                    f"Show {app_name} Menu",
                    on_click=show_native_menu
                ))
            else:
                # No menu available, just add basic activation
                print(f"[DEBUG] No menu available for {app_name}, adding basic options")
                options.append(dropdown_option(
                    f"Open {app_name}",
                    on_click=activate_app
                ))
                options.append(dropdown_divider(""))
                options.append(dropdown_option(
                    "Show Context Menu",
                    on_click=show_native_menu
                ))

    except Exception as e:
        print(f"[DEBUG] Exception while extracting menu for {app_name}: {e}")
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


def refresh_dropdown_menu(dropdown, tray_item):
    """Refresh the dropdown menu with current menu state"""
    try:
        # Get fresh menu options
        fresh_options = get_tray_menu_options(tray_item)

        # Update the dropdown children
        if hasattr(dropdown, 'child_window') and hasattr(dropdown.child_window, 'dropdown'):
            dropdown.child_window.dropdown.children = fresh_options

        return True
    except Exception:
        return False


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

    # Store reference to tray item for refreshing
    dropdown_menu._tray_item = tray_item

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
        # Always refresh the dropdown to get current menu state
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
