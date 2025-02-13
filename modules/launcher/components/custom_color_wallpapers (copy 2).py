import hashlib
import json
import os
from PIL import Image
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GdkPixbuf, GLib, Gtk, Gio
from snippets import MaterialIcon
from fabric.utils import exec_shell_command, get_relative_path
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from fabric.widgets.label import Label


def is_valid_hex_color(value: str) -> bool:
    """Validate if the string is a Hex color."""
    return (
        value.startswith("#")
        and len(value) == 7
        and all(c in "0123456789ABCDEFabcdef" for c in value[1:])
    )


def is_valid_hue(value: str) -> bool:
    """Validate if the string is a numeric Hue value (0–360)."""
    return value.isnumeric() and 0 <= float(value) <= 360


class WallpaperSelector(Box):
    CACHE_DIR = os.path.expanduser("~/.cache/modus/wallpapers")
    SETTINGS_FILE = os.path.expanduser("~/dotfiles/hypr/scripts/settings.json")
    SCHEMES = {
        "TonalSpot": "tonalSpot",
        "Expressive": "expressive",
        "FruitSalad": "fruitSalad",
        "Monochrome": "monochrome",
        "Rainbow": "rainbow",
        "Vibrant": "vibrant",
        "Neutral": "neutral",
        "Fidelity": "fidelity",
        "Content": "content",
    }

    def __init__(self, **kwargs):
        super().__init__(name="wallpapers", spacing=4, orientation="v", **kwargs)
        self.launcher = kwargs["launcher"]

        self.wallpapers_dir = os.path.expanduser("~/Pictures/wallpapers")
        os.makedirs(self.CACHE_DIR, exist_ok=True)

        self.files = [f for f in os.listdir(self.wallpapers_dir) if self._is_image(f)]
        self.thumbnails = []
        self.thumbnail_queue = []
        self.executor = ThreadPoolExecutor(max_workers=4)  # Shared executor

        self.viewport = Gtk.IconView()
        self.viewport.set_model(Gtk.ListStore(GdkPixbuf.Pixbuf, str))
        self.viewport.set_pixbuf_column(0)
        self.viewport.set_text_column(1)
        self.viewport.set_item_width(0)
        self.viewport.connect("item-activated", self.on_wallpaper_selected)

        self.scrolled_window = ScrolledWindow(
            name="scrolled-window",
            spacing=10,
            h_expand=True,
            v_expand=True,
            child=self.viewport,
        )

        self.search_entry = Entry(
            name="search-entry",
            h_expand=True,
            notify_text=lambda entry, *_: self.arrange_viewport(entry.get_text()),
        )

        self.scheme_dropdown = Gtk.ComboBoxText()
        self.scheme_dropdown.set_name("scheme-dropdown")
        self.scheme_dropdown.set_tooltip_text("Select color scheme")

        for display_name, scheme_id in sorted(self.SCHEMES.items()):
            self.scheme_dropdown.append(scheme_id, display_name)

        self.scheme_dropdown.set_active_id("tonalSpot")
        self.scheme_dropdown.connect("changed", self.on_scheme_changed)

        initial_icon = "light_mode" if not self.check_dark_mode_state() else "dark_mode"
        self.toggle_button = Button(
            child=MaterialIcon(initial_icon),
            name="toggle-launcher-button",
            on_clicked=self.toggle_dark_mode,
        )
        self.custom_color_entry = Entry(
            name="search-entry",
            h_expand=True,
        )
        self.custom_color_entry.connect("activate", self.on_custom_color_submitted)

        self.custom_color_box = Box(
            name="custom-color-box",
            spacing=10,
            orientation="h",
            children=[
                Label(label="Custom Color:"),
                self.custom_color_entry,
            ],
        )

        self.dropdown_box = Box(
            name="dropdown-box",
            orientation="h",
            children=[
                self.scheme_dropdown,
                MaterialIcon("keyboard_arrow_down"),
            ],
        )

        self.header_box = Box(
            name="header-box",
            spacing=10,
            orientation="h",
            children=[
                self.search_entry,
                self.dropdown_box,
                self.custom_color_box,
                self.toggle_button,
            ],
        )

        self.add(self.header_box)
        self.add(self.scrolled_window)
        self._start_thumbnail_thread()
        self.setup_file_monitor()
        self.show_all()

    def setup_file_monitor(self):
        gfile = Gio.File.new_for_path(self.wallpapers_dir)
        self.file_monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.file_monitor.connect("changed", self.on_directory_changed)

    def on_directory_changed(self, monitor, file, other_file, event_type):
        file_name = file.get_basename()
        if event_type == Gio.FileMonitorEvent.DELETED:
            if file_name in self.files:
                self.files.remove(file_name)
                cache_path = self._get_cache_path(file_name)
                if os.path.exists(cache_path):
                    try:
                        os.remove(cache_path)
                    except Exception as e:
                        print(f"Error deleting cache {cache_path}: {e}")
                self.thumbnails = [(p, n) for p, n in self.thumbnails if n != file_name]
                GLib.idle_add(self.arrange_viewport, self.search_entry.get_text())
        elif event_type == Gio.FileMonitorEvent.CREATED:
            if self._is_image(file_name) and file_name not in self.files:
                self.files.append(file_name)
                self.files.sort()
                self.executor.submit(self._process_file, file_name)
        elif event_type == Gio.FileMonitorEvent.CHANGED:
            if self._is_image(file_name) and file_name in self.files:
                cache_path = self._get_cache_path(file_name)
                if os.path.exists(cache_path):
                    try:
                        os.remove(cache_path)
                    except Exception as e:
                        print(f"Error deleting cache for changed file {file_name}: {e}")
                self.executor.submit(self._process_file, file_name)

    def close_selector(self):
        self.launcher.close()

    def arrange_viewport(self, query: str = ""):
        self.viewport.get_model().clear()
        filtered_thumbnails = [
            (thumb, name)
            for thumb, name in self.thumbnails
            if query.casefold() in name.casefold()
        ]

        filtered_thumbnails.sort(key=lambda x: x[1].lower())

        for pixbuf, file_name in filtered_thumbnails:
            self.viewport.get_model().append([pixbuf, file_name])

    def toggle_dark_mode(self, *_):
        GLib.spawn_command_line_async(
            f"bash {get_relative_path('../../../assets/scripts/dark-theme.sh --toggle')}"
        )
        icon_name = "dark_mode" if not self.check_dark_mode_state() else "light_mode"
        if self.toggle_button.get_child():
            self.toggle_button.remove(self.toggle_button.get_child())
        self.toggle_button.add(MaterialIcon(icon_name))
        self.toggle_button.show_all()

    def check_dark_mode_state(self):
        result = exec_shell_command(
            "gsettings get org.gnome.desktop.interface color-scheme"
        )
        return result.strip().replace("'", "") == "prefer-dark"

    def on_wallpaper_selected(self, iconview, path):
        model = iconview.get_model()
        file_name = model[path][1]
        full_path = os.path.join(self.wallpapers_dir, file_name)
        selected_scheme = self.scheme_dropdown.get_active_id()
        home_dir = GLib.get_home_dir()
        command = (
            f"python -O {home_dir}/dotfiles/hypr/scripts/wallpaper.py -I {full_path}"
        )
        GLib.spawn_command_line_async(command)
        self.update_scheme(selected_scheme)

    def on_scheme_changed(self, combo):
        scheme_id = combo.get_active_id()
        display_name = next(
            name for name, id in self.SCHEMES.items() if id == scheme_id
        )
        print(f"Color scheme selected: {display_name} ({scheme_id})")
        self.update_scheme(scheme_id)

        home_dir = GLib.get_home_dir()
        color_generator = os.path.join(home_dir, "dotfiles/material-colors/generate.py")
        try:
            command = f'python -O {color_generator} -R --scheme "{scheme_id}"'
            GLib.spawn_command_line_async(command)
            print(f"Applied color scheme: {display_name}")
        except Exception as e:
            print(f"Failed to apply color scheme: {e}")

    def update_scheme(self, scheme: str):
        try:
            with open(self.SETTINGS_FILE, "r") as f:
                settings = json.loads(f.read())

            settings["generation-scheme"] = scheme

            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception as error:
            print(f"Failed to update generation-scheme in settings.json: {error}")

    def _start_thumbnail_thread(self):
        thread = GLib.Thread.new("thumbnail-loader", self._preload_thumbnails, None)

    def _preload_thumbnails(self, _data):
        futures = [
            self.executor.submit(self._process_file, file_name)
            for file_name in self.files
        ]
        concurrent.futures.wait(futures)
        GLib.idle_add(self._process_batch)

    def _process_file(self, file_name):
        full_path = os.path.join(self.wallpapers_dir, file_name)
        cache_path = self._get_cache_path(file_name)
        if not os.path.exists(cache_path):
            try:
                with Image.open(full_path) as img:
                    img.thumbnail((96, 96), Image.Resampling.BILINEAR)
                    img.save(cache_path, "PNG")
            except Exception as e:
                print(f"Error processing {file_name}: {e}")
                return
        self.thumbnail_queue.append((cache_path, file_name))
        GLib.idle_add(self._process_batch)

    def _process_batch(self):
        batch = self.thumbnail_queue[:10]
        del self.thumbnail_queue[:10]
        for cache_path, file_name in batch:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(cache_path)
                self.thumbnails.append((pixbuf, file_name))
                self.viewport.get_model().append([pixbuf, file_name])
            except Exception as e:
                print(f"Error loading thumbnail {cache_path}: {e}")
        if self.thumbnail_queue:
            GLib.idle_add(self._process_batch)
        return False

    def _get_cache_path(self, file_name: str) -> str:
        file_hash = hashlib.md5(file_name.encode("utf-8")).hexdigest()
        return os.path.join(self.CACHE_DIR, f"{file_hash}.png")

    @staticmethod
    def _is_image(file_name: str) -> bool:
        return file_name.lower().endswith(
            (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
        )

    def on_custom_color_submitted(self, entry: Entry):
        """Handle color submission."""
        color = entry.get_text().strip()
        if is_valid_hex_color(color) or is_valid_hue(color):
            color_value = (
                color if is_valid_hex_color(color) else self.hue_to_hex(float(color))
            )
            print(f"Applying custom color: {color_value}")
            self.update_custom_color(color_value)
        else:
            print("Invalid color input. Please use a valid Hex or Hue.")

    def update_custom_color(self, color: str):
        """Update the custom color in settings and regenerate theme."""
        try:
            with open(self.SETTINGS_FILE, "r") as f:
                settings = json.loads(f.read())

            settings["custom-color"] = color

            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=2)

            home_dir = GLib.get_home_dir()
            color_generator = os.path.join(
                home_dir, "dotfiles/material-colors/generate.py"
            )
            command = f'python -O {color_generator} --color "{color}"'
            GLib.spawn_command_line_async(command)
            print(f"Custom color applied: {color}")
        except Exception as e:
            print(f"Failed to update custom color: {e}")

    @staticmethod
    def hue_to_hex(hue: float) -> str:
        """Convert Hue to Hex color."""
        hue = hue / 360.0
        rgb = WallpaperSelector.hls_to_rgb(hue, 0.5, 1.0)
        return f"#{int(rgb[0] * 255):02X}{int(rgb[1] * 255):02X}{int(rgb[2] * 255):02X}"

    @staticmethod
    def hls_to_rgb(h: float, l: float, s: float) -> tuple:
        """Convert HLS to RGB color."""
        if s == 0:
            return l, l, l

        def hue2rgb(p, q, t):
            if t < 0:
                t += 1
            if t > 1:
                t -= 1
            if t < 1 / 6:
                return p + (q - p) * 6 * t
            if t < 1 / 2:
                return q
            if t < 2 / 3:
                return p + (q - p) * (2 / 3 - t) * 6
            return p

        q = l * (1 + s) if l < 0.5 else l + s - l * s
        p = 2 * l - q
        r = hue2rgb(p, q, h + 1 / 3)
        g = hue2rgb(p, q, h)
        b = hue2rgb(p, q, h - 1 / 3)
        return r, g, b
