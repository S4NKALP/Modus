"""
Emoji plugin for the launcher.
Provides quick access to emojis with search functionality.
"""

import json
import os
import subprocess
from typing import Dict, List

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
        self.emoji_path = get_relative_path("../../../config/emoji.json")

    def initialize(self):
        """Initialize the emoji plugin."""
        self.set_triggers(["emoji", "emoji ", ";", "; "])
        self._load_emoji_data()

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

    def _copy_to_clipboard(self, emoji: str):
        """Copy emoji to clipboard."""
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
        except Exception as e:
            print(f"Failed to copy to clipboard: {e}")

    def query(self, query_string: str) -> List[Result]:
        """Search emojis based on query."""
        results = []
        query = query_string.lower().strip()

        # If no query, show some popular emojis
        if not query:
            popular_emojis = ["😀", "👍", "❤️", "🎉", "🔥", "✨", "🚀", "🌈"]
            for emoji in popular_emojis:
                if emoji in self.emoji_data:
                    emoji_info = self.emoji_data[emoji]
                    results.append(self._create_emoji_result(emoji, emoji_info, 1.0))
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

        return Result(
            title=name,  # Show only the name, not the emoji
            subtitle=f"{group}",
            icon_markup=emoji,  # Use the emoji itself as the icon
            action=lambda e=emoji: self._copy_to_clipboard(e),
            relevance=relevance,
            plugin_name=self.display_name,
            data={"emoji": emoji, "name": name, "group": group},
        )
