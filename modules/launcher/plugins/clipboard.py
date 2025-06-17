"""
Clipboard plugin using cliphist for clipboard history management.
"""

import os
import subprocess
import sys
import tempfile
from typing import List, Dict
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
from gi.repository import GdkPixbuf, GLib


class ClipboardPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "clipboard"
        self.display_name = "Clipboard History"
        self.description = "Search and manage clipboard history using cliphist"

        # Initialize cache and temp directory
        self.tmp_dir = tempfile.mkdtemp(prefix="cliphist-")
        self.image_cache: Dict[str, GdkPixbuf.Pixbuf] = {}
        self.clipboard_items = []
        self._loading = False
        self._pending_updates = False

    def initialize(self):
        self.set_triggers(["clip", "clip "])
        """Initialize the plugin."""
        try:
            subprocess.run(["cliphist", "list"], capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            raise RuntimeError("cliphist is not installed or not working properly")

    def cleanup(self):
        """Cleanup the plugin."""
        try:
            if os.path.exists(self.tmp_dir):
                import shutil

                shutil.rmtree(self.tmp_dir)
            self.image_cache.clear()
        except Exception as e:
            print(f"Error cleaning up temporary files: {e}", file=sys.stderr)

    def _load_clipboard_items(self) -> List[str]:
        """Load clipboard items from cliphist."""
        try:
            result = subprocess.run(
                ["cliphist", "list"], capture_output=True, check=True
            )
            stdout_str = result.stdout.decode("utf-8", errors="replace")
            lines = stdout_str.strip().split("\n")
            return [line for line in lines if line and "<meta http-equiv" not in line]
        except subprocess.CalledProcessError as e:
            print(f"Error loading clipboard history: {e}", file=sys.stderr)
            return []
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            return []

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

    def _load_image_preview_async(self, item_id: str) -> GdkPixbuf.Pixbuf:
        """Load image preview asynchronously."""
        if item_id in self.image_cache:
            return self.image_cache[item_id]

        try:
            result = subprocess.run(
                ["cliphist", "decode", item_id], capture_output=True, check=True
            )
            pixbuf = self._create_pixbuf_from_bytes(result.stdout)
            if pixbuf:
                self.image_cache[item_id] = pixbuf
            return pixbuf
        except Exception as e:
            print(f"Error loading image preview: {e}", file=sys.stderr)
            return None

    def query(self, query_string: str) -> List[Result]:
        """Search clipboard history using cliphist."""
        results = []

        # Handle query string
        if query_string.lower() == "clip":
            query_string = ""  # Show all items

        try:
            # Load clipboard items
            self.clipboard_items = self._load_clipboard_items()

            # Filter items based on query
            filtered_items = []
            for item in self.clipboard_items:
                parts = item.split("\t", 1)
                content = parts[1] if len(parts) > 1 else item
                if not query_string or query_string.lower() in content.lower():
                    filtered_items.append(item)

            # Process all items without batching
            for item in filtered_items:
                parts = item.split("\t", 1)
                item_id = parts[0] if len(parts) > 1 else "0"
                content = parts[1] if len(parts) > 1 else item

                # Handle image content
                if self._is_image_data(content):
                    pixbuf = self._load_image_preview_async(item_id)
                    if pixbuf:
                        result = Result(
                            title="Image from clipboard",
                            subtitle="Click to copy image to clipboard",
                            description="Image content",
                            icon=pixbuf,
                            relevance=1.0,
                            plugin_name=self.name,
                            action=lambda id=item_id: self._copy_to_clipboard(id),
                            data={"bypass_max_results": True},
                        )
                        results.append(result)
                        continue

                # Handle text content
                display_text = self._get_text_preview(content)
                result = Result(
                    title=display_text,
                    subtitle="Text from clipboard",
                    description=content,
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
        """Copy entry to clipboard using cliphist."""
        try:
            result = subprocess.run(
                ["cliphist", "decode", entry_id], capture_output=True, check=True
            )
            # Use wl-copy for Wayland or xclip for X11
            try:
                subprocess.run(["wl-copy"], input=result.stdout, check=True)
            except subprocess.SubprocessError:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=result.stdout,
                    check=True,
                )
        except subprocess.SubprocessError as e:
            print(f"Error copying to clipboard: {e}", file=sys.stderr)
