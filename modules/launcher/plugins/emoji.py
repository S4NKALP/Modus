import json
import os
import subprocess
import time
from collections import OrderedDict
from typing import Dict, List

import config.data as data
from fabric.utils import get_relative_path
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class EmojiPlugin(PluginBase):
    """
    Plugin for searching and copying emojis.
    """

    def __init__(self):
        super().__init__()
        self.name = "emoji"
        self.display_name = "Emoji"
        self.description = "Search and copy emojis"
        self.emoji_data = {}
        self.emoji_path = get_relative_path("../../../config/json/emoji.json")

        # Use cache directory for recent emojis (save directly in cache dir)
        self.recent_emoji_path = os.path.join(data.CACHE_DIR, "recent_emoji.json")
        self.recent_emojis = OrderedDict()
        self.max_recent_emojis = 20  # Maximum number of recent emojis to track

    def initialize(self):
        """Initialize the emoji plugin."""
        self.set_triggers(["emoji", ";"])
        self._load_emoji_data()
        self._load_recent_emojis()

    def cleanup(self):
        """Cleanup the emoji plugin."""
        pass

    def _load_emoji_data(self):
        """Load emoji data from JSON file."""
        try:
            if os.path.exists(self.emoji_path):
                with open(self.emoji_path, "r", encoding="utf-8") as f:
                    self.emoji_data = json.load(f)
            else:
                print(f"Emoji file not found: {self.emoji_path}")
        except Exception as e:
            print(f"Error loading emoji data: {e}")

    def _load_recent_emojis(self):
        """Load recently used emojis from JSON file."""
        try:
            if os.path.exists(self.recent_emoji_path):
                with open(self.recent_emoji_path, "r", encoding="utf-8") as f:
                    recent_data = json.load(f)
                    # Convert to OrderedDict to maintain order
                    self.recent_emojis = OrderedDict(recent_data)
            else:
                # Create empty recent emojis file
                self.recent_emojis = OrderedDict()
                self._save_recent_emojis()
        except Exception as e:
            print(f"Error loading recent emoji data: {e}")
            self.recent_emojis = OrderedDict()

    def _save_recent_emojis(self):
        """Save recently used emojis to JSON file."""
        try:
            # Ensure the cache directory exists
            os.makedirs(data.CACHE_DIR, exist_ok=True)

            with open(self.recent_emoji_path, "w", encoding="utf-8") as f:
                json.dump(dict(self.recent_emojis), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving recent emoji data: {e}")

    def _add_to_recent(self, emoji: str):
        """Add an emoji to the recent list."""
        # Remove if already exists (to move it to front)
        if emoji in self.recent_emojis:
            del self.recent_emojis[emoji]

        # Add to front with current timestamp
        self.recent_emojis[emoji] = time.time()

        # Keep only the most recent emojis
        while len(self.recent_emojis) > self.max_recent_emojis:
            # Remove the oldest item
            self.recent_emojis.popitem(last=False)

        # Save to file
        self._save_recent_emojis()

    def _copy_to_clipboard(self, emoji: str):
        """Copy emoji to clipboard and track usage."""
        try:
            # Try Wayland first
            try:
                subprocess.run(["wl-copy"], input=emoji.encode(), check=True)
            except subprocess.SubprocessError:
                # Fall back to X11
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=emoji.encode(),
                    check=True,
                )

            # Track this emoji as recently used
            self._add_to_recent(emoji)

        except Exception as e:
            print(f"Failed to copy to clipboard: {e}")

    def query(self, query_string: str) -> List[Result]:
        """Search emojis based on query."""
        results = []
        query = query_string.lower().strip()

        # If no query, show recently used emojis
        if not query:
            if self.recent_emojis:
                # Show recent emojis in reverse order (most recent first)
                for emoji in reversed(list(self.recent_emojis.keys())):
                    if emoji in self.emoji_data:
                        emoji_info = self.emoji_data[emoji]
                        results.append(
                            self._create_emoji_result(emoji, emoji_info, 1.0)
                        )
            else:
                # If no recent emojis, show some popular ones as fallback
                popular_emojis = ["😀", "👍", "❤️", "🎉", "🔥", "✨", "🚀", "🌈"]
                for emoji in popular_emojis:
                    if emoji in self.emoji_data:
                        emoji_info = self.emoji_data[emoji]
                        results.append(
                            self._create_emoji_result(emoji, emoji_info, 1.0)
                        )
            return results

        # Search by name, group, or the emoji itself
        for emoji, info in self.emoji_data.items():
            relevance = 0
            name = info.get("name", "").lower()
            group = info.get("group", "").lower()
            slug = info.get("slug", "").lower()

            # Exact match with emoji
            if query == emoji:
                relevance = 1.0
            # Name contains query
            elif query in name:
                relevance = 0.9
            # Slug contains query
            elif query in slug:
                relevance = 0.8
            # Group contains query
            elif query in group:
                relevance = 0.7

            if relevance > 0:
                results.append(self._create_emoji_result(emoji, info, relevance))

        # Sort by relevance
        results.sort(key=lambda x: x.relevance, reverse=True)
        return results[:20]  # Limit to 20 results

    def _create_emoji_result(self, emoji: str, info: Dict, relevance: float) -> Result:
        """Create a Result object for an emoji."""
        name = info.get("name", "")
        group = info.get("group", "")

        # Check if this is a recently used emoji
        is_recent = emoji in self.recent_emojis
        subtitle = f"{group}" + (" • Recently used" if is_recent else "")

        return Result(
            title=name,  # Show only the name, not the emoji
            subtitle=subtitle,
            icon_markup=emoji,  # Use the emoji itself as the icon
            action=lambda e=emoji: self._copy_to_clipboard(e),
            relevance=relevance,
            plugin_name=self.display_name,
            data={"emoji": emoji, "name": name, "group": group, "recent": is_recent},
        )
