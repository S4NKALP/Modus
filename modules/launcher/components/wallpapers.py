import hashlib, json, os, colorsys
from PIL import Image
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GdkPixbuf, GLib, Gtk, Gio, Gdk
from fabric.utils import get_relative_path, exec_shell_command_async
from concurrent.futures import ThreadPoolExecutor, wait
from utils import WALLPAPERS_DIR
import utils.icons as icons


class WallpaperSelector(Box):
    CACHE_DIR = os.path.expanduser("~/.cache/modus/wallpapers")
    SETTINGS_FILE = get_relative_path("../../../config/assets/settings.json")
    CURRENT_WALLPAPER_FILE = os.path.expanduser("~/.cache/current_wallpaper")
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
    ITEM_WIDTH = 108

    def __init__(self, **kwargs):
        super().__init__(
            name="wallpapers",
            spacing=4,
            orientation="v",
            h_expand=False,
            v_expand=False,
            **kwargs,
        )
        self.launcher = kwargs["launcher"]
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        self.files = [f for f in os.listdir(WALLPAPERS_DIR) if self._is_image(f)]
        self.thumbnails, self.thumbnail_queue = [], []
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.selected_index, self.current_wallpaper = -1, None
        self._init_widgets()
        self._start_thumbnail_thread()
        self.setup_file_monitor()
        if os.path.exists(self.CURRENT_WALLPAPER_FILE):
            gfile = Gio.File.new_for_path(self.CURRENT_WALLPAPER_FILE)
            self.current_wp_monitor = gfile.monitor_file(
                Gio.FileMonitorFlags.NONE, None
            )
            self.current_wp_monitor.connect(
                "changed", self.on_current_wallpaper_changed
            )
        self.show_all()
        self.search_entry.grab_focus()

    def _init_widgets(self):
        self.viewport = Gtk.IconView(name="wallpaper-icons")
        self.viewport.set_model(Gtk.ListStore(GdkPixbuf.Pixbuf, str))
        self.viewport.set_pixbuf_column(0)
        self.viewport.set_text_column(-1)
        self.viewport.set_item_width(self.ITEM_WIDTH)
        self.viewport.connect("item-activated", self.on_wallpaper_selected)
        self.scrolled_window = ScrolledWindow(
            name="scrolled-window",
            spacing=10,
            h_expand=True,
            v_expand=True,
            child=self.viewport,
        )
        self.search_entry = Entry(
            name="search-entry-walls",
            h_expand=True,
            notify_text=lambda entry, *_: self.arrange_viewport(entry.get_text()),
            on_key_press_event=self.on_search_entry_key_press,
        )
        self.scheme_dropdown = Gtk.ComboBoxText()
        self.scheme_dropdown.set_name("scheme-dropdown")
        self.scheme_dropdown.set_tooltip_text("Select color scheme")
        for display_name, scheme_id in sorted(self.SCHEMES.items()):
            self.scheme_dropdown.append(scheme_id, display_name)
        self.scheme_dropdown.set_active_id("tonalSpot")
        self.scheme_dropdown.connect("changed", self.on_scheme_changed)
        self.materialyoucolor_switcher = Gtk.Switch(name="materialyoucolor-switcher")
        self.materialyoucolor_switcher.set_vexpand(False)
        self.materialyoucolor_switcher.set_hexpand(False)
        self.materialyoucolor_switcher.set_valign(Gtk.Align.CENTER)
        self.materialyoucolor_switcher.set_halign(Gtk.Align.CENTER)
        self.materialyoucolor_switcher.set_active(True)
        self.mat_icon = Label(name="mat-label", markup=icons.palette)
        self.dropdown_box = Box(name="dropdown-box", children=[self.scheme_dropdown])
        self.custom_color_entry = Entry(
            name="entry-custom-color",
            h_expand=True,
            notify_text=lambda entry, *_: self.on_custom_color_submitted(entry),
            on_key_press_event=self.on_custom_color_key_press,
        )
        self.header_box = CenterBox(
            name="header-box",
            spacing=10,
            orientation="h",
            start_children=[self.materialyoucolor_switcher, self.mat_icon],
            center_children=[
                self.search_entry,
                Label(label="Custom Color:"),
                self.custom_color_entry,
            ],
            end_children=[self.dropdown_box],
        )
        self.add(self.header_box)
        self.add(self.scrolled_window)

    def setup_file_monitor(self):
        gfile = Gio.File.new_for_path(WALLPAPERS_DIR)
        self.file_monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.file_monitor.connect("changed", self.on_directory_changed)

    def on_current_wallpaper_changed(self, monitor, file, other_file, event_type):
        if event_type in (Gio.FileMonitorEvent.CHANGED, Gio.FileMonitorEvent.CREATED):
            try:
                with open(self.CURRENT_WALLPAPER_FILE, "r") as f:
                    new_wp = f.read().strip()
                if new_wp and new_wp != self.current_wallpaper:
                    self.current_wallpaper = new_wp
                    if self.custom_color_entry.get_text().strip().lower() in [
                        "",
                        "none",
                    ]:
                        scheme = self.scheme_dropdown.get_active_id()
                        color_generator = get_relative_path(
                            "../../../config/material-colors/generate.py"
                        )
                        command = f'python -O {color_generator} --scheme "{scheme}" --image "{self.current_wallpaper}"'
                        self._run_command(command)
            except Exception as e:
                print(f"Error updating current wallpaper: {e}")

    def on_directory_changed(self, monitor, file, other_file, event_type):
        file_name = file.get_basename()
        if event_type == Gio.FileMonitorEvent.DELETED:
            if file_name in self.files:
                self.files.remove(file_name)
                self._delete_cache(file_name)
                self.thumbnails = [(p, n) for p, n in self.thumbnails if n != file_name]
                GLib.idle_add(self.arrange_viewport, self.search_entry.get_text())
            return
        if event_type in (
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.CHANGED,
        ) and self._is_image(file_name):
            if (
                event_type == Gio.FileMonitorEvent.CREATED
                and file_name not in self.files
            ):
                self.files.append(file_name)
                self.files.sort()
            elif event_type == Gio.FileMonitorEvent.CHANGED and file_name in self.files:
                self._delete_cache(file_name)
            self.executor.submit(self._process_file, file_name)

    def _delete_cache(self, file_name: str):
        cache_path = self._get_cache_path(file_name)
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except Exception:
                pass

    def arrange_viewport(self, query: str = ""):
        model = self.viewport.get_model()
        model.clear()
        for pixbuf, file_name in sorted(
            [
                (thumb, name)
                for thumb, name in self.thumbnails
                if query.casefold() in name.casefold()
            ],
            key=lambda x: x[1].lower(),
        ):
            model.append([pixbuf, file_name])
        if not query.strip():
            self.viewport.unselect_all()
            self.selected_index = -1
        elif len(model) > 0:
            self.update_selection(0)

    def on_wallpaper_selected(self, iconview, path):
        model = iconview.get_model()
        file_name = model[path][1]
        full_path = os.path.join(WALLPAPERS_DIR, file_name)
        selected_scheme = self.scheme_dropdown.get_active_id()
        wallpaper_script = get_relative_path("../../../config/scripts/wallpaper.py")
        if self.materialyoucolor_switcher.get_active():
            command = f"python -O {wallpaper_script} -I {full_path}"
            GLib.spawn_command_line_async(command)
            self.update_scheme(selected_scheme)
        else:
            cmd = f"swww img {full_path} -t outer --transition-duration 1.5 --transition-step 255 --transition-fps 60 -f Nearest"
            exec_shell_command_async(cmd)

    def on_search_entry_key_press(self, widget, event):
        if event.state & Gdk.ModifierType.SHIFT_MASK:
            if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
                scheme_list = [
                    scheme_id for _, scheme_id in sorted(self.SCHEMES.items())
                ]
                try:
                    current_index = scheme_list.index(
                        self.scheme_dropdown.get_active_id()
                    )
                except ValueError:
                    current_index = 0
                new_index = (
                    (current_index - 1) % len(scheme_list)
                    if event.keyval == Gdk.KEY_Up
                    else (current_index + 1) % len(scheme_list)
                )
                self.scheme_dropdown.set_active(new_index)
                return True
            elif event.keyval == Gdk.KEY_Right:
                self.scheme_dropdown.popup()
                return True
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right):
            self.move_selection_2d(event.keyval)
            return True
        elif event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.selected_index != -1:
                path = Gtk.TreePath.new_from_indices([self.selected_index])
                self.on_wallpaper_selected(self.viewport, path)
            return True
        return False

    def move_selection_2d(self, keyval):
        model = self.viewport.get_model()
        total_items = len(model)
        if total_items == 0:
            return
        if self.selected_index == -1:
            new_index = (
                0 if keyval in (Gdk.KEY_Down, Gdk.KEY_Right) else total_items - 1
            )
        else:
            current_index = self.selected_index
            allocation = self.viewport.get_allocation()
            columns = max(1, allocation.width // self.ITEM_WIDTH)
            new_index = current_index + (
                1
                if keyval == Gdk.KEY_Right
                else -1
                if keyval == Gdk.KEY_Left
                else columns
                if keyval == Gdk.KEY_Down
                else -columns
            )
            new_index = max(0, min(new_index, total_items - 1))
        self.update_selection(new_index)

    def update_selection(self, new_index: int):
        self.viewport.unselect_all()
        path = Gtk.TreePath.new_from_indices([new_index])
        self.viewport.select_path(path)
        self.viewport.scroll_to_path(path, False, 0.5, 0.5)
        self.selected_index = new_index

    def _start_thumbnail_thread(self):
        GLib.Thread.new("thumbnail-loader", self._preload_thumbnails, None)

    def _preload_thumbnails(self, _data):
        futures = [
            self.executor.submit(self._process_file, file_name)
            for file_name in self.files
        ]
        wait(futures)
        GLib.idle_add(self._process_batch)

    def _process_file(self, file_name):
        full_path = os.path.join(WALLPAPERS_DIR, file_name)
        cache_path = self._get_cache_path(file_name)
        if not os.path.exists(cache_path):
            try:
                with Image.open(full_path) as img:
                    width, height = img.size
                    side = min(width, height)
                    left = (width - side) // 2
                    top = (height - side) // 2
                    img_cropped = img.crop((left, top, left + side, top + side))
                    img_cropped.thumbnail((96, 96), Image.Resampling.LANCZOS)
                    img_cropped.save(cache_path, "PNG")
            except Exception:
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

    def on_scheme_changed(self, combo):
        scheme_id = combo.get_active_id()
        display_name = next(
            name for name, id in self.SCHEMES.items() if id == scheme_id
        )
        self.update_scheme(scheme_id)
        color_generator = get_relative_path(
            "../../../config/material-colors/generate.py"
        )
        command = f'python -O {color_generator} -R --scheme "{scheme_id}"'
        self._run_command(
            command,
            success_message=f"Applied color scheme: {display_name}",
            failure_message="Failed to apply color scheme:",
        )

    def update_scheme(self, scheme: str):
        self._update_settings_field("generation-scheme", scheme)

    def on_custom_color_submitted(self, entry: Entry):
        color = entry.get_text().strip()
        if not color:
            self.update_custom_color("")
            return
        if self.is_valid_hex_color(color):
            color_value = color
        elif self.is_valid_hue(color):
            color_value = self.hue_to_hex(float(color))
        else:
            return
        self.update_custom_color(color_value)

    def on_custom_color_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Return:
            self.on_custom_color_submitted(widget)
            return True
        return False

    def _fetch_current_wallpaper(self):
        if not self.current_wallpaper or not os.path.exists(self.current_wallpaper):
            if os.path.exists(self.CURRENT_WALLPAPER_FILE):
                try:
                    with open(self.CURRENT_WALLPAPER_FILE, "r") as f:
                        self.current_wallpaper = f.read().strip()
                except Exception as e:
                    print(f"Error reading current wallpaper: {e}")
        return self.current_wallpaper

    def update_custom_color(self, color: str):
        color = color if color and color.lower() != "none" else "none"
        self._update_settings_field("custom-color", color)
        color_generator = get_relative_path(
            "../../../config/material-colors/generate.py"
        )
        if color == "none":
            scheme = self.scheme_dropdown.get_active_id()
            current_wp = self._fetch_current_wallpaper()
            command = f'python -O {color_generator} --scheme "{scheme}" --image "{current_wp}"'
        else:
            command = f'python -O {color_generator} --color "{color}"'
        self._run_command(command)

    @staticmethod
    def _is_image(file_name: str) -> bool:
        return file_name.lower().endswith(
            (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
        )

    @staticmethod
    def is_valid_hex_color(value: str) -> bool:
        return (
            value.startswith("#")
            and len(value) == 7
            and all(c in "0123456789ABCDEFabcdef" for c in value[1:])
        )

    @staticmethod
    def is_valid_hue(value: str) -> bool:
        try:
            return 0 <= float(value) <= 360
        except ValueError:
            return False

    def hue_to_hex(self, hue: float) -> str:
        r, g, b = colorsys.hls_to_rgb(hue / 360.0, 0.5, 1.0)
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

    def _update_settings_field(self, field: str, value):
        try:
            with open(self.SETTINGS_FILE, "r") as f:
                settings = json.load(f)
            settings[field] = value
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass

    def _run_command(
        self, command: str, success_message: str = None, failure_message: str = None
    ):
        try:
            GLib.spawn_command_line_async(command)
            if success_message:
                print(success_message)
        except Exception:
            if failure_message:
                print(failure_message)
