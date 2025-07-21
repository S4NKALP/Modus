import os
import gi
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.grid import Grid
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.scale import Scale
from gi.repository import GdkPixbuf, Gtk

from config.data import NOTIF_POS_DEFAULT, NOTIF_POS_KEY
from config.settings.utils import bind_vars

gi.require_version("Gtk", "3.0")


class AppearanceTab:
    """Appearance and layout management tab for settings"""

    def __init__(self, themes, parent_window=None):
        self.themes = themes
        self.parent_window = parent_window
        self.selected_face_icon = None
        
        # Widget references
        self.wall_dir_chooser = None
        self.face_image = None
        self.face_status_label = None
        self.ws_mode_combo = None
        self.ws_chinese_switch = None
        self.position_combo = None
        self.dock_theme_combo = None
        self.icon_size_scale = None
        self.application_switcher_scale = None
        self.dock_switch = None
        self.dock_auto_hide_switch = None
        self.dock_hover_switch = None
        self.dock_hide_special_switch = None
        self.dock_hide_special_apps_switch = None
        self.notification_pos_combo = None
        self.component_switches = {}
        self.corners_switch = None

    def create_appearance_tab(self):
        """Create the Appearance tab content"""
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=False,
            v_expand=False,
            propagate_width=False,
            propagate_height=False,
        )
        # Set fixed size to match tab stack dimensions
        scrolled_window.set_size_request(580, 580)

        vbox = Box(orientation="v", spacing=15, style="margin: 15px;")
        scrolled_window.add(vbox)

        # Create wallpaper and profile icon section
        self._create_wallpaper_profile_section(vbox)
        
        # Add separator
        separator1 = Box(
            style="min-height: 1px; background-color: alpha(@fg_color, 0.2); margin: 5px 0px;",
            h_expand=True,
        )
        vbox.add(separator1)

        # Create layout options section
        self._create_layout_options_section(vbox)

        # Add separator
        separator2 = Box(
            style="min-height: 1px; background-color: alpha(@fg_color, 0.2); margin: 5px 0px;",
            h_expand=True,
        )
        vbox.add(separator2)

        # Create modules section
        self._create_modules_section(vbox)

        return scrolled_window

    def _create_wallpaper_profile_section(self, vbox):
        """Create wallpaper and profile icon section"""
        top_grid = Grid(
            column_spacing=20,
            row_spacing=5,
            style="margin-bottom: 10px;"
        )
        vbox.add(top_grid)

        # Wallpaper section
        wall_header = Label(markup="<b>Wallpapers</b>", h_align="start")
        top_grid.attach(wall_header, 0, 0, 1, 1)
        wall_label = Label(label="Directory:", h_align="start", v_align="center")
        top_grid.attach(wall_label, 0, 1, 1, 1)

        chooser_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        self.wall_dir_chooser = Gtk.FileChooserButton(
            title="Select a folder", action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        self.wall_dir_chooser.set_tooltip_text(
            "Select the directory containing your wallpaper images"
        )
        self.wall_dir_chooser.set_filename(bind_vars.get("wallpapers_dir", ""))
        self.wall_dir_chooser.set_size_request(180, -1)
        chooser_container.add(self.wall_dir_chooser)
        top_grid.attach(chooser_container, 1, 1, 1, 1)

        # Profile icon section
        face_header = Label(markup="<b>Profile Icon</b>", h_align="start")
        top_grid.attach(face_header, 2, 0, 2, 1)
        current_face = os.path.expanduser("~/.face.icon")
        face_image_container = Box(
            style_classes=["image-frame"], h_align="center", v_align="center"
        )
        self.face_image = Image(size=64)
        try:
            if os.path.exists(current_face):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(current_face, 64, 64)
                self.face_image.set_from_pixbuf(pixbuf)
            else:
                self.face_image.set_from_icon_name("user-info", Gtk.IconSize.DIALOG)
        except Exception as e:
            print(f"Error loading face icon: {e}")
            self.face_image.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)
        face_image_container.add(self.face_image)
        top_grid.attach(face_image_container, 2, 1, 1, 1)

        browse_btn_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        face_btn = Button(
            label="Browse...",
            tooltip_text="Select a square image for your profile icon",
            on_clicked=self.on_select_face_icon,
        )
        browse_btn_container.add(face_btn)
        top_grid.attach(browse_btn_container, 3, 1, 1, 1)
        self.face_status_label = Label(label="", h_align="start")
        top_grid.attach(self.face_status_label, 2, 2, 2, 1)

    def _create_layout_options_section(self, vbox):
        """Create layout options section"""
        layout_header = Label(markup="<b>Layout Options</b>", h_align="start")
        vbox.add(layout_header)
        layout_grid = Grid(
            column_spacing=20,
            row_spacing=10,
            style="margin-left: 10px; margin-top: 5px;"
        )
        vbox.add(layout_grid)

        # Workspace mode
        ws_mode_label = Label(label="Workspace Mode", h_align="start", v_align="center")
        layout_grid.attach(ws_mode_label, 0, 0, 1, 1)

        ws_mode_combo_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        self.ws_mode_combo = Gtk.ComboBoxText()
        self.ws_mode_combo.set_tooltip_text("Select how workspaces are displayed")
        ws_modes = ["Dots", "Numbers", "Single Button"]
        for mode in ws_modes:
            self.ws_mode_combo.append_text(mode)

        # Set current mode based on config
        current_dots = bind_vars.get("workspace_dots", True)
        current_nums = bind_vars.get("workspace_nums", False)
        if current_dots:
            current_mode = "Dots"
        elif current_nums:
            current_mode = "Numbers"
        else:
            current_mode = "Single Button"

        try:
            self.ws_mode_combo.set_active(ws_modes.index(current_mode))
        except ValueError:
            self.ws_mode_combo.set_active(0)

        self.ws_mode_combo.connect("changed", self.on_ws_mode_changed)
        ws_mode_combo_container.add(self.ws_mode_combo)
        layout_grid.attach(ws_mode_combo_container, 1, 0, 1, 1)

        # Chinese numerals option
        ws_chinese_label = Label(
            label="Use Chinese Numerals", h_align="start", v_align="center"
        )
        layout_grid.attach(ws_chinese_label, 2, 0, 1, 1)
        ws_chinese_switch_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        self.ws_chinese_switch = Gtk.Switch(
            active=bind_vars.get("workspace_use_chinese_numerals", False),
            sensitive=current_nums,  # Only enabled when numbers mode is selected
        )
        self.ws_chinese_switch.set_tooltip_text(
            "Use Chinese numerals (一, 二, 三...) instead of Arabic numbers"
        )
        ws_chinese_switch_container.add(self.ws_chinese_switch)
        layout_grid.attach(ws_chinese_switch_container, 3, 0, 1, 1)

        # Dock position
        position_label = Label(label="Dock Position", h_align="start", v_align="center")
        layout_grid.attach(position_label, 0, 1, 1, 1)
        position_combo_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        self.position_combo = Gtk.ComboBoxText()
        self.position_combo.set_tooltip_text("Select the position of the dock")
        positions = ["Bottom", "Top", "Left", "Right"]
        for pos in positions:
            self.position_combo.append_text(pos)
        current_position = bind_vars.get("dock_position", "Bottom")
        try:
            self.position_combo.set_active(positions.index(current_position))
        except ValueError:
            self.position_combo.set_active(0)
        self.position_combo.connect("changed", self.on_position_changed)
        position_combo_container.add(self.position_combo)
        layout_grid.attach(position_combo_container, 1, 1, 1, 1)

        # Dock theme
        dock_theme_label = Label(label="Dock Theme", h_align="start", v_align="center")
        layout_grid.attach(dock_theme_label, 2, 1, 1, 1)
        dock_theme_combo_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        self.dock_theme_combo = Gtk.ComboBoxText()
        self.dock_theme_combo.set_tooltip_text("Select the visual theme for the dock")
        for theme in self.themes:
            self.dock_theme_combo.append_text(theme)
        current_dock_theme = bind_vars.get("dock_theme", "Pills")
        try:
            self.dock_theme_combo.set_active(self.themes.index(current_dock_theme))
        except ValueError:
            self.dock_theme_combo.set_active(0)
        dock_theme_combo_container.add(self.dock_theme_combo)
        layout_grid.attach(dock_theme_combo_container, 3, 1, 1, 1)

        # Show Dock switch
        dock_label = Label(label="Show Dock", h_align="start", v_align="center")
        layout_grid.attach(dock_label, 0, 2, 1, 1)
        dock_switch_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        self.dock_switch = Gtk.Switch(active=bind_vars.get("dock_enabled", True))
        self.dock_switch.connect("notify::active", self.on_dock_enabled_changed)
        dock_switch_container.add(self.dock_switch)
        layout_grid.attach(dock_switch_container, 1, 2, 1, 1)

        # Show Dock Only on Hover
        dock_hover_label = Label(
            label="Show Dock Only on Hover", h_align="start", v_align="center"
        )
        layout_grid.attach(dock_hover_label, 2, 2, 1, 1)
        dock_hover_switch_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        self.dock_hover_switch = Gtk.Switch(
            active=bind_vars.get("dock_always_occluded", False),
            sensitive=self.dock_switch.get_active(),
        )
        dock_hover_switch_container.add(self.dock_hover_switch)
        layout_grid.attach(dock_hover_switch_container, 3, 2, 1, 1)

        # Auto-hide Dock
        dock_auto_hide_label = Label(
            label="Auto-hide Dock", h_align="start", v_align="center"
        )
        layout_grid.attach(dock_auto_hide_label, 0, 3, 1, 1)
        dock_auto_hide_switch_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        self.dock_auto_hide_switch = Gtk.Switch(
            active=bind_vars.get("dock_auto_hide", False),
            sensitive=self.dock_switch.get_active(),
        )
        dock_auto_hide_switch_container.add(self.dock_auto_hide_switch)
        layout_grid.attach(dock_auto_hide_switch_container, 1, 3, 1, 1)

        # Hide Special Workspace
        dock_hide_special_label = Label(
            label="Hide Special Workspace", h_align="start", v_align="center"
        )
        layout_grid.attach(dock_hide_special_label, 2, 3, 1, 1)
        dock_hide_special_switch_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        self.dock_hide_special_switch = Gtk.Switch(
            active=bind_vars.get("dock_hide_special_workspace", True),
            sensitive=self.dock_switch.get_active(),
        )
        self.dock_hide_special_switch.set_tooltip_text(
            "Hide the dock when on special workspaces (scratchpad)"
        )
        dock_hide_special_switch_container.add(self.dock_hide_special_switch)
        layout_grid.attach(dock_hide_special_switch_container, 3, 3, 1, 1)

        # Icon size scale
        icon_size_label = Label(
            label="Taskbar Icon Size", h_align="start", v_align="center"
        )
        layout_grid.attach(icon_size_label, 0, 4, 1, 1)

        self.icon_size_scale = Scale(
            min_value=20,
            max_value=30,
            value=bind_vars.get("dock_icon_size", 20),
            increments=(2, 4),
            draw_value=True,
            value_position="right",
            digits=0,
            h_expand=True,
        )
        self.icon_size_scale.set_tooltip_text("Adjust the size of dock icons")
        layout_grid.attach(self.icon_size_scale, 1, 4, 3, 1)  # Span 3 columns

        # Application switcher items scale (below taskbar icon size)
        application_switcher_label = Label(
            label="Application Switcher Items", h_align="start", v_align="center"
        )
        layout_grid.attach(application_switcher_label, 0, 5, 1, 1)

        self.application_switcher_scale = Scale(
            min_value=5,
            max_value=20,
            value=bind_vars.get("window_switcher_items_per_row",13),
            increments=(2, 4),
            draw_value=True,
            value_position="right",
            digits=0,
            h_expand=True,
        )
        self.application_switcher_scale.set_tooltip_text(
            "Adjust the number of items per row in the application switcher"
        )
        layout_grid.attach(self.application_switcher_scale, 1, 5, 3, 1)  # Span 3 columns

        # Hide Special Workspace Apps
        dock_hide_special_apps_label = Label(
            label="Hide Special Workspace Apps", h_align="start", v_align="center"
        )
        layout_grid.attach(dock_hide_special_apps_label, 0, 6, 1, 1)
        dock_hide_special_apps_switch_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        self.dock_hide_special_apps_switch = Gtk.Switch(
            active=bind_vars.get("dock_hide_special_workspace_apps", True),
            sensitive=self.dock_switch.get_active(),
        )
        self.dock_hide_special_apps_switch.set_tooltip_text(
            "Hide applications that are in special workspaces (scratchpad) from the dock"
        )
        dock_hide_special_apps_switch_container.add(self.dock_hide_special_apps_switch)
        layout_grid.attach(dock_hide_special_apps_switch_container, 1, 6, 1, 1)

        # Notification position
        notification_pos_label = Label(
            label="Notification Position", h_align="start", v_align="center"
        )
        layout_grid.attach(notification_pos_label, 2, 6, 1, 1)

        notification_pos_combo_container = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )

        self.notification_pos_combo = Gtk.ComboBoxText()
        self.notification_pos_combo.set_tooltip_text(
            "Select where notifications appear on the screen."
        )

        notification_positions_list = ["Top", "Bottom"]
        for pos in notification_positions_list:
            self.notification_pos_combo.append_text(pos)

        current_notif_pos = bind_vars.get(NOTIF_POS_KEY, NOTIF_POS_DEFAULT)
        try:
            self.notification_pos_combo.set_active(
                notification_positions_list.index(current_notif_pos)
            )
        except ValueError:
            self.notification_pos_combo.set_active(0)

        self.notification_pos_combo.connect(
            "changed", self.on_notification_position_changed
        )

        notification_pos_combo_container.add(self.notification_pos_combo)
        layout_grid.attach(notification_pos_combo_container, 3, 6, 1, 1)

    def _create_modules_section(self, vbox):
        """Create modules section"""
        components_header = Label(markup="<b>Modules</b>", h_align="start")
        vbox.add(components_header)
        components_grid = Grid(
            column_spacing=15,
            row_spacing=8,
            style="margin-left: 10px; margin-top: 5px;"
        )
        vbox.add(components_grid)

        self.component_switches = {}
        component_display_names = {
            "workspace": "Workspaces",
            "metrics": "System Metrics",
            "date_time": "Date & Time",
            "battery": "Battery Indicator",
            "controls": "Control Panel",
            "indicators": "Indicators",
            "music_player": "Music Player",
            "applications": "Taskbar",
            "language": "Language Indicator",
        }

        self.corners_switch = Gtk.Switch(active=bind_vars.get("corners_visible", True))
        num_components = len(component_display_names) + 1
        rows_per_column = (num_components + 1) // 2

        corners_label = Label(
            label="Rounded Corners", h_align="start", v_align="center"
        )
        components_grid.attach(corners_label, 0, 0, 1, 1)
        switch_container_corners = Box(
            orientation="horizontal",
            h_align="start",
            v_align="center"
        )
        switch_container_corners.add(self.corners_switch)
        components_grid.attach(switch_container_corners, 1, 0, 1, 1)

        item_idx = 0
        for name, display in component_display_names.items():
            if item_idx < (rows_per_column - 1):
                row = item_idx + 1
                col = 0
            else:
                row = item_idx - (rows_per_column - 1)
                col = 2

            component_label = Label(label=display, h_align="start", v_align="center")
            components_grid.attach(component_label, col, row, 1, 1)

            switch_container = Box(
                orientation="horizontal",
                h_align="start",
                v_align="center"
            )
            component_switch = Gtk.Switch(
                active=bind_vars.get(f"dock_{name}_visible", True)
            )
            switch_container.add(component_switch)
            components_grid.attach(switch_container, col + 1, row, 1, 1)
            self.component_switches[name] = component_switch
            item_idx += 1

    # Event handlers
    def on_ws_mode_changed(self, combo):
        """Handle workspace mode change"""
        mode = combo.get_active_text()
        is_numbers_mode = mode == "Numbers"
        self.ws_chinese_switch.set_sensitive(is_numbers_mode)
        if not is_numbers_mode:
            self.ws_chinese_switch.set_active(False)

    def on_position_changed(self, _combo):
        """Handle dock position change"""
        # Note: centered_switch is not used in appearance tab,
        # this method is kept for compatibility
        pass

    def on_dock_enabled_changed(self, switch, _gparam):
        """Handle dock enabled/disabled change"""
        is_active = switch.get_active()
        self.dock_hover_switch.set_sensitive(is_active)
        self.dock_auto_hide_switch.set_sensitive(is_active)
        self.dock_hide_special_switch.set_sensitive(is_active)
        self.dock_hide_special_apps_switch.set_sensitive(is_active)
        if not is_active:
            self.dock_hover_switch.set_active(False)
            self.dock_auto_hide_switch.set_active(False)
            self.dock_hide_special_switch.set_active(False)
            self.dock_hide_special_apps_switch.set_active(False)

    def on_notification_position_changed(self, combo):
        """Handle notification position change"""
        selected_text = combo.get_active_text()
        if selected_text:
            bind_vars[NOTIF_POS_KEY] = selected_text
            print(
                f"Notification position updated in bind_vars: {
                    bind_vars[NOTIF_POS_KEY]
                }"
            )

    def on_select_face_icon(self, _widget):
        """Handle face icon selection"""
        dialog = Gtk.FileChooserDialog(
            title="Select Face Icon",
            transient_for=self.parent_window,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )
        image_filter = Gtk.FileFilter()
        image_filter.set_name("Image files")
        for mime in ["image/png", "image/jpeg"]:
            image_filter.add_mime_type(mime)
        for pattern in ["*.png", "*.jpg", "*.jpeg"]:
            image_filter.add_pattern(pattern)
        dialog.add_filter(image_filter)
        if dialog.run() == Gtk.ResponseType.OK:
            self.selected_face_icon = dialog.get_filename()
            self.face_status_label.label = (
                f"Selected: {os.path.basename(self.selected_face_icon)}"
            )
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    self.selected_face_icon, 64, 64
                )
                self.face_image.set_from_pixbuf(pixbuf)
            except Exception as e:
                print(f"Error loading selected face icon preview: {e}")
                self.face_image.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)
        dialog.destroy()

    def get_appearance_values(self):
        """Get current appearance values from widgets"""
        values = {}

        values["wallpapers_dir"] = self.wall_dir_chooser.get_filename()
        values["dock_position"] = self.position_combo.get_active_text()
        values["vertical"] = values["dock_position"] in ["Left", "Right"]
        values["dock_enabled"] = self.dock_switch.get_active()
        values["dock_auto_hide"] = self.dock_auto_hide_switch.get_active()
        values["dock_always_occluded"] = self.dock_hover_switch.get_active()
        values["dock_hide_special_workspace"] = self.dock_hide_special_switch.get_active()
        values["dock_hide_special_workspace_apps"] = self.dock_hide_special_apps_switch.get_active()
        values["dock_icon_size"] = int(self.icon_size_scale.get_value())
        values["window_switcher_items_per_row"] = int(self.application_switcher_scale.get_value())
        values["corners_visible"] = self.corners_switch.get_active()
        values["dock_theme"] = self.dock_theme_combo.get_active_text()

        selected_notif_pos_text = self.notification_pos_combo.get_active_text()
        if selected_notif_pos_text:
            values[NOTIF_POS_KEY] = selected_notif_pos_text
        else:
            values[NOTIF_POS_KEY] = NOTIF_POS_DEFAULT

        for component_name, switch in self.component_switches.items():
            values[f"dock_{component_name}_visible"] = switch.get_active()

        # Save workspace settings
        ws_mode = self.ws_mode_combo.get_active_text()
        values["workspace_dots"] = ws_mode == "Dots"
        values["workspace_nums"] = ws_mode == "Numbers"
        values["workspace_use_chinese_numerals"] = self.ws_chinese_switch.get_active()

        return values

    def get_selected_face_icon(self):
        """Get the selected face icon path"""
        return self.selected_face_icon

    def clear_selected_face_icon(self):
        """Clear the selected face icon"""
        self.selected_face_icon = None
        self.face_status_label.label = ""

    def reset_to_defaults(self, defaults):
        """Reset appearance settings to default values"""
        self.wall_dir_chooser.set_filename(defaults.get("wallpapers_dir", ""))

        positions = ["Bottom", "Top", "Left", "Right"]
        default_position = defaults.get("dock_position", "Bottom")
        try:
            self.position_combo.set_active(positions.index(default_position))
        except ValueError:
            self.position_combo.set_active(0)

        self.dock_switch.set_active(defaults.get("dock_enabled", True))
        self.dock_auto_hide_switch.set_active(defaults.get("dock_auto_hide", False))
        self.dock_hover_switch.set_active(defaults.get("dock_always_occluded", False))
        self.dock_hide_special_switch.set_active(defaults.get("dock_hide_special_workspace", True))
        self.dock_hide_special_apps_switch.set_active(defaults.get("dock_hide_special_workspace_apps", True))

        # Update sensitivity based on dock enabled state
        dock_enabled = self.dock_switch.get_active()
        self.dock_hover_switch.set_sensitive(dock_enabled)
        self.dock_auto_hide_switch.set_sensitive(dock_enabled)
        self.dock_hide_special_switch.set_sensitive(dock_enabled)
        self.dock_hide_special_apps_switch.set_sensitive(dock_enabled)

        default_dock_theme_val = defaults.get("dock_theme", "Pills")
        try:
            self.dock_theme_combo.set_active(self.themes.index(default_dock_theme_val))
        except ValueError:
            self.dock_theme_combo.set_active(0)

        default_notif_pos_val = defaults.get(NOTIF_POS_KEY, NOTIF_POS_DEFAULT)
        notification_positions_list = ["Top", "Bottom"]
        try:
            self.notification_pos_combo.set_active(
                notification_positions_list.index(default_notif_pos_val)
            )
        except ValueError:
            self.notification_pos_combo.set_active(0)

        for name, switch in self.component_switches.items():
            switch.set_active(defaults.get(f"dock_{name}_visible", True))

        # Reset workspace settings
        default_dots = defaults.get("workspace_dots", True)
        default_nums = defaults.get("workspace_nums", False)
        if default_dots:
            default_mode = "Dots"
        elif default_nums:
            default_mode = "Numbers"
        else:
            default_mode = "Single Button"

        ws_modes = ["Dots", "Numbers", "Single Button"]
        try:
            self.ws_mode_combo.set_active(ws_modes.index(default_mode))
        except ValueError:
            self.ws_mode_combo.set_active(0)

        self.ws_chinese_switch.set_active(defaults.get("workspace_use_chinese_numerals", False))
        self.ws_chinese_switch.set_sensitive(default_nums)
        self.corners_switch.set_active(defaults.get("corners_visible", True))

        # Reset face icon
        self.selected_face_icon = None
        self.face_status_label.label = ""
        current_face = os.path.expanduser("~/.face.icon")
        try:
            if os.path.exists(current_face):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(current_face, 64, 64)
                self.face_image.set_from_pixbuf(pixbuf)
            else:
                self.face_image.set_from_icon_name("user-info", Gtk.IconSize.DIALOG)
        except Exception as e:
            print(f"Error loading face icon: {e}")
            self.face_image.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)

        # Reset scales
        self.icon_size_scale.set_value(defaults.get("dock_icon_size", 20))
        self.application_switcher_scale.set_value(defaults.get("window_switcher_items_per_row", 13))
