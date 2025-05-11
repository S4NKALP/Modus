import os
import shutil
import json
import sys
from pathlib import Path
import random
import subprocess
import toml
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

# Fabric imports
from fabric import Application
from fabric.widgets.window import Window
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.image import Image
from fabric.widgets.stack import Stack
from fabric.widgets.scale import Scale
from fabric.utils import exec_shell_command, exec_shell_command_async

# Assuming data.py exists in the same directory or is accessible via sys.path
# If data.py is in ./config/data.py relative to this script's original location:
try:
    # Adjust path relative to the *original* location if needed
    sys.path.insert(0, str(Path(__file__).resolve().parent / "../config"))
    from data import (
        APP_NAME,
        APP_NAME_CAP,
        WALLPAPERS_DIR_DEFAULT,
    )
except ImportError as e:
    print(f"Error importing data constants: {e}")
    # Provide fallback defaults if import fails
    APP_NAME = "modusv2"
    APP_NAME_CAP = "Modusv2"
    CONFIG_DIR = "~/Modusv2"
    HOME_DIR = "~"
    WALLPAPERS_DIR_DEFAULT = "~/Pictures/wallpapers"

SOURCE_STRING = f"""
# {APP_NAME_CAP}
source = ~/{APP_NAME_CAP}/config/hypr/{APP_NAME}.conf
"""

DEFAULTS = {
    "prefix_restart": "SHIFT ALT",
    "suffix_restart": "T",
    "prefix_bluetooth": "SHIFT ALT",
    "suffix_bluetooth": "B",
    "prefix_emoji": "SUPER",
    "suffix_emoji": "E",
    "prefix_cliphist": "SUPER",
    "suffix_cliphist": "V",
    "prefix_kanban": "SUPER",
    "suffix_kanban": "T",
    "prefix_toolbox": "SUPER",
    "suffix_toolbox": "S",
    "prefix_walls": "SUPER",
    "suffix_walls": "W",
    "prefix_launcher": "SUPER",
    "suffix_launcher": "D",
    "prefix_power": "SUPER",
    "suffix_power": "X",
    "prefix_tmux": "SUPER",
    "suffix_tmux": "Z",
    "prefix_notifications": "SUPER",
    "suffix_notifications": "N",
    "prefix_window_switcher": "ALT",
    "suffix_window_switcher": "W",
    "prefix_restart_inspector": "SUPER SHIFT",
    "suffix_restart_inspector": "T",
    "vertical": False,
    "vertical_right_align": True,
    "bottom_bar": False,
    "centered_bar": False,
    "terminal_command": "kitty -e",
    "wallpapers_dir": WALLPAPERS_DIR_DEFAULT,
    "dock_enabled": True,
    "dock_always_occluded": False,  # Added default
    "dock_icon_size": 28,
    "osd_enabled": True,  # Added default
    # Defaults for bar components (assuming True initially)
    "bar_button_app_visible": True,
    "bar_tray_visible": True,
    "bar_workspaces_visible": True,
    "bar_metrics_visible": True,
    "bar_language_visible": True,
    "bar_date_time_visible": True,
    "bar_updates_visible": True,
    "bar_indicators_visible": True,
    "corners_visible": True,  # Added default for corners visibility
    "bar_metrics_disks": ["/"],
    # Add metric visibility defaults
    "metrics_visible": {
        "cpu": True,
        "ram": True,
        "disk": True,
        "swap": True,
        "gpu": False,
    },
}

bind_vars = DEFAULTS.copy()


def deep_update(target: dict, update: dict) -> dict:
    """
    Recursively update a nested dictionary with values from another dictionary.
    """
    for key, value in update.items():
        if isinstance(value, dict):
            target[key] = deep_update(target.get(key, {}), value)
        else:
            target[key] = value
    return target


def ensure_matugen_config():
    """
    Ensure that the matugen configuration file exists and is updated
    with the expected settings.
    """
    expected_config = {
        "config": {
            "reload_apps": True,
            "wallpaper": {
                "command": "swww",
                "arguments": [
                    "img",
                    "-t",
                    "outer",
                    "--transition-duration",
                    "1.5",
                    "--transition-step",
                    "255",
                    "--transition-fps",
                    "60",
                    "-f",
                    "Nearest",
                ],
                "set": True,
            },
            "custom_colors": {
                "red": {"color": "#FF0000", "blend": True},
                "green": {"color": "#00FF00", "blend": True},
                "yellow": {"color": "#FFFF00", "blend": True},
                "blue": {"color": "#0000FF", "blend": True},
                "magenta": {"color": "#FF00FF", "blend": True},
                "cyan": {"color": "#00FFFF", "blend": True},
                "white": {"color": "#FFFFFF", "blend": True},
            },
        },
        "templates": {
            "hyprland": {
                "input_path": f"~/{APP_NAME_CAP}/config/matugen/templates/hyprland-colors.conf",
                "output_path": f"~/{APP_NAME_CAP}/config/hypr/colors.conf",
            },
            f"{APP_NAME}": {
                "input_path": f"~/{APP_NAME_CAP}/config/matugen/templates/{APP_NAME}.css",
                "output_path": f"~/{APP_NAME_CAP}/styles/colors.css",
                "post_hook": f"fabric-cli exec {APP_NAME} 'app.set_css()' &",
            },
        },
    }

    config_path = os.path.expanduser("~/.config/matugen/config.toml")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    # Load any existing configuration
    existing_config = {}
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            existing_config = toml.load(f)
        # Backup existing configuration
        shutil.copyfile(config_path, config_path + ".bak")

    # Merge configurations
    merged_config = deep_update(existing_config, expected_config)
    with open(config_path, "w") as f:
        toml.dump(merged_config, f)

    # Check if colors.css exists in styles directory
    colors_css_path = os.path.expanduser(f"~/{APP_NAME_CAP}/styles/colors.css")
    if not os.path.exists(colors_css_path):
        # Get the wallpapers directory from bind_vars or use default
        wallpapers_dir = bind_vars.get("wallpapers_dir", WALLPAPERS_DIR_DEFAULT)
        wallpapers_dir = os.path.expanduser(wallpapers_dir)

        # Get list of image files in the directory
        image_extensions = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
        image_files = [
            f
            for f in os.listdir(wallpapers_dir)
            if f.lower().endswith(image_extensions)
        ]

        if image_files:
            # Select a random image
            random_image = random.choice(image_files)
            image_path = os.path.join(wallpapers_dir, random_image)
            # Apply the random wallpaper using matugen
            os.system(f"matugen image {image_path}")
        else:
            # If no images found in user's directory, try the default directory
            default_dir = os.path.expanduser(f"~/{APP_NAME_CAP}/assets/wallpaper/")
            default_images = [
                f
                for f in os.listdir(default_dir)
                if f.lower().endswith(image_extensions)
            ]

            random_image = random.choice(default_images)
            image_path = os.path.join(default_dir, random_image)
            os.system(f"matugen image {image_path}")


