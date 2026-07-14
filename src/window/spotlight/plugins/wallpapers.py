import os
import random
from typing import Any

from fabric.utils import logger

from services.wallpaper import WallpaperService, create_thumbnail
from shared.data import WALLPAPERS_THUMBNAILS_SIZE
from utils.functions import fuzzy_filter
from window.spotlight.api import SearchResult, SpotlightPlugin

MAX_THUMBS_PER_SEARCH = 3


class WallpaperPlugin(SpotlightPlugin):
    id = "wallpaper"
    name = "Wallpaper"
    icon = "wallpaper"
    keywords = ["wall", "wr"]
    searchable = True
    priority = 85

    def __init__(self, context):
        super().__init__(context)
        self._wallpaper_service: WallpaperService | None = None

    def initialize(self) -> None:
        self._wallpaper_service = WallpaperService()

    def cleanup(self) -> None:
        self._wallpaper_service = None

    def release_memory(self) -> None:
        if self._wallpaper_service:
            self._wallpaper_service.invalidate_cache()

    def search(self, query: str, token: Any) -> list[SearchResult]:
        service = self._wallpaper_service
        if not service:
            return []

        q = query.strip()
        for prefix in ("wall ", "wr "):
            if q.lower().startswith(prefix):
                q = q[len(prefix) :].strip()
                break
        if q.lower() in ("wall", "wr"):
            q = ""

        all_files = service.get_all_wallpapers()
        if not all_files:
            return []

        if q:
            filtered = fuzzy_filter(q, all_files, key=os.path.basename, limit=50)
        else:
            filtered = all_files[:50]

        results: list[SearchResult] = []
        thumbs_created = 0

        for image_path in filtered:
            if token.is_cancelled or not self._wallpaper_service:
                return []

            thumbnail_path = service.get_thumbnail_path(image_path)

            if not service.has_thumbnail(image_path):
                if thumbs_created >= MAX_THUMBS_PER_SEARCH:
                    continue
                try:
                    create_thumbnail(
                        image_path, thumbnail_path, WALLPAPERS_THUMBNAILS_SIZE
                    )
                    thumbs_created += 1
                except Exception as e:
                    logger.warning(
                        f"[wallpapers] create_thumbnail( image_path, thumbnail_path, WALLPAPERS_... failed: {e}"
                    )
                    continue

            filename = os.path.basename(image_path)
            results.append(
                SearchResult(
                    id=f"wall_{filename}",
                    title=filename,
                    subtitle=image_path,
                    icon_name="",
                    score=80.0,
                    render_type="wallpaper",
                    action=lambda p=image_path: self._set_wallpaper(p),
                    metadata={
                        "image_path": image_path,
                        "thumbnail_path": thumbnail_path,
                    },
                )
            )

        return results

    def _set_wallpaper(self, path: str) -> None:
        service = self._wallpaper_service
        if service:
            service.set_wallpaper(path)
            service.invalidate_cache()

    def apply_random_wallpaper(self) -> None:
        service = self._wallpaper_service
        if not service:
            return
        service.invalidate_cache()
        files = service.get_all_wallpapers()
        if files:
            service.set_wallpaper(random.choice(files))

    def handle_external(self, command: str, args: str) -> None:
        if command == "wr":
            self.apply_random_wallpaper()


PLUGIN = WallpaperPlugin
