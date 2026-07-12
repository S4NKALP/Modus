from fabric.utils import GdkPixbuf, GLib, Gtk, os, re

from config.data import ICON_CACHE_FILE
from utils.functions import read_json_file, write_json_file


class IconResolver:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if os.path.exists(ICON_CACHE_FILE):
            self._icon_dict = read_json_file(ICON_CACHE_FILE) or {}
        else:
            self._icon_dict = {}

        self.default_application_icon = "application-x-executable"

    def get_icon_name(self, app_id: str):
        if app_id in self._icon_dict:
            return self._icon_dict[app_id]
        new_icon = self._compositor_find_icon(app_id)
        self._store_new_icon(app_id, new_icon)
        return new_icon

    def resolve_icon(self, pixmap, icon_name: str, app_id: str, icon_size: int = 16):
        try:
            return (
                pixmap.as_pixbuf(icon_size, GdkPixbuf.InterpType.HYPER)
                if pixmap is not None
                else Gtk.IconTheme()
                .get_default()
                .load_icon(
                    icon_name,
                    icon_size,
                    Gtk.IconLookupFlags.FORCE_SIZE,
                )
            )
        except GLib.GError:
            return self.get_icon_pixbuf(app_id, icon_size)

    def get_icon_pixbuf(self, app_id: str, size: int = 16):
        icon_name = self.get_icon_name(app_id)
        try:
            return Gtk.IconTheme.get_default().load_icon(
                icon_name,
                size,
                Gtk.IconLookupFlags.FORCE_SIZE,
            )
        except GLib.GError:
            return (
                Gtk.IconTheme()
                .get_default()
                .load_icon(
                    "image-missing",
                    size,
                    Gtk.IconLookupFlags.FORCE_SIZE,
                )
            )

    def _store_new_icon(self, app_id: str, icon: str):
        self._icon_dict[app_id] = icon
        write_json_file(self._icon_dict, ICON_CACHE_FILE)

    def _get_icon_from_desktop_file(self, desktop_file_path: str):
        with open(desktop_file_path) as f:
            for line in f.readlines():
                if "Icon=" in line:
                    return "".join(line[5:].split())

        return self.default_application_icon

    def _get_desktop_file(self, app_id: str) -> str | None:
        data_dirs = GLib.get_system_data_dirs()
        for data_dir in data_dirs:
            data_dir = data_dir + "/applications/"
            if os.path.exists(data_dir):
                # Do name resolving here
                files = os.listdir(data_dir)
                matching = [
                    s for s in files if "".join(app_id.lower().split()) in s.lower()
                ]
                if matching:
                    return data_dir + matching[0]

                for word in list(filter(None, re.split(r"-|\.|_|\s", app_id))):
                    matching = [s for s in files if word.lower() in s.lower()]
                    if matching:
                        return data_dir + matching[0]

        return None

    def _compositor_find_icon(self, app_id: str):
        if Gtk.IconTheme.get_default().has_icon(app_id):
            return app_id
        if Gtk.IconTheme.get_default().has_icon(app_id + "-desktop"):
            return app_id + "-desktop"
        desktop_file = self._get_desktop_file(app_id)
        return (
            self._get_icon_from_desktop_file(desktop_file)
            if desktop_file
            else self.default_application_icon
        )
