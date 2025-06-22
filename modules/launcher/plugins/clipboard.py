"""
Clipboard plugin using cliphist for clipboard history management.
Optimized for performance with caching, threading, and lazy loading.
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
from gi.repository import GdkPixbuf, GLib


class ClipboardPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "clipboard"
        self.display_name = "Clipboard History"
        self.description = "Search and manage clipboard history using cliphist"

        # Performance settings
        self.max_results = 20
        self.cache_ttl = 5  # Cache clipboard items for 5 seconds (more responsive)
        self.image_cache_ttl = 300  # Cache images for 5 minutes

        # Initialize cache and temp directory
        self.tmp_dir = tempfile.mkdtemp(prefix="cliphist-")
        self.image_cache: Dict[str, GdkPixbuf.Pixbuf] = {}
        self.clipboard_items_cache: List[str] = []
        self.cache_timestamp = 0
        self.image_cache_timestamps: Dict[str, float] = {}

        # Threading
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="clipboard")
        self.cache_lock = threading.Lock()

        # State tracking
        self._loading = False
        self._pending_updates = False

    def initialize(self):
        """Initialize the plugin."""
        self.set_triggers(["clip", "clip "])
        try:
            subprocess.run(["cliphist", "list"], capture_output=True, check=True, timeout=5)
        except (subprocess.SubprocessError, FileNotFoundError):
            raise RuntimeError("cliphist is not installed or not working properly")

        # Pre-warm cache in background
        self.executor.submit(self._load_clipboard_items_cached)

    def cleanup(self):
        """Cleanup the plugin."""
        try:
            # Shutdown executor
            if hasattr(self, 'executor'):
                self.executor.shutdown(wait=False)

            # Clean up temp files
            if os.path.exists(self.tmp_dir):
                import shutil
                shutil.rmtree(self.tmp_dir)

            # Clear caches
            with self.cache_lock:
                self.image_cache.clear()
                self.clipboard_items_cache.clear()
                self.image_cache_timestamps.clear()
        except Exception as e:
            print(f"Error cleaning up temporary files: {e}", file=sys.stderr)

    def invalidate_cache(self):
        """Force invalidation of the clipboard cache."""
        with self.cache_lock:
            self.clipboard_items_cache.clear()
            self.cache_timestamp = 0
            self.image_cache.clear()
            self.image_cache_timestamps.clear()

    def _force_launcher_refresh(self):
        """Force the launcher to refresh its results."""
        try:
            from gi.repository import GLib

            def trigger_refresh():
                try:
                    # Try to access the launcher through the fabric Application
                    from fabric import Application
                    app = Application.get_default()

                    if app and hasattr(app, 'launcher'):
                        launcher = app.launcher
                        if launcher and hasattr(launcher, 'search_entry') and hasattr(launcher, '_perform_search'):
                            # Get current search text to preserve the query
                            current_text = launcher.search_entry.get_text()
                            # Trigger the search to refresh results
                            launcher._perform_search(current_text)
                            return False

                    # Fallback: try to find launcher instance through other means
                    import gc
                    for obj in gc.get_objects():
                        if (hasattr(obj, '__class__') and obj.__class__.__name__ == 'Launcher'):
                            if hasattr(obj, 'search_entry') and hasattr(obj, '_perform_search'):
                                current_text = obj.search_entry.get_text()
                                obj._perform_search(current_text)
                                return False

                except Exception as e:
                    print(f"Error forcing launcher refresh: {e}")

                return False  # Don't repeat

            # Use immediate refresh
            GLib.timeout_add(10, trigger_refresh)

        except Exception as e:
            print(f"Could not trigger refresh: {e}")



    def _load_clipboard_items_cached(self) -> List[str]:
        """Load clipboard items from cliphist with caching and change detection."""
        current_time = time.time()

        # Always load fresh data to check for changes
        try:
            result = subprocess.run(
                ["cliphist", "list"], capture_output=True, check=True, timeout=5
            )
            stdout_str = result.stdout.decode("utf-8", errors="replace")
            if stdout_str.strip():
                lines = stdout_str.strip().split("\n")
                items = [line for line in lines if line and "<meta http-equiv" not in line]
            else:
                items = []

            # Check if data has changed
            with self.cache_lock:
                data_changed = (
                    not self.clipboard_items_cache or
                    len(items) != len(self.clipboard_items_cache) or
                    items != self.clipboard_items_cache
                )

                # If cache is still valid and data hasn't changed, return cached data
                if (not data_changed and
                    self.clipboard_items_cache and
                    current_time - self.cache_timestamp < self.cache_ttl):
                    return self.clipboard_items_cache.copy()

                # Update cache with fresh data
                self.clipboard_items_cache = items
                self.cache_timestamp = current_time

                # If data changed significantly, clear image cache too
                if data_changed:
                    self.image_cache.clear()
                    self.image_cache_timestamps.clear()

            return items
        except subprocess.CalledProcessError as e:
            print(f"Error loading clipboard history: {e}", file=sys.stderr)
            return []
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            return []

    def _load_clipboard_items(self) -> List[str]:
        """Load clipboard items (legacy method for compatibility)."""
        return self._load_clipboard_items_cached()

    def _create_pixbuf_from_bytes(
        self, image_data: bytes, max_size: int = 100
    ) -> GdkPixbuf.Pixbuf:
        """Create a GdkPixbuf from image bytes with size limit."""
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(image_data)
            loader.close()
            pixbuf = loader.get_pixbuf()

            # Scale image if needed
            width, height = pixbuf.get_width(), pixbuf.get_height()
            if width > height:
                new_width = max_size
                new_height = int(height * (max_size / width))
            else:
                new_height = max_size
                new_width = int(width * (max_size / height))

            return pixbuf.scale_simple(
                new_width, new_height, GdkPixbuf.InterpType.BILINEAR
            )
        except GLib.Error:
            return None

    def _is_image_data(self, content: str) -> bool:
        """Determine if clipboard content is likely an image."""
        return "binary" in content.lower() and any(
            ext in content.lower() for ext in ["jpg", "jpeg", "png", "bmp", "gif"]
        )

    def _get_text_preview(self, content: str) -> str:
        """Get a text preview of the content."""
        if len(content) > 50:
            return content[:37] + "..."
        return content

    def _load_image_preview_cached(self, item_id: str) -> Optional[GdkPixbuf.Pixbuf]:
        """Load image preview with caching and timeout."""
        current_time = time.time()

        # Check cache first
        with self.cache_lock:
            if (item_id in self.image_cache and
                item_id in self.image_cache_timestamps and
                current_time - self.image_cache_timestamps[item_id] < self.image_cache_ttl):
                return self.image_cache[item_id]

        try:
            result = subprocess.run(
                ["cliphist", "decode", item_id], capture_output=True, check=True, timeout=3
            )
            pixbuf = self._create_pixbuf_from_bytes(result.stdout)
            if pixbuf:
                with self.cache_lock:
                    self.image_cache[item_id] = pixbuf
                    self.image_cache_timestamps[item_id] = current_time
            return pixbuf
        except Exception as e:
            print(f"Error loading image preview: {e}", file=sys.stderr)
            return None

    def _load_image_preview_async(self, item_id: str) -> Optional[GdkPixbuf.Pixbuf]:
        """Load image preview (legacy method for compatibility)."""
        return self._load_image_preview_cached(item_id)

    def query(self, query_string: str) -> List[Result]:
        """Search clipboard history using cliphist with optimized performance."""
        results = []

        # Handle query string
        if query_string.lower() == "clip":
            query_string = ""  # Show all items

        try:
            # Load clipboard items from cache
            clipboard_items = self._load_clipboard_items_cached()

            # Early exit if no items
            if not clipboard_items:
                return results

            # Filter items based on query with early termination
            filtered_items = []
            query_lower = query_string.lower() if query_string else ""

            for item in clipboard_items:
                # Stop if we have enough results
                if len(filtered_items) >= self.max_results:
                    break

                parts = item.split("\t", 1)
                content = parts[1] if len(parts) > 1 else item

                # Fast filtering
                if not query_lower or query_lower in content.lower():
                    filtered_items.append(item)

            # Process items with lazy image loading
            for i, item in enumerate(filtered_items):
                # Limit total results
                if len(results) >= self.max_results:
                    break

                parts = item.split("\t", 1)
                item_id = parts[0] if len(parts) > 1 else str(i)
                content = parts[1] if len(parts) > 1 else item

                # Handle image content with lazy loading
                if self._is_image_data(content):
                    # Check if image is already cached
                    cached_pixbuf = None
                    with self.cache_lock:
                        cached_pixbuf = self.image_cache.get(item_id)

                    if cached_pixbuf:
                        # Use cached image
                        result = Result(
                            title="Image from clipboard",
                            subtitle="Click to copy image to clipboard",
                            description="Image content",
                            icon=cached_pixbuf,
                            relevance=1.0,
                            plugin_name=self.name,
                            action=lambda id=item_id: self._copy_to_clipboard(id),
                            data={"bypass_max_results": True},
                        )
                    else:
                        # Show placeholder and load image in background
                        result = Result(
                            title="Image from clipboard",
                            subtitle="Loading preview...",
                            description="Image content",
                            icon_name="image-x-generic",
                            relevance=1.0,
                            plugin_name=self.name,
                            action=lambda id=item_id: self._copy_to_clipboard(id),
                            data={"bypass_max_results": True},
                        )
                        # Load image in background (don't wait for it)
                        self.executor.submit(self._load_image_preview_cached, item_id)

                    results.append(result)
                    continue

                # Handle text content
                display_text = self._get_text_preview(content)
                result = Result(
                    title=display_text,
                    subtitle="Text from clipboard",
                    description=content if len(content) <= 100 else content[:97] + "...",
                    icon_name="edit-paste",
                    relevance=1.0,
                    plugin_name=self.name,
                    action=lambda id=item_id: self._copy_to_clipboard(id),
                    data={"bypass_max_results": True},
                )
                results.append(result)

        except Exception as e:
            # Handle errors gracefully
            results.append(
                Result(
                    title="Error accessing clipboard history",
                    subtitle=str(e),
                    icon_name="dialog-error",
                    relevance=0.0,
                    plugin_name=self.name,
                    data={"bypass_max_results": True},
                )
            )

        return results

    def _copy_to_clipboard(self, entry_id: str):
        """Copy entry to clipboard using cliphist with timeout."""
        try:
            result = subprocess.run(
                ["cliphist", "decode", entry_id], capture_output=True, check=True, timeout=5
            )
            # Use wl-copy for Wayland or xclip for X11
            try:
                subprocess.run(["wl-copy"], input=result.stdout, check=True, timeout=3)
            except subprocess.SubprocessError:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=result.stdout,
                    check=True,
                    timeout=3
                )

            # Invalidate cache since clipboard content has changed
            self.invalidate_cache()

        except subprocess.SubprocessError as e:
            print(f"Error copying to clipboard: {e}", file=sys.stderr)
        except subprocess.TimeoutExpired as e:
            print(f"Timeout copying to clipboard: {e}", file=sys.stderr)
