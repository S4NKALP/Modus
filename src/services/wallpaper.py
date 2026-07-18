import hashlib
import mimetypes
import shlex

from fabric.core import Service, Signal
from fabric.utils import GdkPixbuf as gdk_pixbuf
from fabric.utils import exec_shell_command_async, logger, os

from services.config import on_config_change
from shared.data import (
    WALLPAPERS_THUMBNAILS_SIZE,
    _get_wallpaper_path,
)

os.makedirs(_get_wallpaper_path(), exist_ok=True)


def get_thumbnail_filename(image_path: str) -> str:
    key = hashlib.sha256(image_path.encode()).hexdigest()
    return f"{key}_{WALLPAPERS_THUMBNAILS_SIZE}x{WALLPAPERS_THUMBNAILS_SIZE}.webp"


def create_thumbnail(
    image_path: str,
    thumbnail_path: str,
    size: int = WALLPAPERS_THUMBNAILS_SIZE,
) -> bool:
    """Create a compressed WebP thumbnail."""

    try:
        pixbuf = gdk_pixbuf.Pixbuf.new_from_file_at_scale(
            image_path,
            size,
            size,
            preserve_aspect_ratio=True,
        )

        return bool(
            pixbuf.savev(
                thumbnail_path,
                "webp",
                ["quality"],
                ["85"],
            )
        )

    except Exception as e:
        logger.warning(
            f"[wallpaper] pixbuf = gdk_pixbuf.Pixbuf.new_from_file_at_scale( image_... failed: {e}"
        )
        return False


class WallpaperService(Service):
    @Signal
    def wallpaper_ready(self, image_path: str, thumbnail_path: str) -> None: ...

    @Signal
    def wallpaper_set(self, image_path: str) -> None: ...

    @Signal
    def colors_generated(self, image_path: str) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._file_cache: list[str] | None = None
        on_config_change(self._on_config_change)

    def _on_config_change(self, new_config, old_config):
        if new_config.get("wallpapers_dir") != old_config.get("wallpapers_dir"):
            self._file_cache = None
            path = _get_wallpaper_path()
            os.makedirs(path, exist_ok=True)
            os.makedirs(f"{path}/.thumbnails", exist_ok=True)

    def get_all_wallpapers(self, use_cache: bool = True) -> list[str]:
        if use_cache and self._file_cache is not None:
            return self._file_cache

        wallpapers: list[str] = []
        wallpaper_path = _get_wallpaper_path()

        with os.scandir(wallpaper_path) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue

                mime, _ = mimetypes.guess_type(entry.path)
                if mime and mime.startswith("image/"):
                    wallpapers.append(entry.path)

        self._file_cache = wallpapers
        return wallpapers

    def invalidate_cache(self) -> None:
        self._file_cache = None

    def get_thumbnail_path(self, image_path: str) -> str:
        thumbs_dir = f"{_get_wallpaper_path()}/.thumbnails"
        return os.path.join(
            thumbs_dir,
            get_thumbnail_filename(image_path),
        )

    def has_thumbnail(self, image_path: str) -> bool:
        return os.path.isfile(self.get_thumbnail_path(image_path))

    def set_wallpaper(self, image_path: str) -> None:
        exec_shell_command_async(
            f"awww img {shlex.quote(image_path)} "
            "--transition-type none "
            "--transition-duration 0 "
            "--transition-fps 60"
        )

        self.wallpaper_set(image_path)

        link_path = os.path.expanduser("~/.current.wall")

        if os.path.lexists(link_path):
            os.remove(link_path)

        os.symlink(os.path.abspath(image_path), link_path)

        exec_shell_command_async(
            f"matugen image {shlex.quote(image_path)} --source-color-index 0"
        )

        self.colors_generated(image_path)

    def get_wallpaper_info(self, image_path: str) -> dict:
        stat = os.stat(image_path)

        return {
            "path": image_path,
            "filename": os.path.basename(image_path),
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "has_thumbnail": self.has_thumbnail(image_path),
            "thumbnail_path": self.get_thumbnail_path(image_path),
        }
