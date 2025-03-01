import os
import json
import shutil
import gi
import subprocess
from concurrent.futures import ThreadPoolExecutor

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


# Constants
SOURCE_STRING = """
# Modus
source = ~/Modus/config/hypr/modus.conf
"""

CONFIG_DIR = os.path.expanduser("~/Modus")
WALLPAPERS_DIR_DEFAULT = os.path.expanduser("~/Modus/assets/wallpaper")

# Default key binding values
bind_vars = {
    "prefix_restart": "SHIFT ALT",
    "suffix_restart": "T",
    "prefix_bluetooth": "ALT",
    "suffix_bluetooth": "B",
    "prefix_emoji": "SUPER",
    "suffix_emoji": "E",
    "prefix_cliphist": "SUPER",
    "suffix_cliphist": "V",
    "prefix_todo": "SUPER",
    "suffix_todo": "T",
    "prefix_sh": "SUPER",
    "suffix_sh": "S",
    "prefix_walls": "SUPER",
    "suffix_walls": "W",
    "prefix_screenshotregion": "SUPER",
    "suffix_screenshotregion": "Z",
    "prefix_screenshot": "",
    "suffix_screenshot": "Print",
    "prefix_screencast": "SUPER",
    "suffix_screencast": "R",
    "prefix_launcher": "SUPER",
    "suffix_launcher": "D",
    "prefix_power": "SUPER",
    "suffix_power": "X",
    "prefix_wifi": "SUPER",
    "suffix_wifi": "N",
    "prefix_toggle": "SUPER",
    "suffix_toggle": "H",
    "prefix_randomwallpaper": "ALT SHIFT",
    "suffix_randomwallpaper": "W",
    "wallpapers_dir": WALLPAPERS_DIR_DEFAULT,
}


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


def parallel_subprocesses(commands):
    """
    Run multiple subprocess commands in parallel.
    """
    with ThreadPoolExecutor() as executor:
        executor.map(subprocess.run, commands)


def setup_colors():
    subprocess.run(
        [
            "python",
            "-O",
            os.path.expanduser("~/Modus/config/material-colors/generate.py"),
            "--color",
            "#0000FF",
        ]
    )


def setup_sddm():
    commands = [
        ["sudo", "mkdir", "-p", "/etc/sddm.conf.d"],
        [
            "sudo",
            "cp",
            os.path.expanduser("~/Modus/config/sddm/sddm.conf"),
            "/etc/sddm.conf.d/",
        ],
        [
            "sudo",
            "cp",
            os.path.expanduser("~/Modus/config/sddm/sddm.conf"),
            "/etc/",
        ],
        ["sudo", "chmod", "644", "/etc/sddm.conf.d/sddm.conf"],
        ["sudo", "chmod", "644", "/etc/sddm.conf"],
        ["sudo", "chmod", "-R", "755", "/usr/share/sddm/themes/corners/"],
    ]
    parallel_subprocesses(commands)
    subprocess.run([os.path.expanduser("~/Modus/config/sddm/scripts/wallpaper.sh")])


def copy_wallpapers():
    dest_wallpaper_dir = os.path.expanduser("~/Pictures/wallpaper")
    src_wallpaper_dir = os.path.expanduser("~/Modus/assets/wallpaper")
    if not os.path.exists(dest_wallpaper_dir):
        shutil.copytree(src_wallpaper_dir, dest_wallpaper_dir, dirs_exist_ok=True)
    subprocess.run(
        [
            "python",
            os.path.expanduser("~/Modus/config/scripts/wallpaper.py"),
            "-I",
            os.path.join(dest_wallpaper_dir, "example-1.jpg"),
        ]
    )


def load_bind_vars():
    """
    Load saved key binding variables from JSON, if available.
    """
    config_json = os.path.expanduser("~/Modus/config/assets/config.json")
    try:
        with open(config_json, "r") as f:
            saved_vars = json.load(f)
            bind_vars.update(saved_vars)
    except FileNotFoundError:
        # Use default values if no saved config exists
        pass


