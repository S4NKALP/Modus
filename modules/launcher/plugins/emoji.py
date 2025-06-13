import json
import os
import subprocess
from typing import List, Dict, Any
from . import LauncherPlugin


class EmojiPlugin(LauncherPlugin):
    """Plugin for emoji search and clipboard functionality"""

    def __init__(self):
        self._emojis = {}
        self._load_emojis()

    def _load_emojis(self):
        """Load emoji data from the JSON file"""
        try:
            emoji_file_path = os.path.expanduser("~/Modus/config/emoji.json")
            with open(emoji_file_path, "r", encoding="utf-8") as f:
                self._emojis = json.load(f)
        except Exception as e:
            print(f"Failed to load emoji data: {e}")
            self._emojis = {}

    @property
    def name(self) -> str:
        return "Emoji"

    @property
    def category(self) -> str:
        return "Utilities"

    @property
    def icon_name(self) -> str:
        return "face-smile-symbolic"

    def search(self, query: str) -> List[Dict[str, Any]]:
        if not query or len(query) < 2:  # Require at least 2 characters
            return []

        results = []
        query_lower = query.lower()

        # Search through emojis
        for emoji_char, emoji_data in self._emojis.items():
            # Search in name, slug, and group
            searchable_text = (
                emoji_data.get("name", "").lower()
                + " "
                + emoji_data.get("slug", "").lower()
                + " "
                + emoji_data.get("group", "").lower()
            )

            if query_lower in searchable_text:
                results.append(
                    {
                        "title": emoji_data.get('name', 'Unknown'),
                        "description": f"{emoji_data.get('group', 'Unknown')}",
                        "emoji_icon": emoji_char,  # Store the emoji character for display
                        "action": lambda emoji=emoji_char: self.copy_emoji(emoji),
                    }
                )

                # Limit results to prevent overwhelming the UI
                if len(results) >= 20:
                    break

        # Sort results by relevance (exact matches first)
        def sort_key(item):
            name = item["title"].lower()
            # Check if query matches the emoji name
            if name.startswith(query_lower):
                return 0  # Name starts with query
            elif query_lower in name:
                return 1  # Partial name match
            else:
                return 2  # Other matches

        results.sort(key=sort_key)
        return results

    def copy_emoji(self, emoji: str):
        """Copy emoji to clipboard using wl-copy"""
        # Use a fire-and-forget approach to avoid blocking
        try:
            # Start wl-copy in the background and don't wait for it
            subprocess.Popen(
                ["wl-copy", emoji], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print(f"Copied emoji to clipboard: {emoji}")
        except FileNotFoundError:
            try:
                # Fallback to xclip
                process = subprocess.Popen(
                    ["xclip", "-selection", "clipboard"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                process.stdin.write(emoji)
                process.stdin.close()
                print(f"Copied emoji to clipboard (xclip): {emoji}")
            except (FileNotFoundError, OSError):
                print(f"Could not copy emoji to clipboard: {emoji}")
        except OSError:
            print(f"Could not copy emoji to clipboard: {emoji}")

    def get_action_items(self, query: str) -> List[Dict[str, Any]]:
        """Get quick action items for emoji search"""
        if not query or len(query) < 2:
            return []

        # Return a quick action to search for emojis
        return [
            {
                "title": f'Search emojis for "{query}"',
                "icon_name": "face-smile-symbolic",
                "action": lambda: None,  # No specific action needed
            }
        ]
