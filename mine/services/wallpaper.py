import hashlib
import mimetypes

from fabric.core import Service, Signal
from fabric.utils import GdkPixbuf as gdk_pixbuf
from fabric.utils import exec_shell_command_async, os

from config.data import (
    WALLPAPER_PATH,
    WALLPAPER_THUMBS_PATH,
    WALLPAPERS_THUMBNAILS_SIZE,
)

for path in (WALLPAPER_PATH, WALLPAPER_THUMBS_PATH):
    os.makedirs(path, exist_ok=True)


def get_thumbnail_filename(image_path: str) -> str:
    key = hashlib.sha256(image_path.encode()).hexdigest()
    size = WALLPAPERS_THUMBNAILS_SIZE
    return f"{key}_{size}x{size}.webp"


def create_thumbnail(
    image_path: str, thumbnail_path: str, size: int = WALLPAPERS_THUMBNAILS_SIZE
) -> bool:
    """Create WebP thumbnail with proper memory cleanup to prevent leaks."""
    pixbuf = None
    try:
        # Load image at scaled size to minimize memory usage
        pixbuf = gdk_pixbuf.Pixbuf.new_from_file_at_scale(image_path, size, size, True)
        # Save as WebP with quality 85 for better compression (60-80% smaller than PNG)
        result = pixbuf.savev(thumbnail_path, "webp", ["quality"], ["85"])
        return bool(result)
    except Exception:
        return False
    finally:
        # Explicitly clear pixbuf reference to free memory
        if pixbuf is not None:
            del pixbuf


def generate_colors_from_wallpaper(image_path: str) -> bool:
    cmd = f'matugen image "{image_path}"'
    return bool(exec_shell_command_async(cmd))


class WallpaperService(Service):
    @Signal
    def wallpaper_ready(self, image_path: str, thumbnail_path: str) -> None: ...

    @Signal
    def wallpaper_set(self, image_path: str) -> None: ...

    @Signal
    def colors_generated(self, image_path: str) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._processed_count = 0

    def get_all_wallpapers(self) -> list[str]:
        all_files = []
        for file in os.listdir(WALLPAPER_PATH):
            file_full = WALLPAPER_PATH + "/" + file
            mt = mimetypes.guess_type(file_full)[0]
            if mt and mt.startswith("image/"):
                all_files.append(file_full)
        return all_files

    def get_thumbnail_path(self, image_path: str) -> str:
        thumbnail_filename = get_thumbnail_filename(image_path)
        return WALLPAPER_THUMBS_PATH + "/" + thumbnail_filename

    def has_thumbnail(self, image_path: str) -> bool:
        thumbnail_path = self.get_thumbnail_path(image_path)
        return os.path.isfile(thumbnail_path)

    def set_wallpaper(self, image_path: str):
        exec_shell_command_async(
            f"awww img {image_path} --transition-type none --transition-duration 0 --transition-fps 60"
        )
        self.wallpaper_set(image_path)

        target_path = os.path.abspath(image_path)
        home_dir = os.path.expanduser("~")
        link_path = os.path.join(home_dir, ".current.wall")

        if os.path.islink(link_path) or os.path.exists(link_path):
            os.remove(link_path)

        os.symlink(target_path, link_path)

        exec_shell_command_async(f'matugen image "{image_path}" --source-color-index 0')
        self.colors_generated(image_path)

    def get_wallpaper_info(self, image_path: str) -> dict:
        """Get information about a wallpaper"""
        stat = os.stat(image_path)
        return {
            "path": image_path,
            "filename": os.path.basename(image_path),
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "has_thumbnail": self.has_thumbnail(image_path),
            "thumbnail_path": self.get_thumbnail_path(image_path),
        }
