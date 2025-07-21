import json
import os
import subprocess
import threading
import time

import gi
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image as FabricImage
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.stack import Stack
from fabric.widgets.window import Window
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image

from config.data import APP_NAME, APP_NAME_CAP
from config.settings.utils import backup_and_replace, start_config
from config.settings.wifi_tab import WiFiTab
from config.settings.bluetooth_tab import BluetoothTab
from config.settings.key_bindings_tab import KeyBindingsTab
from config.settings.appearance_tab import AppearanceTab
from config.settings.system_tab import SystemTab
from config.settings.about_tab import AboutTab

gi.require_version("Gtk", "3.0")


class HyprConfGUI(Window):
    def __init__(self, show_lock_checkbox: bool, show_idle_checkbox: bool, **kwargs):
        super().__init__(
            title="Modus Settings",
            name="modus-settings-window",
            size=(640, 640),
            **kwargs,
        )

        self.set_resizable(False)
        # Set strict size constraints to prevent dynamic resizing
        self.set_size_request(640, 640)
        self.set_default_size(640, 640)
        # Set geometry hints to enforce fixed size
        geometry = Gdk.Geometry()
        geometry.min_width = 640
        geometry.max_width = 640
        geometry.min_height = 640
        geometry.max_height = 640
        self.set_geometry_hints(None, geometry,
                               Gdk.WindowHints.MIN_SIZE | Gdk.WindowHints.MAX_SIZE)

        self.themes = ["Pills", "Dense", "Edge"]
        self.selected_face_icon = None
        self.show_lock_checkbox = show_lock_checkbox
        self.show_idle_checkbox = show_idle_checkbox

        # Initialize all tabs
        self.wifi_tab = WiFiTab()
        self.bluetooth_tab = BluetoothTab()
        self.key_bindings_tab = KeyBindingsTab()
        self.appearance_tab = AppearanceTab(self.themes, self)
        self.system_tab = SystemTab(show_lock_checkbox, show_idle_checkbox, self.enforce_window_size)
        self.about_tab = AboutTab()

        # Pass window size enforcement method to tabs
        self.wifi_tab.set_window_size_enforcer(self.enforce_window_size)
        self.bluetooth_tab.set_window_size_enforcer(self.enforce_window_size)

        root_box = Box(orientation="v", spacing=10, style="margin: 10px;")
        # Set fixed size for root container
        root_box.set_size_request(620, 620)
        self.add(root_box)

        main_content_box = Box(orientation="h", spacing=6, v_expand=False, h_expand=False)
        # Set fixed size for main content to prevent expansion
        main_content_box.set_size_request(620, 580)
        root_box.add(main_content_box)

        self.tab_stack = Stack(
            transition_type="slide-up-down",
            transition_duration=250,
            v_expand=False,
            h_expand=False,
        )
        # Set fixed size for tab stack
        self.tab_stack.set_size_request(580, 580)

        self.wifi_tab_content = self.wifi_tab.create_wifi_tab()
        self.bluetooth_tab_content = self.bluetooth_tab.create_bluetooth_tab()
        self.key_bindings_tab_content = self.key_bindings_tab.create_key_bindings_tab()
        self.appearance_tab_content = self.appearance_tab.create_appearance_tab()
        self.system_tab_content = self.system_tab.create_system_tab()
        self.about_tab_content = self.about_tab.create_about_tab()

        self.tab_stack.add_titled(
            self.wifi_tab_content, "Wifi", "Wifi"
        )
        self.tab_stack.add_titled(
            self.bluetooth_tab_content, "Bluetooth", "Bluetooth"
        )
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
        # Set fixed width for tab switcher
        tab_switcher.set_size_request(40, -1)
        main_content_box.add(tab_switcher)
        main_content_box.add(self.tab_stack)

        button_box = Box(orientation="h", spacing=10, h_align="end")
        # Set fixed height for button box
        button_box.set_size_request(-1, 40)
        reset_btn = Button(label="Reset to Defaults", on_clicked=self.on_reset)
        button_box.add(reset_btn)
        close_btn = Button(label="Close", on_clicked=self.on_close)
        button_box.add(close_btn)
        accept_btn = Button(label="Apply & Reload", on_clicked=self.on_accept)
        button_box.add(accept_btn)
        root_box.add(button_box)

        # Force window size after all content is added and on any size changes
        self.connect("realize", self._force_window_size)
        self.connect("size-allocate", self._on_size_allocate)

    def _force_window_size(self, widget):
        """Force the window to respect the declared size"""
        self.resize(640, 640)
        self.set_size_request(640, 640)

    def _on_size_allocate(self, widget, allocation):
        """Prevent window from changing size during allocation"""
        if allocation.width != 640 or allocation.height != 640:
            GLib.idle_add(lambda: self.resize(640, 640))

    def enforce_window_size(self):
        """Public method to enforce window size - can be called by tabs"""
        self._force_window_size(self)



    # Removed create_appearance_tab - now using AppearanceTab class

    # on_notification_position_changed moved to AppearanceTab class

    # Removed create_system_tab - now using SystemTab class
    # Removed create_about_tab - now using AboutTab class


    # Event handlers moved to respective tab classes

    def on_accept(self, _widget):
        current_bind_vars_snapshot = {}

        # Get values from key bindings tab
        current_bind_vars_snapshot.update(self.key_bindings_tab.get_key_binding_values())

        # Get values from appearance tab
        current_bind_vars_snapshot.update(self.appearance_tab.get_appearance_values())

        # Get values from system tab
        current_bind_vars_snapshot.update(self.system_tab.get_system_values())

        # Get face icon and hyprland switches
        selected_icon_path = self.appearance_tab.get_selected_face_icon()
        hyprland_switches = self.system_tab.get_hyprland_switches()
        replace_lock = hyprland_switches["replace_lock"]
        replace_idle = hyprland_switches["replace_idle"]

        if selected_icon_path:
            self.appearance_tab.clear_selected_face_icon()

        def _apply_and_reload_task_thread():
            nonlocal current_bind_vars_snapshot

            from . import utils

            utils.bind_vars.clear()
            utils.bind_vars.update(current_bind_vars_snapshot)

            start_time = time.time()
            print(f"{start_time:.4f}: Background task started.")

            config_json = os.path.expanduser(
                f"~/.config/{APP_NAME_CAP}/config/assets/config.json"
            )
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
                src = os.path.expanduser(
                    f"~/.config/{APP_NAME_CAP}/config/hypr/hyprlock.conf"
                )
                dest = os.path.expanduser("~/.config/hypr/hyprlock.conf")
                if os.path.exists(src):
                    backup_and_replace(src, dest, "Hyprlock")
                else:
                    print(f"Warning: Source hyprlock config not found at {src}")
                print(f"{time.time():.4f}: Finished replacing hyprlock config.")

            if replace_idle:
                print(f"{time.time():.4f}: Replacing hypridle config...")
                src = os.path.expanduser(
                    f"~/.config/{APP_NAME_CAP}/config/hypr/hypridle.conf"
                )
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

            print(f"{time.time():.4f}: Initiating Modus restart using Popen...")
            main_py = os.path.expanduser(f"~/.config/{APP_NAME_CAP}/main.py")
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
                print(f"{time.time():.4f}: killall process finished (or timed out).")
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

            print(f"{time.time():.4f}: Modus restart commands issued via Popen.")
            end_time = time.time()
            total_time = end_time - start_time
            print(
                f"{end_time:.4f}: Background task finished (Total: {total_time:.4f}s)."
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

    def on_reset(self, _widget):
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

            # Reset all tabs to defaults
            self.key_bindings_tab.reset_to_defaults(utils.bind_vars)
            self.appearance_tab.reset_to_defaults(utils.bind_vars)
            self.system_tab.reset_to_defaults(utils.bind_vars)

            self._update_panel_position_sensitivity()
            print("Settings reset to defaults.")

    def on_close(self, _widget):
        if self.application:
            self.application.quit()
        else:
            self.destroy()
