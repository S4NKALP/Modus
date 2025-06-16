from config.settings.utils import backup_and_replace, bind_vars, start_config
from config.data import APP_NAME, APP_NAME_CAP, NOTIF_POS_DEFAULT, NOTIF_POS_KEY
from PIL import Image
from gi.repository import GdkPixbuf, GLib, Gtk
from fabric.widgets.window import Window
from fabric.widgets.stack import Stack
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.scale import Scale
from fabric.widgets.label import Label
from fabric.widgets.image import Image as FabricImage
from fabric.widgets.entry import Entry
from fabric.widgets.button import Button
from fabric.widgets.box import Box
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")


class HyprConfGUI(Window):
    def __init__(self, show_lock_checkbox: bool, show_idle_checkbox: bool, **kwargs):
        super().__init__(
            title="Ax-Shell Settings",
            name="axshell-settings-window",
            size=(640, 640),
            **kwargs,
        )

        self.set_resizable(False)
        self.themes = ["Pills", "Dense", "Edge"]
        self.selected_face_icon = None
        self.show_lock_checkbox = show_lock_checkbox
        self.show_idle_checkbox = show_idle_checkbox

        root_box = Box(orientation="v", spacing=10, style="margin: 10px;")
        self.add(root_box)

        main_content_box = Box(orientation="h", spacing=6, v_expand=True, h_expand=True)
        root_box.add(main_content_box)

        self.tab_stack = Stack(
            transition_type="slide-up-down",
            transition_duration=250,
            v_expand=True,
            h_expand=True,
        )

        self.key_bindings_tab_content = self.create_key_bindings_tab()
        self.appearance_tab_content = self.create_appearance_tab()
        self.system_tab_content = self.create_system_tab()
        self.about_tab_content = self.create_about_tab()

        self.tab_stack.add_titled(
            self.key_bindings_tab_content, "key_bindings", "Key Bindings"
        )
        self.tab_stack.add_titled(
            self.appearance_tab_content, "appearance", "Appearance"
        )
        self.tab_stack.add_titled(self.system_tab_content, "system", "System")
        self.tab_stack.add_titled(self.about_tab_content, "about", "About")

        tab_switcher = Gtk.StackSwitcher()
        tab_switcher.set_stack(self.tab_stack)
        tab_switcher.set_orientation(Gtk.Orientation.VERTICAL)
        main_content_box.add(tab_switcher)
        main_content_box.add(self.tab_stack)

        button_box = Box(orientation="h", spacing=10, h_align="end")
        reset_btn = Button(label="Reset to Defaults", on_clicked=self.on_reset)
        button_box.add(reset_btn)
        close_btn = Button(label="Close", on_clicked=self.on_close)
        button_box.add(close_btn)
        accept_btn = Button(label="Apply & Reload", on_clicked=self.on_accept)
        button_box.add(accept_btn)
        root_box.add(button_box)

    def create_key_bindings_tab(self):
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False,
        )

        main_vbox = Box(orientation="v", spacing=10, style="margin: 15px;")
        scrolled_window.add(main_vbox)

        keybind_grid = Gtk.Grid()
        keybind_grid.set_column_spacing(10)
        keybind_grid.set_row_spacing(8)
        keybind_grid.set_margin_start(5)
        keybind_grid.set_margin_end(5)
        keybind_grid.set_margin_top(5)
        keybind_grid.set_margin_bottom(5)

        action_label = Label(
            markup="<b>Action</b>", h_align="start", style="margin-bottom: 5px;"
        )
        modifier_label = Label(
            markup="<b>Modifier</b>", h_align="start", style="margin-bottom: 5px;"
        )
        separator_label = Label(
            label="+", h_align="center", style="margin-bottom: 5px;"
        )
        key_label = Label(
            markup="<b>Key</b>", h_align="start", style="margin-bottom: 5px;"
        )

        keybind_grid.attach(action_label, 0, 0, 1, 1)
        keybind_grid.attach(modifier_label, 1, 0, 1, 1)
        keybind_grid.attach(separator_label, 2, 0, 1, 1)
        keybind_grid.attach(key_label, 3, 0, 1, 1)

        self.entries = []
        bindings = [
            (f"Reload {APP_NAME_CAP}", "prefix_restart", "suffix_restart"),
            ("Message", "prefix_axmsg", "suffix_axmsg"),
            ("Application Switcher", "prefix_application_switcher", "suffix_application_switcher"),
            ("Dashboard", "prefix_dash", "suffix_dash"),
            ("Bluetooth", "prefix_bluetooth", "suffix_bluetooth"),
            ("Pins", "prefix_pins", "suffix_pins"),
            ("Kanban", "prefix_kanban", "suffix_kanban"),
            ("App Launcher", "prefix_launcher", "suffix_launcher"),
            ("Tmux", "prefix_tmux", "suffix_tmux"),
            ("Clipboard History", "prefix_cliphist", "suffix_cliphist"),
            ("Toolbox", "prefix_toolbox", "suffix_toolbox"),
            ("Overview", "prefix_overview", "suffix_overview"),
            ("Wallpapers", "prefix_wallpapers", "suffix_wallpapers"),
            ("Random Wallpaper", "prefix_randwall", "suffix_randwall"),
            ("Emoji Picker", "prefix_emoji", "suffix_emoji"),
            ("Power Menu", "prefix_power", "suffix_power"),
            ("Toggle Caffeine", "prefix_caffeine", "suffix_caffeine"),
            ("Reload CSS", "prefix_css", "suffix_css"),
            (
                "Restart with inspector",
                "prefix_restart_inspector",
                "suffix_restart_inspector",
            ),
        ]

        for i, (label_text, prefix_key, suffix_key) in enumerate(bindings):
            row = i + 1
            binding_label = Label(label=label_text, h_align="start")
            keybind_grid.attach(binding_label, 0, row, 1, 1)
            prefix_entry = Entry(text=bind_vars.get(prefix_key, ""))
            keybind_grid.attach(prefix_entry, 1, row, 1, 1)
            plus_label = Label(label="+", h_align="center")
            keybind_grid.attach(plus_label, 2, row, 1, 1)
            suffix_entry = Entry(text=bind_vars.get(suffix_key, ""))
            keybind_grid.attach(suffix_entry, 3, row, 1, 1)
            self.entries.append((prefix_key, suffix_key, prefix_entry, suffix_entry))

        main_vbox.add(keybind_grid)
        return scrolled_window

    def create_appearance_tab(self):
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False,
        )

        vbox = Box(orientation="v", spacing=15, style="margin: 15px;")
        scrolled_window.add(vbox)

        top_grid = Gtk.Grid()
        top_grid.set_column_spacing(20)
        top_grid.set_row_spacing(5)
        top_grid.set_margin_bottom(10)
        vbox.add(top_grid)

        wall_header = Label(markup="<b>Wallpapers</b>", h_align="start")
        top_grid.attach(wall_header, 0, 0, 1, 1)
        wall_label = Label(label="Directory:", h_align="start", v_align="center")
        top_grid.attach(wall_label, 0, 1, 1, 1)

        chooser_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        chooser_container.set_halign(Gtk.Align.START)
        chooser_container.set_valign(Gtk.Align.CENTER)
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

        face_header = Label(markup="<b>Profile Icon</b>", h_align="start")
        top_grid.attach(face_header, 2, 0, 2, 1)
        current_face = os.path.expanduser("~/.face.icon")
        face_image_container = Box(
            style_classes=["image-frame"], h_align="center", v_align="center"
        )
        self.face_image = FabricImage(size=64)
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

        browse_btn_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        browse_btn_container.set_halign(Gtk.Align.START)
        browse_btn_container.set_valign(Gtk.Align.CENTER)
        face_btn = Button(
            label="Browse...",
            tooltip_text="Select a square image for your profile icon",
            on_clicked=self.on_select_face_icon,
        )
        browse_btn_container.add(face_btn)
        top_grid.attach(browse_btn_container, 3, 1, 1, 1)
        self.face_status_label = Label(label="", h_align="start")
        top_grid.attach(self.face_status_label, 2, 2, 2, 1)

        separator1 = Box(
            style="min-height: 1px; background-color: alpha(@fg_color, 0.2); margin: 5px 0px;",
            h_expand=True,
        )
        vbox.add(separator1)

        layout_header = Label(markup="<b>Layout Options</b>", h_align="start")
        vbox.add(layout_header)
        layout_grid = Gtk.Grid()
        layout_grid.set_column_spacing(20)
        layout_grid.set_row_spacing(10)
        layout_grid.set_margin_start(10)
        layout_grid.set_margin_top(5)
        vbox.add(layout_grid)

        # Workspace mode
        ws_mode_label = Label(label="Workspace Mode", h_align="start", v_align="center")
        layout_grid.attach(ws_mode_label, 0, 0, 1, 1)

        ws_mode_combo_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
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
        ws_chinese_switch_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
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

        position_label = Label(label="Dock Position", h_align="start", v_align="center")
        layout_grid.attach(position_label, 0, 1, 1, 1)
        position_combo_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )
        self.position_combo = Gtk.ComboBoxText()
        self.position_combo.set_tooltip_text("Select the position of the dock")
        positions = ["Bottom", "Left", "Right"]
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

        dock_theme_label = Label(label="Dock Theme", h_align="start", v_align="center")
        layout_grid.attach(dock_theme_label, 2, 1, 1, 1)
        dock_theme_combo_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
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

        # Add icon size scale
        icon_size_label = Label(label="Taskbar Icon Size", h_align="start", v_align="center")
        layout_grid.attach(icon_size_label, 0, 4, 1, 1)

        icon_size_scale_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            hexpand=True,
        )

        self.icon_size_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 20, 30, 2
        )
        self.icon_size_scale.set_value(bind_vars.get("dock_icon_size", 20))
        self.icon_size_scale.set_size_request(150, -1)
        self.icon_size_scale.set_draw_value(True)
        self.icon_size_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.icon_size_scale.set_tooltip_text("Adjust the size of dock icons")

        icon_size_scale_container.add(self.icon_size_scale)
        layout_grid.attach(icon_size_scale_container, 1, 4, 1, 1)

        # Add application switcher items scale
        application_switcher_label = Label(label="Application Switcher Items", h_align="start", v_align="center")
        layout_grid.attach(application_switcher_label, 2, 4, 1, 1)

        application_switcher_scale_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            hexpand=True,
        )

        self.application_switcher_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 5, 20, 1
        )
        self.application_switcher_scale.set_value(bind_vars.get("window_switcher_items_per_row", 13))
        self.application_switcher_scale.set_size_request(150, -1)
        self.application_switcher_scale.set_draw_value(True)
        self.application_switcher_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.application_switcher_scale.set_tooltip_text("Adjust the number of items per row in the application switcher")

        application_switcher_scale_container.add(self.application_switcher_scale)
        layout_grid.attach(application_switcher_scale_container, 3, 4, 1, 1)

        dock_label = Label(label="Show Dock", h_align="start", v_align="center")
        layout_grid.attach(dock_label, 0, 2, 1, 1)
        dock_switch_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )
        self.dock_switch = Gtk.Switch(active=bind_vars.get("dock_enabled", True))
        self.dock_switch.connect("notify::active", self.on_dock_enabled_changed)
        dock_switch_container.add(self.dock_switch)
        layout_grid.attach(dock_switch_container, 1, 2, 1, 1)

        dock_auto_hide_label = Label(
            label="Auto-hide Dock", h_align="start", v_align="center"
        )
        layout_grid.attach(dock_auto_hide_label, 0, 3, 1, 1)
        dock_auto_hide_switch_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )
        self.dock_auto_hide_switch = Gtk.Switch(
            active=bind_vars.get("dock_auto_hide", False),
            sensitive=self.dock_switch.get_active(),
        )
        dock_auto_hide_switch_container.add(self.dock_auto_hide_switch)
        layout_grid.attach(dock_auto_hide_switch_container, 1, 3, 1, 1)

        dock_hover_label = Label(
            label="Show Dock Only on Hover", h_align="start", v_align="center"
        )
        layout_grid.attach(dock_hover_label, 2, 2, 1, 1)
        dock_hover_switch_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )
        self.dock_hover_switch = Gtk.Switch(
            active=bind_vars.get("dock_always_occluded", False),
            sensitive=self.dock_switch.get_active(),
        )
        dock_hover_switch_container.add(self.dock_hover_switch)
        layout_grid.attach(dock_hover_switch_container, 3, 2, 1, 1)

        notification_pos_label = Label(
            label="Notification Position", h_align="start", v_align="center"
        )
        layout_grid.attach(notification_pos_label, 0, 8, 1, 1)

        notification_pos_combo_container = Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
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
        layout_grid.attach(notification_pos_combo_container, 1, 8, 3, 1)

        separator2 = Box(
            style="min-height: 1px; background-color: alpha(@fg_color, 0.2); margin: 5px 0px;",
            h_expand=True,
        )
        vbox.add(separator2)

        components_header = Label(markup="<b>Modules</b>", h_align="start")
        vbox.add(components_header)
        components_grid = Gtk.Grid()
        components_grid.set_column_spacing(15)
        components_grid.set_row_spacing(8)
        components_grid.set_margin_start(10)
        components_grid.set_margin_top(5)
        vbox.add(components_grid)

        self.component_switches = {}
        component_display_names = {
            "workspace": "Workspaces",
            "metrics": "System Metrics",
            "date_time": "Date & Time",
            "battery": "Battery Indicator",
            "controls": "Control Panel",
            "indicators": "Indicators",
            "applications": "Taskbar",
            "language": "Language Indicator",
            "music_player": "Music Player"
        }

        self.corners_switch = Gtk.Switch(active=bind_vars.get("corners_visible", True))
        num_components = len(component_display_names) + 1
        rows_per_column = (num_components + 1) // 2

        corners_label = Label(
            label="Rounded Corners", h_align="start", v_align="center"
        )
        components_grid.attach(corners_label, 0, 0, 1, 1)
        switch_container_corners = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )
        switch_container_corners.add(self.corners_switch)
        components_grid.attach(switch_container_corners, 1, 0, 1, 1)

        current_row = 0
        current_col = 0
        item_idx = 0
        for i, (name, display) in enumerate(component_display_names.items()):
            if item_idx < (rows_per_column - 1):
                row = item_idx + 1
                col = 0
            else:
                row = item_idx - (rows_per_column - 1)
                col = 2

            component_label = Label(label=display, h_align="start", v_align="center")
            components_grid.attach(component_label, col, row, 1, 1)

            switch_container = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
            )
            component_switch = Gtk.Switch(
                active=bind_vars.get(f"dock_{name}_visible", True)
            )
            switch_container.add(component_switch)
            components_grid.attach(switch_container, col + 1, row, 1, 1)
            self.component_switches[name] = component_switch
            item_idx += 1

        return scrolled_window

    def on_notification_position_changed(self, combo: Gtk.ComboBoxText):
        selected_text = combo.get_active_text()
        if selected_text:
            bind_vars[NOTIF_POS_KEY] = selected_text
            print(
                f"Notification position updated in bind_vars: {
                    bind_vars[NOTIF_POS_KEY]
                }"
            )

    def create_system_tab(self):
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False,
        )

        vbox = Box(orientation="v", spacing=15, style="margin: 15px;")
        scrolled_window.add(vbox)

        system_grid = Gtk.Grid()
        system_grid.set_column_spacing(20)
        system_grid.set_row_spacing(10)
        system_grid.set_margin_bottom(15)
        vbox.add(system_grid)

        terminal_header = Label(markup="<b>Terminal Settings</b>", h_align="start")
        system_grid.attach(terminal_header, 0, 0, 2, 1)
        terminal_label = Label(label="Command:", h_align="start", v_align="center")
        system_grid.attach(terminal_label, 0, 1, 1, 1)
        self.terminal_entry = Entry(
            text=bind_vars.get("terminal_command", "kitty -e"),
            tooltip_text="Command used to launch terminal apps (e.g., 'kitty -e')",
            h_expand=True,
        )
        system_grid.attach(self.terminal_entry, 1, 1, 1, 1)
        hint_label = Label(
            markup="<small>Examples: 'kitty -e', 'alacritty -e', 'foot -e'</small>",
            h_align="start",
        )
        system_grid.attach(hint_label, 0, 2, 2, 1)

        hypr_header = Label(markup="<b>Hyprland Integration</b>", h_align="start")
        system_grid.attach(hypr_header, 2, 0, 2, 1)
        row = 1
        self.lock_switch = None
        if self.show_lock_checkbox:
            lock_label = Label(
                label="Replace Hyprlock config", h_align="start", v_align="center"
            )
            system_grid.attach(lock_label, 2, row, 1, 1)
            lock_switch_container = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
            )
            self.lock_switch = Gtk.Switch(
                tooltip_text="Replace Hyprlock configuration with Ax-Shell's custom config"
            )
            lock_switch_container.add(self.lock_switch)
            system_grid.attach(lock_switch_container, 3, row, 1, 1)
            row += 1
        self.idle_switch = None
        if self.show_idle_checkbox:
            idle_label = Label(
                label="Replace Hypridle config", h_align="start", v_align="center"
            )
            system_grid.attach(idle_label, 2, row, 1, 1)
            idle_switch_container = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
            )
            self.idle_switch = Gtk.Switch(
                tooltip_text="Replace Hypridle configuration with Ax-Shell's custom config"
            )
            idle_switch_container.add(self.idle_switch)
            system_grid.attach(idle_switch_container, 3, row, 1, 1)
            row += 1
        if self.show_lock_checkbox or self.show_idle_checkbox:
            note_label = Label(
                markup="<small>Existing configs will be backed up</small>",
                h_align="start",
            )
            system_grid.attach(note_label, 2, row, 2, 1)

        metrics_header = Label(markup="<b>System Metrics Options</b>", h_align="start")
        vbox.add(metrics_header)
        metrics_grid = Gtk.Grid(
            column_spacing=15, row_spacing=8, margin_start=10, margin_top=5
        )
        vbox.add(metrics_grid)

        self.metrics_switches = {}
        metric_names = {
            "cpu": "CPU",
            "ram": "RAM",
            "swap": "Swap",
            "disk": "Disk",
            "gpu": "GPU",
        }

        metrics_grid.attach(Label(label="Show in Metrics", h_align="start"), 0, 0, 1, 1)
        for i, (key, label_text) in enumerate(metric_names.items()):
            switch = Gtk.Switch(
                active=bind_vars.get("metrics_visible", {}).get(key, True)
            )
            self.metrics_switches[key] = switch
            metrics_grid.attach(
                Label(label=label_text, h_align="start"), 0, i + 1, 1, 1
            )
            metrics_grid.attach(switch, 1, i + 1, 1, 1)

        def enforce_minimum_metrics(switch_dict):
            enabled_switches = [s for s in switch_dict.values() if s.get_active()]
            can_disable = len(enabled_switches) > 1
            for s in switch_dict.values():
                s.set_sensitive(True if can_disable or not s.get_active() else False)

        def on_metric_toggle(switch, gparam, switch_dict):
            enforce_minimum_metrics(switch_dict)

        for k_s, s_s in self.metrics_switches.items():
            s_s.connect("notify::active", on_metric_toggle, self.metrics_switches)
        enforce_minimum_metrics(self.metrics_switches)

        disks_label = Label(
            label="Disk directories for Metrics", h_align="start", v_align="center"
        )
        vbox.add(disks_label)
        self.disk_entries = Box(orientation="v", spacing=8, h_align="start")

        self._create_disk_edit_entry_func = lambda path: self._add_disk_entry_widget(
            path
        )

        for p in bind_vars.get("metrics_disks", ["/"]):
            self._create_disk_edit_entry_func(p)
        vbox.add(self.disk_entries)

        add_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )
        add_btn = Button(
            label="Add new disk",
            on_clicked=lambda _: self._create_disk_edit_entry_func("/"),
        )
        add_container.add(add_btn)
        vbox.add(add_container)

        return scrolled_window

    def _add_disk_entry_widget(self, path):
        """Helper para añadir una fila de entrada de disco al Box disk_entries."""
        bar = Box(orientation="h", spacing=10, h_align="start")
        entry = Entry(text=path, h_expand=True)
        bar.add(entry)
        x_btn = Button(label="X")
        x_btn.connect(
            "clicked",
            lambda _, current_bar_to_remove=bar: self.disk_entries.remove(
                current_bar_to_remove
            ),
        )
        bar.add(x_btn)
        self.disk_entries.add(bar)
        self.disk_entries.show_all()

    def create_about_tab(self):
        vbox = Box(orientation="v", spacing=18, style="margin: 30px;")
        vbox.add(
            Label(
                markup=f"<b>{APP_NAME_CAP}</b>",
                h_align="start",
                style="font-size: 1.5em; margin-bottom: 8px;",
            )
        )
        vbox.add(
            Label(
                label="A hackable shell for Hyprland, powered by Fabric.",
                h_align="start",
                style="margin-bottom: 12px;",
            )
        )
        repo_box = Box(orientation="h", spacing=6, h_align="start")
        repo_label = Label(label="GitHub:", h_align="start")
        repo_link = Label(
            markup='<a href="https://github.com/S4NKALP/Modus">https://github.com/S4NKALP/Modus</a>'
        )
        repo_box.add(repo_label)
        repo_box.add(repo_link)
        vbox.add(repo_box)

        # def on_kofi_clicked(_):
        #     import webbrowser

        #     webbrowser.open("https://github.com/S4NKALP")

        # kofi_btn = Button(
        #     label="Support on Ko-Fi ❤️",
        #     on_clicked=on_kofi_clicked,
        #     tooltip_text="Support S4NKALP on Ko-Fi",
        #     style="margin-top: 18px; min-width: 160px;",
        # )
        # vbox.add(kofi_btn)
        vbox.add(Box(v_expand=True))
        return vbox

    def on_ws_mode_changed(self, combo):
        mode = combo.get_active_text()
        is_numbers_mode = mode == "Numbers"
        self.ws_chinese_switch.set_sensitive(is_numbers_mode)
        if not is_numbers_mode:
            self.ws_chinese_switch.set_active(False)

    def on_ws_num_changed(self, switch, gparam):
        is_active = switch.get_active()
        self.ws_chinese_switch.set_sensitive(is_active)
        if not is_active:
            self.ws_chinese_switch.set_active(False)

    def on_position_changed(self, combo):
        position = combo.get_active_text()
        is_vertical = position in ["Left", "Right"]
        self.centered_switch.set_sensitive(is_vertical)
        if not is_vertical:
            self.centered_switch.set_active(False)

    def on_dock_enabled_changed(self, switch, gparam):
        is_active = switch.get_active()
        self.dock_hover_switch.set_sensitive(is_active)
        self.dock_auto_hide_switch.set_sensitive(is_active)
        if not is_active:
            self.dock_hover_switch.set_active(False)
            self.dock_auto_hide_switch.set_active(False)

    def on_select_face_icon(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Select Face Icon",
            transient_for=self.get_toplevel(),
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

    def on_accept(self, widget):
        current_bind_vars_snapshot = {}
        for prefix_key, suffix_key, prefix_entry, suffix_entry in self.entries:
            current_bind_vars_snapshot[prefix_key] = prefix_entry.get_text()
            current_bind_vars_snapshot[suffix_key] = suffix_entry.get_text()

        current_bind_vars_snapshot["wallpapers_dir"] = (
            self.wall_dir_chooser.get_filename()
        )

        current_bind_vars_snapshot["dock_position"] = (
            self.position_combo.get_active_text()
        )
        current_bind_vars_snapshot["vertical"] = current_bind_vars_snapshot[
            "dock_position"
        ] in ["Left", "Right"]

        current_bind_vars_snapshot["dock_enabled"] = self.dock_switch.get_active()
        current_bind_vars_snapshot["dock_auto_hide"] = (
            self.dock_auto_hide_switch.get_active()
        )
        current_bind_vars_snapshot["dock_always_occluded"] = (
            self.dock_hover_switch.get_active()
        )
        current_bind_vars_snapshot["dock_icon_size"] = int(
            self.icon_size_scale.get_value()
        )
        current_bind_vars_snapshot["window_switcher_items_per_row"] = int(
            self.window_switcher_scale.get_value()
        )
        current_bind_vars_snapshot["terminal_command"] = self.terminal_entry.get_text()
        current_bind_vars_snapshot["corners_visible"] = self.corners_switch.get_active()
        current_bind_vars_snapshot["dock_theme"] = (
            self.dock_theme_combo.get_active_text()
        )

        selected_notif_pos_text = self.notification_pos_combo.get_active_text()
        if selected_notif_pos_text:
            current_bind_vars_snapshot[NOTIF_POS_KEY] = selected_notif_pos_text
        else:
            current_bind_vars_snapshot[NOTIF_POS_KEY] = NOTIF_POS_DEFAULT

        for component_name, switch in self.component_switches.items():
            current_bind_vars_snapshot[f"dock_{component_name}_visible"] = (
                switch.get_active()
            )

        # Save workspace settings
        ws_mode = self.ws_mode_combo.get_active_text()
        current_bind_vars_snapshot["workspace_dots"] = ws_mode == "Dots"
        current_bind_vars_snapshot["workspace_nums"] = ws_mode == "Numbers"
        current_bind_vars_snapshot["workspace_use_chinese_numerals"] = (
            self.ws_chinese_switch.get_active()
        )

        current_bind_vars_snapshot["metrics_visible"] = {
            k: s.get_active() for k, s in self.metrics_switches.items()
        }
        current_bind_vars_snapshot["metrics_disks"] = [
            child.get_children()[0].get_text()
            for child in self.disk_entries.get_children()
            if isinstance(child, Gtk.Box)
            and child.get_children()
            and isinstance(child.get_children()[0], Entry)
        ]

        selected_icon_path = self.selected_face_icon
        replace_lock = self.lock_switch and self.lock_switch.get_active()
        replace_idle = self.idle_switch and self.idle_switch.get_active()

        if self.selected_face_icon:
            self.selected_face_icon = None
            self.face_status_label.label = ""

        def _apply_and_reload_task_thread():
            nonlocal current_bind_vars_snapshot

            from . import utils

            utils.bind_vars.clear()
            utils.bind_vars.update(current_bind_vars_snapshot)

            start_time = time.time()
            print(f"{start_time:.4f}: Background task started.")

            config_json = os.path.expanduser(f"~/{APP_NAME_CAP}/config/config.json")
            os.makedirs(os.path.dirname(config_json), exist_ok=True)
            try:
                with open(config_json, "w") as f:
                    json.dump(utils.bind_vars, f, indent=4)
                print(f"{time.time():.4f}: Saved config.json.")
            except Exception as e:
                print(f"Error saving config.json: {e}")

            if selected_icon_path:
                print(f"{time.time():.4f}: Processing face icon...")
                try:
                    img = Image.open(selected_icon_path)
                    side = min(img.size)
                    left = (img.width - side) // 2
                    top = (img.height - side) // 2
                    cropped_img = img.crop((left, top, left + side, top + side))
                    face_icon_dest = os.path.expanduser("~/.face.icon")
                    cropped_img.save(face_icon_dest, format="PNG")
                    print(f"{time.time():.4f}: Face icon saved to {face_icon_dest}")
                    GLib.idle_add(self._update_face_image_widget, face_icon_dest)
                except Exception as e:
                    print(f"Error processing face icon: {e}")
                print(f"{time.time():.4f}: Finished processing face icon.")

            if replace_lock:
                print(f"{time.time():.4f}: Replacing hyprlock config...")
                src = os.path.expanduser(f"~/{APP_NAME_CAP}/config/hypr/hyprlock.conf")
                dest = os.path.expanduser("~/.config/hypr/hyprlock.conf")
                if os.path.exists(src):
                    backup_and_replace(src, dest, "Hyprlock")
                else:
                    print(f"Warning: Source hyprlock config not found at {src}")
                print(f"{time.time():.4f}: Finished replacing hyprlock config.")

            if replace_idle:
                print(f"{time.time():.4f}: Replacing hypridle config...")
                src = os.path.expanduser(f"~/{APP_NAME_CAP}/config/hypr/hypridle.conf")
                dest = os.path.expanduser("~/.config/hypr/hypridle.conf")
                if os.path.exists(src):
                    backup_and_replace(src, dest, "Hypridle")
                else:
                    print(f"Warning: Source hypridle config not found at {src}")
                print(f"{time.time():.4f}: Finished replacing hypridle config.")

            print(
                f"{time.time():.4f}: Checking/Appending hyprland.conf source string..."
            )
            hypr_path = os.path.expanduser("~/.config/hypr/hyprland.conf")
            try:
                from .constants import SOURCE_STRING

                needs_append = True
                if os.path.exists(hypr_path):
                    with open(hypr_path, "r") as f:
                        if SOURCE_STRING.strip() in f.read():
                            needs_append = False
                else:
                    os.makedirs(os.path.dirname(hypr_path), exist_ok=True)

                if needs_append:
                    with open(hypr_path, "a") as f:
                        f.write("\n" + SOURCE_STRING)
                    print(f"Appended source string to {hypr_path}")
            except Exception as e:
                print(f"Error updating {hypr_path}: {e}")
            print(
                f"{time.time():.4f}: Finished checking/appending hyprland.conf source string."
            )

            print(f"{time.time():.4f}: Running start_config()...")
            start_config()
            print(f"{time.time():.4f}: Finished start_config().")

            print(f"{time.time():.4f}: Initiating Ax-Shell restart using Popen...")
            main_py = os.path.expanduser(f"~/{APP_NAME_CAP}/main.py")
            kill_cmd = f"killall {APP_NAME}"
            start_cmd = ["uwsm", "app", "--", "python", main_py]
            try:
                kill_proc = subprocess.Popen(
                    kill_cmd,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                kill_proc.wait(timeout=2)
                print(f"{time.time():.4f}: killall process finished (o timed out).")
            except subprocess.TimeoutExpired:
                print("Warning: killall command timed out.")
            except Exception as e:
                print(f"Error running killall: {e}")

            try:
                subprocess.Popen(
                    start_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                print(f"{APP_NAME_CAP} restart initiated via Popen.")
            except FileNotFoundError as e:
                print(f"Error restarting {APP_NAME_CAP}: Command not found ({e})")
            except Exception as e:
                print(f"Error restarting {APP_NAME_CAP} via Popen: {e}")

            print(f"{time.time():.4f}: Ax-Shell restart commands issued via Popen.")
            end_time = time.time()
            print(
                f"{end_time:.4f}: Background task finished (Total: {
                    end_time - start_time:.4f
                }s)."
            )

        thread = threading.Thread(target=_apply_and_reload_task_thread)
        thread.daemon = True
        thread.start()
        print("Configuration apply/reload task started in background.")

    def _update_face_image_widget(self, icon_path):
        try:
            if self.face_image and self.face_image.get_window():
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 64, 64)
                self.face_image.set_from_pixbuf(pixbuf)
        except Exception as e:
            print(f"Error reloading face icon preview: {e}")
            if self.face_image and self.face_image.get_window():
                self.face_image.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)
        return GLib.SOURCE_REMOVE

    def on_reset(self, widget):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Reset all settings to defaults?",
        )
        dialog.format_secondary_text(
            "This will reset all keybindings and appearance settings to their default values."
        )
        response = dialog.run()
        dialog.hide()  # Hide the dialog first
        dialog.destroy()  # Then destroy it

        # Process any pending events
        while Gtk.events_pending():
            Gtk.main_iteration()

        if response == Gtk.ResponseType.YES:
            from . import utils
            from .constants import DEFAULTS

            utils.bind_vars.clear()
            utils.bind_vars.update(DEFAULTS.copy())

            for prefix_key, suffix_key, prefix_entry, suffix_entry in self.entries:
                prefix_entry.set_text(utils.bind_vars[prefix_key])
                suffix_entry.set_text(utils.bind_vars[suffix_key])

            self.wall_dir_chooser.set_filename(utils.bind_vars["wallpapers_dir"])

            positions = ["Bottom", "Left", "Right"]
            default_position = DEFAULTS.get("dock_position", "Top")
            try:
                self.position_combo.set_active(positions.index(default_position))
            except ValueError:
                self.position_combo.set_active(0)

            self.dock_switch.set_active(utils.bind_vars.get("dock_enabled", True))
            self.dock_auto_hide_switch.set_active(
                utils.bind_vars.get("dock_auto_hide", False)
            )
            self.dock_hover_switch.set_active(
                utils.bind_vars.get("dock_always_occluded", False)
            )
            self.dock_hover_switch.set_sensitive(self.dock_switch.get_active())
            self.dock_auto_hide_switch.set_sensitive(self.dock_switch.get_active())
            self.terminal_entry.set_text(utils.bind_vars["terminal_command"])

            default_dock_theme_val = DEFAULTS.get("dock_theme", "Pills")
            try:
                self.dock_theme_combo.set_active(
                    self.themes.index(default_dock_theme_val)
                )
            except ValueError:
                self.dock_theme_combo.set_active(0)

            default_notif_pos_val = DEFAULTS.get(NOTIF_POS_KEY, NOTIF_POS_DEFAULT)
            notification_positions_list = ["Top", "Bottom"]
            try:
                self.notification_pos_combo.set_active(
                    notification_positions_list.index(default_notif_pos_val)
                )
            except ValueError:
                self.notification_pos_combo.set_active(0)

            for name, switch in self.component_switches.items():
                switch.set_active(utils.bind_vars.get(f"dock_{name}_visible", True))

            # Reset workspace settings
            default_dots = DEFAULTS.get("workspace_dots", True)
            default_nums = DEFAULTS.get("workspace_nums", False)
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

            self.ws_chinese_switch.set_active(
                utils.bind_vars.get("workspace_use_chinese_numerals", False)
            )
            self.ws_chinese_switch.set_sensitive(default_nums)
            self.corners_switch.set_active(utils.bind_vars.get("corners_visible", True))

            metrics_vis_defaults = DEFAULTS.get("metrics_visible", {})
            for k, s_widget in self.metrics_switches.items():
                s_widget.set_active(metrics_vis_defaults.get(k, True))

            def enforce_minimum_metrics(switch_dict):
                enabled_switches = [s for s in switch_dict.values() if s.get_active()]
                can_disable = len(enabled_switches) > 1
                for s in switch_dict.values():
                    s.set_sensitive(
                        True if can_disable or not s.get_active() else False
                    )

            enforce_minimum_metrics(self.metrics_switches)

            for child in list(self.disk_entries.get_children()):
                self.disk_entries.remove(child)

            for p in DEFAULTS.get("metrics_disks", ["/"]):
                self._add_disk_edit_entry_func(p)

            self._update_panel_position_sensitivity()

            self.selected_face_icon = None
            self.face_status_label.label = ""
            current_face = os.path.expanduser("~/.face.icon")
            try:
                pixbuf = (
                    GdkPixbuf.Pixbuf.new_from_file_at_size(current_face, 64, 64)
                    if os.path.exists(current_face)
                    else None
                )
                if pixbuf:
                    self.face_image.set_from_pixbuf(pixbuf)
                else:
                    self.face_image.set_from_icon_name("user-info", Gtk.IconSize.DIALOG)
            except Exception:
                self.face_image.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)

            if self.lock_switch:
                self.lock_switch.set_active(False)
            if self.idle_switch:
                self.idle_switch.set_active(False)
            # Add reset for icon size scale
            self.icon_size_scale.set_value(utils.bind_vars.get("dock_icon_size", 20))
            self.application_switcher_scale.set_value(utils.bind_vars.get("window_switcher_items_per_row", 13))
            print("Settings reset to defaults.")

    def on_close(self, widget):
        if self.application:
            self.application.quit()
        else:
            self.destroy()