def generate_hyprconf() -> str:
    """
    Generate the Hypr configuration string using the current bind_vars.
    """
    home = os.path.expanduser("~")
    return f"""exec-once = python {home}/Modus/main.py
exec = pgrep -x "hypridle" > /dev/null || hypridle
exec = swww-daemon
exec-once = wl-paste --type text --watch cliphist store
exec-once = wl-paste --type image --watch cliphist store

$fabricSend = fabric-cli exec modus
$scriptsDir = $HOME/Modus/config/scripts/

bind = {bind_vars["prefix_restart"]}, {bind_vars["suffix_restart"]}, exec, killall modus; python {home}/Modus/main.py # Reload Modus | Default: SUPER ALT + T
bind = {bind_vars["prefix_bluetooth"]}, {bind_vars["suffix_bluetooth"]}, exec, $fabricSend 'launcher.open("bluetooth")' # Bluetooth | Default: ALT + B
bind = {bind_vars["prefix_wifi"]}, {bind_vars["suffix_wifi"]}, exec, $fabricSend 'launcher.open("wifi")' # Wifi | Default: SUPER + N
bind = {bind_vars["prefix_emoji"]}, {bind_vars["suffix_emoji"]}, exec, $fabricSend 'launcher.open("emoji")' # Emoji | Default: SUPER + E
bind = {bind_vars["prefix_cliphist"]}, {bind_vars["suffix_cliphist"]}, exec, $fabricSend 'launcher.open("cliphist")' # Cliphist | Default: SUPER + V
bind = {bind_vars["prefix_todo"]}, {bind_vars["suffix_todo"]}, exec, $fabricSend 'launcher.open("todo")' # Todo | Default: SUPER + T
bind = {bind_vars["prefix_sh"]}, {bind_vars["suffix_sh"]}, exec, $fabricSend 'launcher.open("sh")' # Sh | Default: SUPER + S
bind = {bind_vars["prefix_walls"]}, {bind_vars["suffix_walls"]}, exec, $fabricSend 'launcher.open("wallpapers")' # Wallpaper Selector | Default: SUPER + W
bind ={bind_vars["prefix_randomwallpaper"]}, {bind_vars["suffix_randomwallpaper"]}, exec, python -O $scriptsDir/wallpaper.py -R # Random Wallpaper | Default: ALT SHIFT + W
bind = {bind_vars["prefix_launcher"]}, {bind_vars["suffix_launcher"]}, exec, $fabricSend 'launcher.open("launcher")' # App Launcher | Default: SUPER + D
bind = {bind_vars["prefix_power"]}, {bind_vars["suffix_power"]}, exec, $fabricSend 'launcher.open("power")' # Power Menu | Default: SUPER + X
bind = {bind_vars["prefix_toggle"]}, {bind_vars["suffix_toggle"]}, exec, $fabricSend 'bar.toggle_hidden()' # Toggle Bar | Default: SUPER + H
bind = {bind_vars["prefix_screenshotregion"]}, {bind_vars["suffix_screenshotregion"]}, exec, $fabricSend 'sc.screenshot()' # Screenshot Region | Default: SUPER + Z
bind = {bind_vars["prefix_screenshot"]}, {bind_vars["suffix_screenshot"]}, exec, $fabricSend 'sc.screenshot(True)' # ScreenshotFullScreen | Default: Print
bind = {bind_vars["prefix_screencast"]}, {bind_vars["suffix_screencast"]}, exec, $fabricSend 'sc.screencast_start()' # Screencast | Default: SUPER + R


# Wallpapers directory: {bind_vars["wallpapers_dir"]}

general {{
    gaps_in = 2
    gaps_out = 4
    border_size = 0
    layout = dwindle
}}

decoration {{
    blur {{
        enabled = false
    }}
    rounding = 15
    active_opacity = 1
    inactive_opacity = 1
    fullscreen_opacity = 1

    dim_inactive = true
    dim_strength = 0.1
    dim_special = 0.8
    shadow {{
      enabled = false
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
    bezier = md2, 0.4, 0, 0.2, 1 # use with .2s duration
    # Animation configs
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
    # animation = workspaces, 1, 2.5, softAcDecel, slide
    # animation = workspaces, 1, 7, menu_decel, slidefade 15%
    # animation = specialWorkspace, 1, 3, md3_decel, slidefadevert 15%
    animation = specialWorkspace, 1, 3, md3_decel, slidevert
}}
"""


