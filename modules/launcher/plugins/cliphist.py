import re
import subprocess
from typing import List, Dict, Any

import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf

from . import LauncherPlugin


class CliphistPlugin(LauncherPlugin):
    """Plugin for clipboard history functionality using cliphist"""

    @property
    def name(self) -> str:
        return "Clipboard History"

    @property
    def category(self) -> str:
        return "Utilities"

    @property
    def icon_name(self) -> str:
        return "edit-paste-symbolic"

    def search(self, query: str) -> List[Dict[str, Any]]:
        if not query:
            return []

        query_lower = query.lower()

        # Show clipboard history when user types "clip" (like Albert launcher)
        if query_lower == "clip" or query_lower == "clipboard":
            return self._get_clipboard_history()

        # Also show clipboard history if query starts with "clip " for further filtering
        if query_lower.startswith("clip ") and len(query) > 5:
            search_term = query[5:].strip()  # Remove "clip " prefix
            return self._get_clipboard_history(search_term)

        return []

    def _get_clipboard_history(self, search_term: str = "") -> List[Dict[str, Any]]:
        """Get clipboard history, optionally filtered by search term"""
        try:
            # Get clipboard history from cliphist
            result = subprocess.run(
                ["cliphist", "list"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                return []

            entries = result.stdout.strip().split('\n')
            if not entries or entries == ['']:
                return []

            results = []
            search_lower = search_term.lower() if search_term else ""

            for entry in entries[:50]:  # Limit to first 50 entries for performance
                if not entry.strip():
                    continue

                # Parse entry format: "ID\tCONTENT"
                parts = entry.split('\t', 1)
                if len(parts) != 2:
                    continue

                entry_id, content = parts
                content = content.strip()

                # Check if this is an image
                is_image = self._is_image_data(content)

                # Skip binary data entries that aren't images
                if content.startswith('[[') and 'binary data' in content and not is_image:
                    continue

                # If we have a search term, filter by it
                if search_term and search_lower not in content.lower():
                    continue

                # Prepare display content and icon
                if is_image:
                    display_content = "[Image]"
                    # Try to load image preview
                    image_pixbuf = self._load_image_preview(entry_id)
                    if image_pixbuf:
                        result_item = {
                            "title": display_content,
                            "image_pixbuf": image_pixbuf,  # Custom field for image preview
                            "action": lambda eid=entry_id: self.copy_to_clipboard(eid),
                            "clip_id": entry_id,
                        }
                    else:
                        result_item = {
                            "title": display_content,
                            "icon_name": "image-x-generic-symbolic",
                            "action": lambda eid=entry_id: self.copy_to_clipboard(eid),
                            "clip_id": entry_id,
                        }
                else:
                    # Truncate long content for display
                    display_content = content
                    if len(display_content) > 80:
                        display_content = display_content[:77] + "..."
                    # Replace newlines with spaces for display
                    display_content = display_content.replace('\n', ' ').replace('\r', ' ')

                    result_item = {
                        "title": display_content,
                        "icon_name": "edit-paste-symbolic",
                        "action": lambda eid=entry_id: self.copy_to_clipboard(eid),
                        "clip_id": entry_id,
                    }

                results.append(result_item)

                # # Limit results to prevent overwhelming the UI
                # if len(results) >= 15:
                #     break

            # Sort results by relevance if we have a search term
            if search_term:
                def sort_key(item):
                    title = item["title"].lower()
                    if title.startswith(search_lower):
                        return 0  # Starts with query
                    elif search_lower in title:
                        return 1  # Contains query
                    else:
                        return 2  # Other matches
                results.sort(key=sort_key)

            return results

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return []
        except Exception as e:
            print(f"Error in cliphist plugin: {e}")
            return []

    def copy_to_clipboard(self, entry_id: str):
        """Copy clipboard history entry back to clipboard"""
        try:
            # Use cliphist decode to get the content and pipe it to wl-copy
            decode_process = subprocess.Popen(
                ["cliphist", "decode", entry_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )

            copy_process = subprocess.Popen(
                ["wl-copy"],
                stdin=decode_process.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            decode_process.stdout.close()  # Allow decode_process to receive SIGPIPE
            copy_process.wait(timeout=2)
            decode_process.wait(timeout=2)

            print(f"Copied clipboard history entry {entry_id}")

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            try:
                # Fallback to xclip
                decode_process = subprocess.Popen(
                    ["cliphist", "decode", entry_id],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True
                )

                content, _ = decode_process.communicate(timeout=2)

                if decode_process.returncode == 0:
                    subprocess.Popen(
                        ["xclip", "-selection", "clipboard"],
                        input=content,
                        text=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    print(f"Copied clipboard history entry {entry_id} (xclip)")

            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                print(f"Could not copy clipboard history entry {entry_id}")
        except Exception as e:
            print(f"Error copying clipboard entry: {e}")

    def _is_image_data(self, content):
        """Determine if clipboard content is likely an image"""
        return (
            content.startswith("data:image/") or
            content.startswith("\x89PNG") or
            content.startswith("GIF8") or
            content.startswith("\xff\xd8\xff") or
            re.match(r'^\s*<img\s+', content) is not None or
            "binary" in content.lower() and any(ext in content.lower() for ext in ["jpg", "jpeg", "png", "bmp", "gif"])
        )

    def _load_image_preview(self, item_id):
        """Load image preview for clipboard item"""
        try:
            result = subprocess.run(
                ["cliphist", "decode", item_id],
                capture_output=True,
                check=True,
                timeout=2
            )

            # Try to load the image data
            loader = GdkPixbuf.PixbufLoader()
            loader.write(result.stdout)
            loader.close()
            pixbuf = loader.get_pixbuf()

            if pixbuf:
                # Scale to thumbnail size
                width, height = pixbuf.get_width(), pixbuf.get_height()
                max_size = 128  # Match launcher icon size
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))

                scaled_pixbuf = pixbuf.scale_simple(
                    new_width, new_height, GdkPixbuf.InterpType.BILINEAR
                )
                return scaled_pixbuf

        except Exception as e:
           pass

        return None

    def get_action_items(self, query: str) -> List[Dict[str, Any]]:
        """Get quick action items for clipboard history"""
        if not query or len(query) < 2:
            return []

        return [
            {
                "title": f'Search clipboard history for "{query}"',
                "icon_name": "edit-paste-symbolic",
                "action": lambda: None,  # No specific action needed
            }
        ]