def load_bind_vars():
    """
    Load saved key binding variables from JSON, if available.
    """
    config_json = os.path.expanduser(f"~/{APP_NAME_CAP}/config/assets/config.json")
    if os.path.exists(config_json):
        try:
            with open(config_json, "r") as f:
                saved_vars = json.load(f)
                # Update defaults with saved values, ensuring all keys exist
                for key in DEFAULTS:
                    if key in saved_vars:
                        bind_vars[key] = saved_vars[key]
                    else:
                        bind_vars[key] = DEFAULTS[
                            key
                        ]  # Use default if missing in saved
                # Add any new keys from DEFAULTS not present in saved_vars
                for key in saved_vars:
                    if key not in bind_vars:
                        bind_vars[key] = saved_vars[
                            key
                        ]  # Keep saved if it's not in new defaults (less likely)
                for vis_key in ["metrics_visible"]:
                    if vis_key in DEFAULTS:
                        if vis_key not in bind_vars or not isinstance(
                            bind_vars[vis_key], dict
                        ):
                            bind_vars[vis_key] = DEFAULTS[vis_key].copy()
                        else:
                            for m in DEFAULTS[vis_key]:
                                if m not in bind_vars[vis_key]:
                                    bind_vars[vis_key][m] = DEFAULTS[vis_key][m]
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {config_json}. Using defaults.")
            bind_vars.update(DEFAULTS)  # Ensure defaults on error
        except Exception as e:
            print(f"Error loading config from {config_json}: {e}. Using defaults.")
            bind_vars.update(DEFAULTS)  # Ensure defaults on error
    else:
        # Ensure defaults are set if file doesn't exist
        bind_vars.update(DEFAULTS)


def generate_hyprconf() -> str:
    """
    Generate the Hypr configuration string using the current bind_vars.
    """
    home = os.path.expanduser("~")
    return f"""# Generated by {APP_NAME_CAP} - DO NOT EDIT MANUALLY
exec-once = python {home}/{APP_NAME_CAP}/main.py
exec = pgrep -x "hypridle" > /dev/null || hypridle
exec = swww-daemon
exec-once = wl-paste --type text --watch cliphist store
exec-once = wl-paste --type image --watch cliphist store

$fabricSend = fabric-cli exec {APP_NAME}
$scriptsDir = {home}/{APP_NAME_CAP}/config/scripts/

# Key Bindings
bind = {bind_vars["prefix_restart"]}, {bind_vars["suffix_restart"]}, exec, killall {APP_NAME}; python {home}/{APP_NAME_CAP}/main.py # Reload {APP_NAME_CAP}
bind = {bind_vars["prefix_bluetooth"]}, {bind_vars["suffix_bluetooth"]}, exec, $fabricSend 'launcher.open("bluetooth")' # Bluetooth
bind = {bind_vars["prefix_notifications"]}, {bind_vars["suffix_notifications"]}, exec, $fabricSend 'launcher.open("notification-center")' # Notifications
bind = {bind_vars["prefix_emoji"]}, {bind_vars["suffix_emoji"]}, exec, $fabricSend 'launcher.open("emoji")' # Emoji
bind = {bind_vars["prefix_cliphist"]}, {bind_vars["suffix_cliphist"]}, exec, $fabricSend 'launcher.open("cliphist")' # Clipboard History
bind = {bind_vars["prefix_kanban"]}, {bind_vars["suffix_kanban"]}, exec, $fabricSend 'launcher.open("kanban")' # Kanban
bind = {bind_vars["prefix_tmux"]}, {bind_vars["suffix_tmux"]}, exec, $fabricSend 'launcher.open("tmux")' # Tmux Manager
bind = {bind_vars["prefix_toolbox"]}, {bind_vars["suffix_toolbox"]}, exec, $fabricSend 'launcher.open("tools")' # Toolbox
bind = {bind_vars["prefix_walls"]}, {bind_vars["suffix_walls"]}, exec, $fabricSend 'launcher.open("wallpapers")' # Wallpaper Selector
bind = {bind_vars["prefix_launcher"]}, {bind_vars["suffix_launcher"]}, exec, $fabricSend 'launcher.open("launcher")' # App Launcher
bind = {bind_vars["prefix_window_switcher"]}, {bind_vars["suffix_window_switcher"]}, exec, $fabricSend 'launcher.open("window-switcher")' # Window Switcher
bind = {bind_vars["prefix_power"]}, {bind_vars["suffix_power"]}, exec, $fabricSend 'launcher.open("power")' # Power Menu
bind = {bind_vars["prefix_restart_inspector"]}, {bind_vars["suffix_restart_inspector"]}, exec, killall {APP_NAME}; GTK_DEBUG=interactive python {home}/{APP_NAME_CAP}/main.py # Restart with inspector

# Wallpapers directory: {bind_vars["wallpapers_dir"]}

# Source color scheme
source = {home}/{APP_NAME_CAP}/config/hypr/colors.conf

general {{
    col.active_border = 0xff$primary
    col.inactive_border = 0xff$surface
    gaps_in = 2
    gaps_out = 4
    border_size = 2
    layout = dwindle
}}

decoration {{
    blur {{
        enabled = yes
        size = 5
        passes = 3
        new_optimizations = yes
        contrast = 1
        brightness = 1
    }}
    rounding = 14
    shadow {{
        enabled = true
        range = 10
        render_power = 2
        color = rgba(0, 0, 0, 0.25)
    }}
}}

animations {{
    enabled = true
    # Animation curves
    bezier = linear, 0, 0, 1, 1
    bezier = md3_standard, 0.2, 0, 0, 1
    bezier = md3_decel, 0.05, 0.7, 0.1, 1
    bezier = md3_accel, 0.3, 0, 0.8, 0.15
    bezier = overshot, 0.05, 0.9, 0.1, 1.1
    bezier = crazyshot, 0.1, 1.5, 0.76, 0.92
    bezier = hyprnostretch, 0.05, 0.9, 0.1, 1.0
    bezier = menu_decel, 0.1, 1, 0, 1
    bezier = menu_accel, 0.38, 0.04, 1, 0.07
    bezier = easeInOutCirc, 0.85, 0, 0.15, 1
    bezier = easeOutCirc, 0, 0.55, 0.45, 1
    bezier = easeOutExpo, 0.16, 1, 0.3, 1
    bezier = softAcDecel, 0.26, 0.26, 0.15, 1
    bezier = md2, 0.4, 0, 0.2, 1

    animation = windows, 1, 3, md3_decel, popin 60%
    animation = windowsIn, 1, 3, md3_decel, popin 60%
    animation = windowsOut, 1, 3, md3_accel, popin 60%
    animation = border, 1, 10, default
    animation = fade, 1, 3, md3_decel
    animation = layers, 1, 2, md3_decel, slide
    animation = layersIn, 1, 3, menu_decel, slide
    animation = layersOut, 1, 1.6, menu_accel, slide
    animation = fadeLayersIn, 1, 2, menu_decel
    animation = fadeLayersOut, 1, 4.5, menu_accel
    animation = workspaces, 1, 7, menu_decel, slide
    animation = specialWorkspace, 1, 3, md3_decel, slidevert
}}
"""