def backup_and_replace(src: str, dest: str, config_name: str):
    """
    Backup the existing configuration file and replace it with a new one.
    """
    if os.path.exists(dest):
        backup_path = dest + ".bak"
        if not os.path.exists(backup_path):
            shutil.copy(dest, backup_path)
            print(f"{config_name} config backed up to {backup_path}")
    shutil.copy(src, dest)
    print(f"{config_name} config replaced from {src}")


class HyprConfGUI(Gtk.Window):
    def __init__(self, show_lock_checkbox: bool, show_idle_checkbox: bool):
        super().__init__(title="Configure Key Binds")
        self.set_border_width(20)
        self.set_default_size(500, 450)
        self.set_resizable(False)

        self.selected_face_icon = None

        # Main container
        main_vbox = Gtk.VBox(spacing=10)
        self.add(main_vbox)

        # Create input entries for key bindings
        self.entries = []
        bindings = [
            ("Reload Modus", "prefix_restart", "suffix_restart"),
            ("Bluetooth", "prefix_bluetooth", "suffix_bluetooth"),
            ("Wallpaper Selector", "prefix_walls", "suffix_walls"),
            ("Random Wallpaper", "prefix_randomwallpaper", "suffix_randomwallpaper"),
            ("App Launcher", "prefix_launcher", "suffix_launcher"),
            ("Power Menu", "prefix_power", "suffix_power"),
            ("Emoji Selector", "prefix_emoji", "suffix_emoji"),
            ("Clipboard History", "prefix_cliphist", "suffix_cliphist"),
            ("Screenshot", "prefix_screenshot", "suffix_screenshot"),
            ("ScreenRecorder", "prefix_screencast", "suffix_screencast"),
            ("Screenshot Region", "prefix_screenshotregion", "suffix_screenshotregion"),
            ("Sh runner", "prefix_sh", "suffix_sh"),
            ("Todo List", "prefix_todo", "suffix_todo"),
            ("Toggle Bar", "prefix_toggle", "suffix_toggle"),
        ]

        for label_text, prefix_key, suffix_key in bindings:
            entry_box = Gtk.HBox(spacing=10)

            label = Gtk.Label(label=label_text)
            entry_box.pack_start(label, False, False, 0)

            prefix_entry = Gtk.Entry()
            prefix_entry.set_text(bind_vars[prefix_key])
            entry_box.pack_start(prefix_entry, True, True, 0)

            plus_label = Gtk.Label(label=" + ")
            entry_box.pack_start(plus_label, False, False, 0)

            suffix_entry = Gtk.Entry()
            suffix_entry.set_text(bind_vars[suffix_key])
            entry_box.pack_start(suffix_entry, True, True, 0)

            main_vbox.pack_start(entry_box, False, False, 0)
            self.entries.append((prefix_key, suffix_key, prefix_entry, suffix_entry))

        # Wallpaper directory chooser
        wall_box = Gtk.HBox(spacing=10)
        wall_label = Gtk.Label(label="Wallpapers Directory")
        wall_box.pack_start(wall_label, False, False, 0)
        self.wall_dir_chooser = Gtk.FileChooserButton(
            title="Select a folder", action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        self.wall_dir_chooser.set_filename(bind_vars["wallpapers_dir"])
        wall_box.pack_start(self.wall_dir_chooser, True, True, 0)
        main_vbox.pack_start(wall_box, False, False, 0)

        # Optional checkboxes for replacing configs
        if show_lock_checkbox:
            self.lock_checkbox = Gtk.CheckButton(label="Replace Hyprlock config")
            self.lock_checkbox.set_active(False)
            main_vbox.pack_start(self.lock_checkbox, False, False, 0)
        if show_idle_checkbox:
            self.idle_checkbox = Gtk.CheckButton(label="Replace Hypridle config")
            self.idle_checkbox.set_active(False)
            main_vbox.pack_start(self.idle_checkbox, False, False, 0)

        # Accept and Cancel buttons
        button_box = Gtk.HBox(spacing=10)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self.on_cancel)
        accept_btn = Gtk.Button(label="Accept")
        accept_btn.connect("clicked", self.on_accept)
        button_box.pack_end(accept_btn, False, False, 0)
        button_box.pack_end(cancel_btn, False, False, 0)
        main_vbox.pack_start(button_box, False, False, 0)

    def on_accept(self, widget):
        """
        Save the configuration and update the necessary files.
        """
        # Update bind_vars from user inputs
        for prefix_key, suffix_key, prefix_entry, suffix_entry in self.entries:
            bind_vars[prefix_key] = prefix_entry.get_text()
            bind_vars[suffix_key] = suffix_entry.get_text()

        # Update wallpaper directory
        bind_vars["wallpapers_dir"] = self.wall_dir_chooser.get_filename()

        # Save the updated bind_vars to a JSON file
        config_json = os.path.expanduser("~/Modus/config/assets/config.json")
        os.makedirs(os.path.dirname(config_json), exist_ok=True)
        with open(config_json, "w") as f:
            json.dump(bind_vars, f)

        # Replace hyprlock config if requested
        if hasattr(self, "lock_checkbox") and self.lock_checkbox.get_active():
            src_lock = os.path.expanduser("~/Modus/config/hypr/hyprlock.conf")
            dest_lock = os.path.expanduser("~/.config/hypr/hyprlock.conf")
            backup_and_replace(src_lock, dest_lock, "Hyprlock")

        # Replace hypridle config if requested
        if hasattr(self, "idle_checkbox") and self.idle_checkbox.get_active():
            src_idle = os.path.expanduser("~/Modus/config/hypr/hypridle.conf")
            dest_idle = os.path.expanduser("~/.config/hypr/hypridle.conf")
            backup_and_replace(src_idle, dest_idle, "Hypridle")

        # Append the source string to the Hyprland config if not present
        hyprland_config_path = os.path.expanduser("~/.config/hypr/hyprland.conf")
        with open(hyprland_config_path, "r") as f:
            content = f.read()
        if SOURCE_STRING not in content:
            with open(hyprland_config_path, "a") as f:
                f.write(SOURCE_STRING)

        start_config()
        self.destroy()

    def on_cancel(self, widget):
        self.destroy()


