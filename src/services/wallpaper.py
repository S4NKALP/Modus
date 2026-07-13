import hashlib
import mimetypes

from fabric.core import Service, Signal
from fabric.utils import GdkPixbuf as gdk_pixbuf
from fabric.utils import exec_shell_command_async, os

from shared.data import (
    WALLPAPER_PATH,
    WALLPAPER_THUMBS_PATH,
    WALLPAPERS_THUMBNAILS_SIZE,
)

os.makedirs(WALLPAPER_PATH, exist_ok=True)
os.makedirs(WALLPAPER_THUMBS_PATH, exist_ok=True)


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

    except Exception:
        return False


def generate_colors_from_wallpaper(image_path: str) -> bool:
    return bool(exec_shell_command_async(f'matugen image "{image_path}"'))


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

    def get_all_wallpapers(self, use_cache: bool = True) -> list[str]:
        if use_cache and self._file_cache is not None:
            return self._file_cache

        wallpapers: list[str] = []

        with os.scandir(WALLPAPER_PATH) as entries:
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
        return os.path.join(
            WALLPAPER_THUMBS_PATH,
            get_thumbnail_filename(image_path),
        )

    def has_thumbnail(self, image_path: str) -> bool:
        return os.path.isfile(self.get_thumbnail_path(image_path))

    def set_wallpaper(self, image_path: str) -> None:
        exec_shell_command_async(
            f'awww img "{image_path}" '
            "--transition-type none "
            "--transition-duration 0 "
            "--transition-fps 60"
        )

        self.wallpaper_set(image_path)

        link_path = os.path.expanduser("~/.current.wall")

        if os.path.lexists(link_path):
            os.remove(link_path)

        os.symlink(os.path.abspath(image_path), link_path)

        exec_shell_command_async(f'matugen image "{image_path}" --source-color-index 0')

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
