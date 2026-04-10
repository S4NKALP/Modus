import json

from fabric.utils import GLib, Gtk, logger, os

import shared.data as data

ICON_CACHE_FILE = data.CACHE_DIR + "/icons.json"
if not os.path.exists(data.CACHE_DIR):
    os.makedirs(data.CACHE_DIR)


class IconResolver:
    def __init__(
        self, default_applicaiton_icon: str = "application-x-executable-symbolic"
    ):
        if os.path.exists(ICON_CACHE_FILE):
            with open(ICON_CACHE_FILE) as f:
                try:
                    self._icon_dict = json.load(f)
                except json.JSONDecodeError:
                    logger.info("[ICONS] Cache file does not exist or is corrupted")
                    self._icon_dict = {}
        else:
            self._icon_dict = {}

        self.default_applicaiton_icon = default_applicaiton_icon

    def get_icon_name(self, app_id: str):
        if app_id in self._icon_dict:
            return self._icon_dict[app_id]
        new_icon = self._compositor_find_icon(app_id)
        logger.info(
            f"[ICONS] found new icon: '{new_icon}' for app id: '{app_id}', storing..."
        )
        self._store_new_icon(app_id, new_icon)
        return new_icon

    def get_icon_pixbuf(self, app_id: str, size: int = 16):
        icon_theme = Gtk.IconTheme.get_default()
        icon_name = self.get_icon_name(app_id)
        try:
            # Try to load the resolved icon.
            return icon_theme.load_icon(icon_name, size, Gtk.IconLookupFlags.FORCE_SIZE)
        except GLib.Error as primary_error:
            logger.warning(
                f"Warning: Icon '{icon_name}' not found in theme. Error: {primary_error}"
            )
            try:
                # Fallback to the default application icon.
                return icon_theme.load_icon(
                    self.default_applicaiton_icon, size, Gtk.IconLookupFlags.FORCE_SIZE
                )
            except GLib.Error as fallback_error:
                logger.error(
                    f"Error: Fallback icon '{self.default_applicaiton_icon}' also not found. Error: {fallback_error}"
                )
                return None

    def _store_new_icon(self, app_id: str, icon: str):
        self._icon_dict[app_id] = icon
        with open(ICON_CACHE_FILE, "w") as f:
            json.dump(self._icon_dict, f)

    def _get_icon_from_desktop_file(self, desktop_file_path: str):
        # Retrieve the icon specified in the [Desktop Entry] section.
        try:
            with open(desktop_file_path) as f:
                in_desktop_entry = False
                for line in f:
                    line = line.strip()
                    if line == "[Desktop Entry]":
                        in_desktop_entry = True
                    elif line.startswith("[") and line.endswith("]"):
                        in_desktop_entry = False

                    if in_desktop_entry and line.startswith("Icon="):
                        return line[5:].strip()
        except Exception as e:
            logger.error(f"[ICONS] Error reading desktop file {desktop_file_path}: {e}")

        return self.default_applicaiton_icon

    def _get_desktop_file(self, app_id: str) -> str | None:
        if not app_id:
            return None

        search_dirs = [os.path.join(GLib.get_user_data_dir(), "applications")] + [
            os.path.join(d, "applications") for d in GLib.get_system_data_dirs()
        ]

        # Normalize search IDs (full ID and parts for Reverse DNS or decorated names)
        search_ids = [app_id.lower()]
        for sep in [".", "_", "-"]:
            if sep in app_id:
                parts = app_id.split(sep)
                for part in parts:
                    if part and len(part) > 2 and part.lower() not in search_ids:
                        search_ids.append(part.lower())

        # 1. Try exact filename matches first (highest priority)
        for data_dir in search_dirs:
            if not os.path.exists(data_dir):
                continue

            files = os.listdir(data_dir)
            for sid in search_ids:
                target = f"{sid}.desktop"
                for f in files:
                    if f.lower() == target:
                        return os.path.join(data_dir, f)

                # Try basename match without .desktop
                for f in files:
                    basename = f[:-8] if f.lower().endswith(".desktop") else f
                    if basename.lower() == sid:
                        return os.path.join(data_dir, f)

        # 2. Try matching StartupWMClass or Name inside desktop files (more expensive)
        for data_dir in search_dirs:
            if not os.path.exists(data_dir):
                continue

            for f in os.listdir(data_dir):
                if not f.endswith(".desktop"):
                    continue
                path = os.path.join(data_dir, f)
                try:
                    with open(path, "r", errors="ignore") as file:
                        for line in file:
                            line = line.strip()
                            if line.startswith("StartupWMClass="):
                                wm_class = line[15:].strip()
                                if wm_class.lower() == app_id.lower():
                                    return path
                            elif line.startswith("Name="):
                                name = line[5:].strip().lower()
                                if any(sid == name for sid in search_ids):
                                    return path
                except Exception:
                    continue

        return None

    def _compositor_find_icon(self, app_id: str):
        if not app_id:
            return self.default_applicaiton_icon

        icon_theme = Gtk.IconTheme.get_default()

        # Try direct icon name match
        if icon_theme.has_icon(app_id):
            return app_id

        # Try with common suffixes
        for suffix in ["-desktop", "-symbolic"]:
            if icon_theme.has_icon(app_id + suffix):
                return app_id + suffix

        # Try finding desktop file
        desktop_file = self._get_desktop_file(app_id)
        if desktop_file:
            icon = self._get_icon_from_desktop_file(desktop_file)
            if icon and icon_theme.has_icon(icon):
                return icon

        return self.default_applicaiton_icon