def start_config():
    """
    Run final configuration steps: ensure necessary configs, write the hyprconf, and reload.
    """
    copy_wallpapers()
    setup_colors()

    # Write the generated hypr configuration to file
    hypr_config_dir = os.path.expanduser("~/Modus/config/hypr/")
    os.makedirs(hypr_config_dir, exist_ok=True)
    hypr_conf_path = os.path.join(hypr_config_dir, "modus.conf")
    with open(hypr_conf_path, "w") as f:
        f.write(generate_hyprconf())

    # Reload Hyprland configuration
    os.system("hyprctl reload")


def open_config():
    """
    Entry point for opening the configuration GUI.
    """
    load_bind_vars()

    # Check and copy hyprlock config if needed
    dest_lock = os.path.expanduser("~/.config/hypr/hyprlock.conf")
    src_lock = os.path.expanduser("~/Modus/config/hypr/hyprlock.conf")
    os.makedirs(os.path.dirname(dest_lock), exist_ok=True)
    show_lock_checkbox = True
    if not os.path.exists(dest_lock):
        shutil.copy(src_lock, dest_lock)
        show_lock_checkbox = False

    # Check and copy hypridle config if needed
    dest_idle = os.path.expanduser("~/.config/hypr/hypridle.conf")
    src_idle = os.path.expanduser("~/Modus/config/hypr/hypridle.conf")
    show_idle_checkbox = True
    if not os.path.exists(dest_idle):
        shutil.copy(src_idle, dest_idle)
        show_idle_checkbox = False

    # Create and run the GUI
    window = HyprConfGUI(show_lock_checkbox, show_idle_checkbox)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    open_config()
