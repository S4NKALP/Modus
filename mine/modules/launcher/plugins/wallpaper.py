import contextlib
import gc
import random

from fabric.utils import idle_add, os, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from thefuzz import fuzz, process

from config.data import WALLPAPERS_THUMBNAILS_SIZE
from modules.launcher.base import LauncherPlugin
from services import WallpaperService, create_thumbnail


class WallpaperPlugin(LauncherPlugin):
    # Memory optimization: large sliding window for virtual scrolling
    BATCH_SIZE = 10  # Load 10 at a time for smooth UI
    MAX_VISIBLE_WIDGETS = (
        100  # Keep 100 widgets in memory (allows scrolling back/forth)
    )

    @property
    def name(self) -> str:
        return "wallpaper"

    @property
    def icon(self) -> str:
        return "wallpaper"

    @property
    def keywords(self) -> list[str]:
        return ["wall", "wr"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self._current_widgets = []  # Track created widgets for cleanup
        self._batch_count = 0  # Track how many items loaded
        self._all_wallpapers = []  # Store paths instead of widgets

        self.wallpaper_service = WallpaperService()

    def on_search(self, text: str) -> None:
        self.query_wallpapers(text)

    def handle_external(self, command: str, args: str) -> None:
        if command == "wr":
            self.apply_random_wallpaper()

    def stop(self):
        """Stop loading and cleanup resources."""
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        self._cleanup_widgets()

    def _cleanup_widgets(self):
        """Destroy old widgets to free memory."""
        for widget in self._current_widgets:
            with contextlib.suppress(Exception):
                widget.destroy()
        self._current_widgets.clear()
        self._batch_count = 0

        gc.collect()

    def query_wallpapers(self, text: str) -> None:
        # Clean up previous query results
        self._cleanup_widgets()
        self._all_wallpapers.clear()

        self.handler.start("wallpapers")  # pyright: ignore[reportOptionalCall]

        all_files = self.wallpaper_service.get_all_wallpapers()

        if not all_files:
            self.handler.done()
            return

        if text.strip():
            filtered_files = [
                file_full
                for file_full, _ in process.extract(
                    text,
                    all_files,
                    scorer=fuzz.WRatio,
                    processor=os.path.basename,
                    limit=10,
                )
            ]
        else:
            filtered_files = all_files

        # Store all paths but only create widgets for visible ones
        self._all_wallpapers = filtered_files

        self._query_handler = idle_add(
            self.bake_next_wallpaper_slot, iter(filtered_files), pin=True
        )

    def bake_next_wallpaper_slot(self, iterator):
        """Load wallpapers in batches to prevent UI freezing."""
        for _ in range(self.BATCH_SIZE):
            if (image_path := next(iterator, None)) is None:
                idle_add(self.handler.done)  # pyright: ignore[reportArgumentType]
                return False

            self._batch_count += 1

            thumbnail_path = self.wallpaper_service.get_thumbnail_path(image_path)

            # Only create thumbnail if it doesn't exist
            if not self.wallpaper_service.has_thumbnail(image_path):
                try:
                    create_thumbnail(
                        image_path, thumbnail_path, WALLPAPERS_THUMBNAILS_SIZE
                    )
                except Exception:
                    # Skip if thumbnail creation fails
                    continue

            self.post_wallpaper_cache_check(image_path, thumbnail_path)

        # Continue loading next batch
        return True

    def post_wallpaper_cache_check(self, image_path: str, thumbnail_path: str):
        widget = Button(
            style_classes="app-slot wallpaper",
            child=Box(h_expand=True, v_expand=True)
            .build()
            .set_style(
                f"background-image: url('file://{thumbnail_path}');", compile=False
            )
            .unwrap(),
            on_clicked=lambda *_: (
                self.handler.launched and self.handler.launched(),
                self.wallpaper_service.set_wallpaper(image_path),
            ),
        )

        self._current_widgets.append(widget)

        # Once we exceed the window, remove oldest widgets
        if len(self._current_widgets) > self.MAX_VISIBLE_WIDGETS:
            widgets_to_remove = self._current_widgets[:20]
            self._current_widgets = self._current_widgets[20:]

            for old_widget in widgets_to_remove:
                with contextlib.suppress(Exception):
                    old_widget.destroy()

            gc.collect()

        return self.handler.slot_ready(  # pyright: ignore[reportOptionalCall]
            widget,
            "wallpapers",
        )

    def apply_random_wallpaper(self) -> None:
        files = self.wallpaper_service.get_all_wallpapers()
        if not files:
            self.handler.done()
            return
        chosen = random.choice(files)
        self.wallpaper_service.set_wallpaper(chosen)
        self.handler.done()
