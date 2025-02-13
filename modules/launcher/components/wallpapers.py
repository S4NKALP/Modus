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
from snippets import WALLPAPERS_DIR


class WallpaperSelector(Box):
    CACHE_DIR = os.path.expanduser("~/.cache/modus/wallpapers")
    SETTINGS_FILE = get_relative_path("../../../config/assets/settings.json")
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

        # self.wallpapers_dir = os.path.expanduser("~/Pictures/wallpapers")
        os.makedirs(self.CACHE_DIR, exist_ok=True)

        self.files = [f for f in os.listdir(WALLPAPERS_DIR) if self._is_image(f)]
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

        # Set the initial icon based on dark mode state
        initial_icon = "light_mode" if not self.check_dark_mode_state() else "dark_mode"
        self.toggle_button = Button(
            child=MaterialIcon(initial_icon),
            name="toggle-launcher-button",
            on_clicked=self.toggle_dark_mode,
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
            children=[self.search_entry, self.dropdown_box, self.toggle_button],
        )

        self.add(self.header_box)
        self.add(self.scrolled_window)
        self._start_thumbnail_thread()
        self.setup_file_monitor()
        self.show_all()

    def setup_file_monitor(self):
        gfile = Gio.File.new_for_path(WALLPAPERS_DIR)
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
        current_state = self.check_dark_mode_state()
        new_mode = "dark" if not current_state else "light"

        # Call the shell script with the --set argument
        command = f"bash {get_relative_path('../../../config/dark-theme.sh')} --set {new_mode}"
        GLib.spawn_command_line_async(command)

        # Set the appropriate icon based on the mode
        icon_name = "dark_mode" if new_mode == "dark" else "light_mode"

        # Update button icon
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
        full_path = os.path.join(WALLPAPERS_DIR, file_name)
        selected_scheme = self.scheme_dropdown.get_active_id()
        wallpaper = get_relative_path("../../../config/wallpaper.py")
        command = f"python -O {wallpaper} -I {full_path}"
        GLib.spawn_command_line_async(command)
        self.update_scheme(selected_scheme)

    def on_scheme_changed(self, combo):
        scheme_id = combo.get_active_id()
        display_name = next(
            name for name, id in self.SCHEMES.items() if id == scheme_id
        )
        print(f"Color scheme selected: {display_name} ({scheme_id})")
        self.update_scheme(scheme_id)

        color_generator = get_relative_path(
            "../../../config/material-colors/generate.py"
        )
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
        full_path = os.path.join(WALLPAPERS_DIR, file_name)
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