def backup_and_replace(src: str, dest: str, config_name: str):
    """
    Backup the existing configuration file and replace it with a new one.
    """
    if os.path.exists(dest):
        backup_path = dest + ".bak"
        shutil.copy(dest, backup_path)
        print(f"{config_name} config backed up to {backup_path}")
    shutil.copy(src, dest)
    print(f"{config_name} config replaced from {src}")


class HyprConfGUI(Window):
    def __init__(self, show_lock_checkbox: bool, show_idle_checkbox: bool, **kwargs):
        super().__init__(
            title="Modus Settings",
            name="modus-settings-widnow",
            size=(650, 550),
            **kwargs,
        )
        self.set_resizable(False)

        self.show_lock_checkbox = show_lock_checkbox
        self.show_idle_checkbox = show_idle_checkbox

        # Overall vertical box to hold the main content and bottom buttons
        root_box = Box(orientation="v", spacing=10, style="margin: 10px;")
        self.add(root_box)

        # Main horizontal box for switcher and stack
        main_content_box = Box(orientation="h", spacing=6, v_expand=True, h_expand=True)
        root_box.add(main_content_box)

        # --- Tab Control ---
        self.tab_stack = Stack(
            transition_type="slide-up-down",  # Change transition for vertical feel
            transition_duration=250,
            v_expand=True,
            h_expand=True,
        )

        # Create tabs and add to stack
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
        self.tab_stack.add_titled(
            self.about_tab_content, "about", "About"
        )  # Add About tab to stack

        # Use Gtk.StackSwitcher vertically on the left
        tab_switcher = Gtk.StackSwitcher()
        tab_switcher.set_stack(self.tab_stack)
        tab_switcher.set_orientation(
            Gtk.Orientation.VERTICAL
        )  # Set vertical orientation
        # Optional: Adjust alignment if needed
        # tab_switcher.set_valign(Gtk.Align.START)

        # Add switcher to the left of the main content box
        main_content_box.add(tab_switcher)

        # Add stack to the right of the main content box
        main_content_box.add(self.tab_stack)

        # --- Bottom Buttons ---
        button_box = Box(orientation="h", spacing=10, h_align="end")

        reset_btn = Button(label="Reset to Defaults", on_clicked=self.on_reset)
        button_box.add(reset_btn)

        # Add Close button back
        close_btn = Button(label="Close", on_clicked=self.on_close)
        button_box.add(close_btn)

        accept_btn = Button(label="Apply & Reload", on_clicked=self.on_accept)
        button_box.add(accept_btn)

        # Add button box to the bottom of the root box
        root_box.add(button_box)

    def create_key_bindings_tab(self):
        """Create tab for key bindings configuration using Fabric widgets and Gtk.Grid."""
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
        )
        # Remove fixed height constraints to allow stack to fill space
        scrolled_window.set_min_content_height(300)
        scrolled_window.set_max_content_height(300)

        # Main container with padding
        main_vbox = Box(orientation="v", spacing=10, style="margin: 15px;")
        scrolled_window.add(main_vbox)

        # Create a grid for key bindings
        keybind_grid = Gtk.Grid()
        keybind_grid.set_column_spacing(10)
        keybind_grid.set_row_spacing(8)
        keybind_grid.set_margin_start(5)
        keybind_grid.set_margin_end(5)
        keybind_grid.set_margin_top(5)
        keybind_grid.set_margin_bottom(5)

        # Header Row
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
            ("Bluetooth", "prefix_bluetooth", "suffix_bluetooth"),
            ("Notifications", "prefix_notifications", "suffix_notifications"),
            ("Kanban", "prefix_kanban", "suffix_kanban"),
            ("App Launcher", "prefix_launcher", "suffix_launcher"),
            ("Tmux", "prefix_tmux", "suffix_tmux"),
            ("Toolbox", "prefix_toolbox", "suffix_toolbox"),
            ("Wallpapers", "prefix_walls", "suffix_walls"),
            ("Emoji Picker", "prefix_emoji", "suffix_emoji"),
            ("Clipboard History", "prefix_cliphist", "suffix_cliphist"),
            ("Window Switcher", "prefix_window_switcher", "suffix_window_switcher"),
            ("Power Menu", "prefix_power", "suffix_power"),
            (
                "Restart with inspector",
                "prefix_restart_inspector",
                "suffix_restart_inspector",
            ),
        ]

        # Populate the grid with entries
        for i, (label_text, prefix_key, suffix_key) in enumerate(bindings):
            row = i + 1  # Start at row 1 after headers

            # Action label
            binding_label = Label(label=label_text, h_align="start")
            keybind_grid.attach(binding_label, 0, row, 1, 1)

            # Prefix entry
            prefix_entry = Entry(text=bind_vars[prefix_key])
            keybind_grid.attach(prefix_entry, 1, row, 1, 1)

            # Plus separator
            plus_label = Label(label="+", h_align="center")
            keybind_grid.attach(plus_label, 2, row, 1, 1)

            # Suffix entry
            suffix_entry = Entry(text=bind_vars[suffix_key])
            keybind_grid.attach(suffix_entry, 3, row, 1, 1)

            self.entries.append((prefix_key, suffix_key, prefix_entry, suffix_entry))

        main_vbox.add(keybind_grid)
        return scrolled_window

    def create_appearance_tab(self):
        """Create tab for appearance settings using Fabric widgets and Gtk.Grid."""
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
        )
        scrolled_window.set_min_content_height(300)
        scrolled_window.set_max_content_height(300)

        # Main container with padding
        vbox = Box(orientation="v", spacing=15, style="margin: 15px;")
        scrolled_window.add(vbox)

        # === WALLPAPERS SECTION ===
        wall_header = Label(markup="<b>Wallpapers</b>", h_align="start")
        vbox.add(wall_header)

        wall_box = Box(orientation="h", spacing=10, style="margin-left: 10px;")
        vbox.add(wall_box)

        wall_label = Label(label="Directory:", h_align="start", v_align="center")
        wall_box.add(wall_label)

        self.wall_dir_chooser = Gtk.FileChooserButton(
            title="Select a folder", action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        self.wall_dir_chooser.set_tooltip_text(
            "Select the directory containing your wallpaper images"
        )
        self.wall_dir_chooser.set_filename(bind_vars["wallpapers_dir"])
        self.wall_dir_chooser.set_size_request(180, -1)
        wall_box.add(self.wall_dir_chooser)

        # === LAYOUT OPTIONS SECTION ===
        layout_header = Label(markup="<b>Layout Options</b>", h_align="start")
        vbox.add(layout_header)

        # Create a grid for layout options
        layout_grid = Gtk.Grid()
        layout_grid.set_column_spacing(20)
        layout_grid.set_row_spacing(15)
        layout_grid.set_margin_start(10)
        layout_grid.set_margin_top(5)
        layout_grid.set_margin_bottom(10)
        vbox.add(layout_grid)

        # Column 1 (Left)
        # Vertical Layout
        vertical_label = Label(
            label="Vertical Layout", h_align="start", v_align="center"
        )
        layout_grid.attach(vertical_label, 0, 0, 1, 1)

        vertical_switch_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vertical_switch_container.set_halign(Gtk.Align.START)
        vertical_switch_container.set_valign(Gtk.Align.CENTER)

        self.vertical_switch = Gtk.Switch()
        self.vertical_switch.set_active(bind_vars.get("vertical", False))
        self.vertical_switch.connect("notify::active", self.on_vertical_changed)
        vertical_switch_container.add(self.vertical_switch)

        layout_grid.attach(vertical_switch_container, 1, 0, 1, 1)

        # Vertical Right Align (new)
        vertical_right_label = Label(
            label="Right Side (Vertical)", h_align="start", v_align="center"
        )
        layout_grid.attach(vertical_right_label, 0, 1, 1, 1)

        vertical_right_switch_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL
        )
        vertical_right_switch_container.set_halign(Gtk.Align.START)
        vertical_right_switch_container.set_valign(Gtk.Align.CENTER)

        self.vertical_right_switch = Gtk.Switch()
        self.vertical_right_switch.set_active(
            bind_vars.get("vertical_right_align", True)
        )
        self.vertical_right_switch.set_sensitive(self.vertical_switch.get_active())
        vertical_right_switch_container.add(self.vertical_right_switch)
        layout_grid.attach(vertical_right_switch_container, 1, 1, 1, 1)

        # Bottom Layout
        bottom_bar_label = Label(
            label="Bottom Layout", h_align="start", v_align="center"
        )
        layout_grid.attach(bottom_bar_label, 0, 2, 1, 1)

        bottom_bar_switch_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bottom_bar_switch_container.set_halign(Gtk.Align.START)
        bottom_bar_switch_container.set_valign(Gtk.Align.CENTER)

        self.bottom_bar_switch = Gtk.Switch()
        self.bottom_bar_switch.set_active(bind_vars.get("bottom_bar", False))
        self.bottom_bar_switch.connect("notify::active", self.on_bottom_bar_changed)
        bottom_bar_switch_container.add(self.bottom_bar_switch)
        layout_grid.attach(bottom_bar_switch_container, 1, 2, 1, 1)

        # Dock Options
        dock_label = Label(label="Show Dock", h_align="start", v_align="center")
        layout_grid.attach(dock_label, 0, 3, 1, 1)

        dock_switch_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        dock_switch_container.set_halign(Gtk.Align.START)
        dock_switch_container.set_valign(Gtk.Align.CENTER)

        self.dock_switch = Gtk.Switch()
        self.dock_switch.set_active(bind_vars.get("dock_enabled", True))
        self.dock_switch.connect("notify::active", self.on_dock_enabled_changed)
        dock_switch_container.add(self.dock_switch)
        layout_grid.attach(dock_switch_container, 1, 3, 1, 1)

        # Column 2 (Right)
        # Centered Bar
        centered_label = Label(
            label="Centered Bar (Vertical Only)", h_align="start", v_align="center"
        )
        layout_grid.attach(centered_label, 2, 0, 1, 1)

        centered_switch_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        centered_switch_container.set_halign(Gtk.Align.START)
        centered_switch_container.set_valign(Gtk.Align.CENTER)

        self.centered_switch = Gtk.Switch()
        self.centered_switch.set_active(bind_vars.get("centered_bar", False))
        self.centered_switch.set_sensitive(self.vertical_switch.get_active())
        centered_switch_container.add(self.centered_switch)
        layout_grid.attach(centered_switch_container, 3, 0, 1, 1)

        # Dock Hover
        dock_hover_label = Label(
            label="Show Dock Only on Hover", h_align="start", v_align="center"
        )
        layout_grid.attach(dock_hover_label, 2, 1, 1, 1)

        dock_hover_switch_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        dock_hover_switch_container.set_halign(Gtk.Align.START)
        dock_hover_switch_container.set_valign(Gtk.Align.CENTER)

        self.dock_hover_switch = Gtk.Switch()
        self.dock_hover_switch.set_active(bind_vars.get("dock_always_occluded", False))
        self.dock_hover_switch.set_sensitive(self.dock_switch.get_active())
        dock_hover_switch_container.add(self.dock_hover_switch)
        layout_grid.attach(dock_hover_switch_container, 3, 1, 1, 1)

        # Show OSD
        osd_label = Label(label="Show OSD", h_align="start", v_align="center")
        layout_grid.attach(osd_label, 2, 2, 1, 1)

        osd_hover_switch_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        osd_hover_switch_container.set_halign(Gtk.Align.START)
        osd_hover_switch_container.set_valign(Gtk.Align.CENTER)

        self.osd_switch = Gtk.Switch()
        self.osd_switch.set_active(bind_vars.get("osd_enabled", True))
        osd_hover_switch_container.add(self.osd_switch)
        layout_grid.attach(osd_hover_switch_container, 3, 2, 1, 1)

        # Dock Icon Size (Full width)
        dock_size_label = Label(
            label="Dock Icon Size", h_align="start", v_align="center"
        )
        layout_grid.attach(dock_size_label, 0, 4, 1, 1)

        self.dock_size_scale = Scale(
            min_value=16,
            max_value=48,
            value=bind_vars.get("dock_icon_size", 28),
            increments=(2, 4),
            draw_value=True,
            value_position="right",
            digits=0,
            h_expand=True,
        )
        layout_grid.attach(self.dock_size_scale, 1, 4, 3, 1)

        # === BAR COMPONENTS SECTION ===
        components_header = Label(markup="<b>Bar Components</b>", h_align="start")
        vbox.add(components_header)

        # Create a grid for bar components
        components_grid = Gtk.Grid()
        components_grid.set_column_spacing(15)
        components_grid.set_row_spacing(8)
        components_grid.set_margin_start(10)
        components_grid.set_margin_top(5)
        vbox.add(components_grid)

        self.component_switches = {}
        component_display_names = {
            "button_app": "App Launcher Button",
            "tray": "System Tray",
            "workspaces": "Workspaces",
            "metrics": "System Metrics",
            "language": "Language Indicator",
            "date_time": "Date & Time",
            "updates": "Update Indicator",
            "indicators": "System Indicators",
        }

        # Add corners visibility switch
        self.corners_switch = Gtk.Switch()
        self.corners_switch.set_active(bind_vars.get("corners_visible", True))

        # Calculate number of rows needed (we'll use 2 columns)
        num_components = len(component_display_names) + 1  # +1 for corners
        rows_per_column = (num_components + 1) // 2  # Ceiling division

        # First add corners to the top of first column
        corners_label = Label(
            label="Rounded Corners", h_align="start", v_align="center"
        )
        components_grid.attach(corners_label, 0, 0, 1, 1)

        switch_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        switch_container.set_halign(Gtk.Align.START)
        switch_container.set_valign(Gtk.Align.CENTER)
        switch_container.add(self.corners_switch)
        components_grid.attach(switch_container, 1, 0, 1, 1)

        # Add components to grid in two columns
        for i, (component_name, display_name) in enumerate(
            component_display_names.items()
        ):
            # Determine position: first half in column 0, second half in column 2
            # Start at row 1 to account for corners at row 0
            row = (i + 1) % rows_per_column  # +1 to start after corners
            col = 0 if i < (rows_per_column - 1) else 2  # Adjust column calculation

            component_label = Label(
                label=display_name, h_align="start", v_align="center"
            )
            components_grid.attach(component_label, col, row, 1, 1)

            # Container for switch to prevent stretching
            switch_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            switch_container.set_halign(Gtk.Align.START)
            switch_container.set_valign(Gtk.Align.CENTER)

            component_switch = Gtk.Switch()
            config_key = f"bar_{component_name}_visible"
            component_switch.set_active(bind_vars.get(config_key, True))
            switch_container.add(component_switch)

            components_grid.attach(switch_container, col + 1, row, 1, 1)

            self.component_switches[component_name] = component_switch

        return scrolled_window

    def create_system_tab(self):
        """Create tab for system configurations using Fabric widgets and Gtk.Grid."""
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
        )
        # Remove fixed height constraints
        scrolled_window.set_min_content_height(300)
        scrolled_window.set_max_content_height(300)

        # Main container with padding
        vbox = Box(orientation="v", spacing=15, style="margin: 15px;")
        scrolled_window.add(vbox)

        # Create a grid for system settings
        system_grid = Gtk.Grid()
        system_grid.set_column_spacing(20)
        system_grid.set_row_spacing(10)
        system_grid.set_margin_bottom(15)
        vbox.add(system_grid)

        # === TERMINAL SETTINGS ===
        terminal_header = Label(markup="<b>Terminal Settings</b>", h_align="start")
        system_grid.attach(terminal_header, 0, 0, 2, 1)

        terminal_label = Label(label="Command:", h_align="start", v_align="center")
        system_grid.attach(terminal_label, 0, 1, 1, 1)

        self.terminal_entry = Entry(
            text=bind_vars["terminal_command"],
            tooltip_text="Command used to launch terminal apps (e.g., 'kitty -e')",
            h_expand=True,
        )
        system_grid.attach(self.terminal_entry, 1, 1, 1, 1)

        hint_label = Label(
            markup="<small>Examples: 'kitty -e', 'alacritty -e', 'foot -e'</small>",
            h_align="start",
        )
        system_grid.attach(hint_label, 0, 2, 2, 1)

        # === HYPRLAND INTEGRATION ===
        hypr_header = Label(markup="<b>Hyprland Integration</b>", h_align="start")
        system_grid.attach(hypr_header, 2, 0, 2, 1)

        row = 1

        # Hyprland locks and idle settings
        self.lock_switch = None
        if self.show_lock_checkbox:
            lock_label = Label(
                label="Replace Hyprlock config", h_align="start", v_align="center"
            )
            system_grid.attach(lock_label, 2, row, 1, 1)

            # Container for switch to prevent stretching
            lock_switch_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            lock_switch_container.set_halign(Gtk.Align.START)
            lock_switch_container.set_valign(Gtk.Align.CENTER)

            self.lock_switch = Gtk.Switch()
            self.lock_switch.set_tooltip_text(
                "Replace Hyprlock configuration with Ax-Shell's custom config"
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

            # Container for switch to prevent stretching
            idle_switch_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            idle_switch_container.set_halign(Gtk.Align.START)
            idle_switch_container.set_valign(Gtk.Align.CENTER)

            self.idle_switch = Gtk.Switch()
            self.idle_switch.set_tooltip_text(
                "Replace Hypridle configuration with Ax-Shell's custom config"
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

        # --- System Metrics Options (moved from appearance tab) ---
        metrics_header = Label(markup="<b>System Metrics Options</b>", h_align="start")
        vbox.add(metrics_header)

        # Metrics visibility toggles
        metrics_grid = Gtk.Grid()
        metrics_grid.set_column_spacing(15)
        metrics_grid.set_row_spacing(8)
        metrics_grid.set_margin_start(10)
        metrics_grid.set_margin_top(5)
        vbox.add(metrics_grid)

        self.metrics_switches = {}

        metric_names = {
            "cpu": "CPU",
            "ram": "RAM",
            "disk": "Disk",
            "swap": "Swap",
            "gpu": "GPU",
        }

        # metrics toggles
        metrics_grid.attach(Label(label="Show in Metrics", h_align="start"), 2, 0, 1, 1)
        for i, (key, label) in enumerate(metric_names.items()):
            switch = Gtk.Switch()
            switch.set_active(bind_vars.get("metrics_visible", {}).get(key, True))
            self.metrics_switches[key] = switch
            metrics_grid.attach(Label(label=label, h_align="start"), 2, i + 1, 1, 1)
            metrics_grid.attach(switch, 4, i + 1, 1, 1)

        # Enforce minimum 4 enabled metrics
        def enforce_minimum_metrics(switch_dict):
            enabled = [k for k, s in switch_dict.items() if s.get_active()]
            for k, s in switch_dict.items():
                if len(enabled) <= 4 and s.get_active():
                    s.set_sensitive(False)
                else:
                    s.set_sensitive(True)

        def on_metric_toggle(switch, gparam, which):
            enforce_minimum_metrics(self.metrics_switches)

        for k, s in self.metrics_switches.items():
            s.connect("notify::active", on_metric_toggle, k)
        enforce_minimum_metrics(self.metrics_switches)

        # Disk directories
        disks_label = Label(label="Disk directories", h_align="start", v_align="center")
        vbox.add(disks_label)

        self.disk_entries = Box(orientation="v", spacing=8, h_align="start")

        def create_disk_edit(path):
            bar = Box(orientation="h", spacing=10, h_align="start")
            entry = Entry(text=path, h_expand=True)
            bar.add(entry)
            x = Button(label="X", on_clicked=lambda _: self.disk_entries.remove(bar))
            bar.add(x)
            self.disk_entries.add(bar)

        vbox.add(self.disk_entries)
        for path in bind_vars.get("bar_metrics_disks"):
            create_disk_edit(path)
        add_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        add_container.set_halign(Gtk.Align.START)
        add_container.set_valign(Gtk.Align.CENTER)
        add = Button(label="Add new disk", on_clicked=lambda _: create_disk_edit("/"))
        add_container.add(add)
        vbox.add(add_container)

        return scrolled_window

    def create_about_tab(self):
        """Create an About tab with project info, repo link, and Ko-Fi button."""
        vbox = Box(orientation="v", spacing=18, style="margin: 30px;")
        # Project title
        vbox.add(
            Label(
                markup=f"<b>{APP_NAME_CAP}</b>",
                h_align="start",
                style="font-size: 1.5em; margin-bottom: 8px;",
            )
        )
        # Description
        vbox.add(
            Label(
                label="A hackable shell for Hyprland, powered by Fabric.",
                h_align="start",
                style="margin-bottom: 12px;",
            )
        )
        # Repo link
        repo_box = Box(orientation="h", spacing=6, h_align="start")
        repo_label = Label(label="GitHub:", h_align="start")
        repo_link = Label()
        repo_link.set_markup(
            f'<a href="https://github.com/S4NKALP/Modus">https://github.com/S4NKALP/Modus</a>'
        )
        repo_box.add(repo_label)
        repo_box.add(repo_link)
        vbox.add(repo_box)

        # Ko-Fi button
        def on_kofi_clicked(_):
            import webbrowser

            webbrowser.open("https://ko-fi.com/S4NKALP")

        kofi_btn = Button(
            label="Support on Ko-Fi ❤️",
            on_clicked=on_kofi_clicked,
            tooltip_text="Support S4NKALP on Ko-Fi",
        )
        kofi_btn.set_style("margin-top: 18px; min-width: 160px;")
        vbox.add(kofi_btn)
        # Spacer
        vbox.add(Box(v_expand=True))
        return vbox

    def on_vertical_changed(self, switch, gparam):
        """Callback for vertical switch."""
        is_active = switch.get_active()
        self.centered_switch.set_sensitive(is_active)
        self.vertical_right_switch.set_sensitive(is_active)

        if is_active:
            # Disable bottom bar when vertical layout is enabled
            bind_vars["bottom_bar"] = False
            self.bottom_bar_switch.set_active(False)

    def on_dock_enabled_changed(self, switch, gparam):
        """Callback for dock enabled switch."""
        is_active = switch.get_active()
        self.dock_hover_switch.set_sensitive(is_active)
        if not is_active:
            self.dock_hover_switch.set_active(False)

    def on_bottom_bar_changed(self, switch, gparam):
        """Handle bottom bar switch changes"""
        bind_vars["bottom_bar"] = switch.get_active()
        if switch.get_active():
            # Disable vertical layout
            bind_vars["vertical"] = False
            self.vertical_switch.set_active(False)

            # Only disable centered bar without turning it off
            self.centered_switch.set_sensitive(False)

            # Disable right side option and reset it to False
            self.vertical_right_switch.set_sensitive(False)
            self.vertical_right_switch.set_active(False)
            bind_vars["vertical_right_align"] = False

    def on_accept(self, widget):
        """
        Save the configuration and update the necessary files without closing the window.
        """
        for prefix_key, suffix_key, prefix_entry, suffix_entry in self.entries:
            bind_vars[prefix_key] = prefix_entry.get_text()
            bind_vars[suffix_key] = suffix_entry.get_text()

        bind_vars["wallpapers_dir"] = self.wall_dir_chooser.get_filename()
        bind_vars["vertical"] = self.vertical_switch.get_active()
        bind_vars["vertical_right_align"] = self.vertical_right_switch.get_active()
        bind_vars["bottom_bar"] = self.bottom_bar_switch.get_active()
        bind_vars["enabled_osd"] = self.osd_switch.get_active()
        bind_vars["centered_bar"] = self.centered_switch.get_active()
        bind_vars["dock_enabled"] = self.dock_switch.get_active()
        bind_vars["dock_always_occluded"] = self.dock_hover_switch.get_active()
        bind_vars["dock_icon_size"] = int(self.dock_size_scale.get_value())
        bind_vars["terminal_command"] = self.terminal_entry.get_text()
        bind_vars["corners_visible"] = self.corners_switch.get_active()

        for component_name, switch in self.component_switches.items():
            config_key = f"bar_{component_name}_visible"
            bind_vars[config_key] = switch.get_active()

        # Save metrics visibility
        bind_vars["metrics_visible"] = {
            k: s.get_active() for k, s in self.metrics_switches.items()
        }

        bind_vars["bar_metrics_disks"] = []
        for entry in self.disk_entries.children:
            bind_vars["bar_metrics_disks"].append(entry.children[0].get_text())

        config_json = os.path.expanduser(f"~/{APP_NAME_CAP}/config/assets/config.json")
        os.makedirs(os.path.dirname(config_json), exist_ok=True)
        try:
            with open(config_json, "w") as f:
                json.dump(bind_vars, f, indent=4)
        except Exception as e:
            print(f"Error saving config.json: {e}")

        if self.lock_switch and self.lock_switch.get_active():
            src_lock = os.path.expanduser(f"~/{APP_NAME_CAP}/config/hypr/hyprlock.conf")
            dest_lock = os.path.expanduser("~/.config/hypr/hyprlock.conf")
            if os.path.exists(src_lock):
                backup_and_replace(src_lock, dest_lock, "Hyprlock")
            else:
                print(f"Warning: Source hyprlock config not found at {src_lock}")

        if self.idle_switch and self.idle_switch.get_active():
            src_idle = os.path.expanduser(f"~/{APP_NAME_CAP}/config/hypr/hypridle.conf")
            dest_idle = os.path.expanduser("~/.config/hypr/hypridle.conf")
            if os.path.exists(src_idle):
                backup_and_replace(src_idle, dest_idle, "Hypridle")
            else:
                print(f"Warning: Source hypridle config not found at {src_idle}")

        hyprland_config_path = os.path.expanduser("~/.config/hypr/hyprland.conf")
        try:
            needs_append = True
            if os.path.exists(hyprland_config_path):
                with open(hyprland_config_path, "r") as f:
                    content = f.read()
                    if SOURCE_STRING.strip() in content:
                        needs_append = False
            else:
                os.makedirs(os.path.dirname(hyprland_config_path), exist_ok=True)

            if needs_append:
                with open(hyprland_config_path, "a") as f:
                    f.write("\n" + SOURCE_STRING)
                print(f"Appended source string to {hyprland_config_path}")

        except Exception as e:
            print(f"Error updating {hyprland_config_path}: {e}")

        start_config()

        # Restart Modus using fabric's async command executor
        main_script_path = os.path.expanduser(f"~/{APP_NAME_CAP}/main.py")
        kill_cmd = f"killall {APP_NAME}"
        start_cmd = f"python {main_script_path}"

        try:
            # Use fabric's helper to run the command asynchronously
            exec_shell_command(kill_cmd)
            exec_shell_command_async(start_cmd)
            print(f"{APP_NAME_CAP} restart initiated.")
        except Exception as e:
            print(f"Error restarting {APP_NAME_CAP}: {e}")

    def on_reset(self, widget):
        """
        Reset all settings to default values. Uses Gtk.MessageDialog.
        """
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
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            global bind_vars
            bind_vars = DEFAULTS.copy()

            for prefix_key, suffix_key, prefix_entry, suffix_entry in self.entries:
                prefix_entry.set_text(bind_vars[prefix_key])
                suffix_entry.set_text(bind_vars[suffix_key])

            self.wall_dir_chooser.set_filename(bind_vars["wallpapers_dir"])
            self.vertical_switch.set_active(bind_vars.get("vertical", False))
            self.vertical_right_switch.set_active(
                bind_vars.get("vertical_right_align", True)
            )
            self.centered_switch.set_active(bind_vars.get("centered_bar", False))
            self.centered_switch.set_sensitive(self.vertical_switch.get_active())
            self.vertical_right_switch.set_sensitive(self.vertical_switch.get_active())
            self.dock_switch.set_active(bind_vars.get("dock_enabled", True))
            self.dock_hover_switch.set_active(
                bind_vars.get("dock_always_occluded", False)
            )
            self.dock_hover_switch.set_sensitive(self.dock_switch.get_active())
            self.dock_size_scale.value = bind_vars.get("dock_icon_size", 28)
            self.terminal_entry.set_text(bind_vars["terminal_command"])
            self.osd_switch.set_active(bind_vars.get("osd_enabled", True))
            self.bottom_bar_switch.set_active(bind_vars.get("bottom_bar", False))

            for component_name, switch in self.component_switches.items():
                config_key = f"bar_{component_name}_visible"
                switch.set_active(bind_vars.get(config_key, True))

            self.corners_switch.set_active(bind_vars.get("corners_visible", True))

            # Reset metrics visibility
            for k, s in self.metrics_switches.items():
                s.set_active(DEFAULTS["metrics_visible"][k])

            # Reset disk entries
            if True:
                for i in self.disk_entries.children:
                    self.disk_entries.remove(i)
                bar = Box(orientation="h", spacing=10, h_align="start")
                entry = Entry(text="/", h_expand=True)
                bar.add(entry)
                x = Button(
                    label="X", on_clicked=lambda _: self.disk_entries.remove(bar)
                )
                bar.add(x)
                self.disk_entries.add(bar)

            if self.lock_switch:
                self.lock_switch.set_active(False)
            if self.idle_switch:
                self.idle_switch.set_active(False)

            print("Settings reset to defaults.")

    def on_close(self, widget):
        """Close the settings window."""
        if self.application:
            self.application.quit()
        else:
            self.destroy()


def start_config():
    """
    Run final configuration steps: ensure necessary configs, write the hyprconf, and reload.
    """
    ensure_matugen_config()

    hypr_config_dir = os.path.expanduser(f"~/{APP_NAME_CAP}/config/hypr/")
    os.makedirs(hypr_config_dir, exist_ok=True)
    hypr_conf_path = os.path.join(hypr_config_dir, f"{APP_NAME}.conf")
    try:
        with open(hypr_conf_path, "w") as f:
            f.write(generate_hyprconf())
        print(f"Generated Hyprland config at {hypr_conf_path}")
    except Exception as e:
        print(f"Error writing Hyprland config: {e}")

    try:
        subprocess.run(["hyprctl", "reload"], check=True, capture_output=True)
        print("Hyprland configuration reloaded.")
    except subprocess.CalledProcessError as e:
        print(f"Error reloading Hyprland: {e}\nstderr: {e.stderr.decode()}")
    except FileNotFoundError:
        print("Error: hyprctl command not found. Cannot reload Hyprland.")
    except Exception as e:
        print(f"An unexpected error occurred during hyprctl reload: {e}")


def open_config():
    """
    Entry point for opening the configuration GUI using Fabric Application.
    """
    load_bind_vars()

    dest_lock = os.path.expanduser("~/.config/hypr/hyprlock.conf")
    src_lock = os.path.expanduser(f"~/{APP_NAME_CAP}/config/hypr/hyprlock.conf")
    show_lock_checkbox = True
    if not os.path.exists(dest_lock) and os.path.exists(src_lock):
        try:
            os.makedirs(os.path.dirname(dest_lock), exist_ok=True)
            shutil.copy(src_lock, dest_lock)
            show_lock_checkbox = False
            print(f"Copied default hyprlock config to {dest_lock}")
        except Exception as e:
            print(f"Error copying default hyprlock config: {e}")
            show_lock_checkbox = os.path.exists(src_lock)

    dest_idle = os.path.expanduser("~/.config/hypr/hypridle.conf")
    src_idle = os.path.expanduser(f"~/{APP_NAME_CAP}/config/hypr/hypridle.conf")
    show_idle_checkbox = True
    if not os.path.exists(dest_idle) and os.path.exists(src_idle):
        try:
            os.makedirs(os.path.dirname(dest_idle), exist_ok=True)
            shutil.copy(src_idle, dest_idle)
            show_idle_checkbox = False
            print(f"Copied default hypridle config to {dest_idle}")
        except Exception as e:
            print(f"Error copying default hypridle config: {e}")
            show_idle_checkbox = os.path.exists(src_idle)

    app = Application(f"{APP_NAME}-settings")
    window = HyprConfGUI(
        show_lock_checkbox=show_lock_checkbox,
        show_idle_checkbox=show_idle_checkbox,
        application=app,
        on_destroy=lambda *_: app.quit(),
    )
    app.add_window(window)

    window.show_all()
    app.run()


if __name__ == "__main__":
    open_config()
