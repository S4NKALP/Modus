import json
import subprocess
from collections import OrderedDict
from typing import Dict, List

from fabric.utils import os, time, GLib, logger

import shared.data as data
from window.launcher.plugin_base import PluginBase
from window.launcher.result import Result


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

        # Language detection (default to en)
        self.lang = os.getenv("LANG", "en").split("_")[0].split(".")[0]
        if not self.lang:
            self.lang = "en"

        # Paths
        self.state_dir = os.path.join(GLib.get_user_state_dir(), data.APP_NAME)
        self.emoji_path = os.path.join(self.state_dir, f"emojis_{self.lang}.json")

        # Use cache directory for recent emojis
        self.recent_emoji_path = os.path.join(data.CACHE_DIR, "recent_emoji.json")
        self.recent_emojis = OrderedDict()
        self.max_recent_emojis = 20
        self._is_downloading = False

    def initialize(self):
        """Initialize the emoji plugin."""
        self.set_triggers(["em"])
        self._load_recent_emojis()

        # Check if local data exists, if not trigger download
        if not os.path.exists(self.emoji_path):
            self._download_emoji_data()
        else:
            self._load_emoji_data()

    def cleanup(self):
        """Cleanup the emoji plugin."""
        pass

    def _download_emoji_data(self, force=False):
        """Download emoji annotations from CLDR repository."""
        if self._is_downloading and not force:
            return

        os.makedirs(self.state_dir, exist_ok=True)
        url = (
            "https://raw.githubusercontent.com/unicode-org/cldr-json/main/"
            f"cldr-json/cldr-annotations-full/annotations/{self.lang}/annotations.json"
        )

        self._is_downloading = True

        def on_done(*args):
            self._is_downloading = False
            if os.path.exists(self.emoji_path):
                self._load_emoji_data()
                logger.info(f"[Emoji] Data updated for language: {self.lang}")
            else:
                logger.error(f"[Emoji] Download failed for URL: {url}")

        logger.info(f"[Emoji] Starting download: {url}")
        from fabric.utils import exec_shell_command_async

        exec_shell_command_async(f"curl -L '{url}' -o '{self.emoji_path}'", on_done)

    def _load_emoji_data(self):
        """Load emoji data from JSON file and parse CLDR structure."""
        try:
            if os.path.exists(self.emoji_path):
                with open(self.emoji_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    self.emoji_data = self._parse_cldr_json(raw_data)
            else:
                logger.warning(f"[Emoji] Local data missing: {self.emoji_path}")
        except Exception as e:
            logger.error(f"[Emoji] Error loading emoji data: {e}")

    def _parse_cldr_json(self, raw_data: Dict) -> Dict:
        """Parse CLDR annotations JSON into a flatter format for searching."""
        try:
            # Structure matches individual file: annotations -> annotations
            annotations_container = raw_data.get("annotations", {})
            raw_annotations = annotations_container.get("annotations", {})

            if not raw_annotations:
                # Fallback to the nested structure just in case it's a full bundle
                main = raw_data.get("main", {})
                lang_data = main.get(self.lang, main.get("en", {}))
                annotations_container = lang_data.get("annotations", {})
                raw_annotations = annotations_container.get("annotations", {})

            parsed = {}
            for emoji, info in raw_annotations.items():
                # Extract TTL (name)
                tts = info.get("tts", [""])
                name = tts[0] if isinstance(tts, list) else tts

                # Extract keywords
                keywords = info.get("default", [])
                if isinstance(keywords, str):
                    keywords = [keywords]

                parsed[emoji] = {
                    "name": name,
                    "keywords": keywords,
                }
            return parsed
        except Exception as e:
            logger.error(f"[Emoji] CLDR parsing error: {e}")
            return {}

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
            logger.error(f"Error loading recent emoji data: {e}")
            self.recent_emojis = OrderedDict()

    def _save_recent_emojis(self):
        """Save recently used emojis to JSON file."""
        try:
            # Ensure the cache directory exists
            os.makedirs(data.CACHE_DIR, exist_ok=True)

            with open(self.recent_emoji_path, "w", encoding="utf-8") as f:
                json.dump(dict(self.recent_emojis), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving recent emoji data: {e}")

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
            logger.error(f"Failed to copy to clipboard: {e}")

    def query(self, query_string: str) -> List[Result]:
        """Search emojis based on query."""
        results = []
        query = query_string.lower().strip()

        # Check if we need to download/reload data
        if not self.emoji_data and not self._is_downloading:
            if not os.path.exists(self.emoji_path):
                self._download_emoji_data()
            else:
                self._load_emoji_data()

        # Handle update command
        if query == "updatejson":
            self._download_emoji_data(force=True)
            return [
                Result(
                    title="Updating Emoji Database...",
                    subtitle=f"Downloading latest annotations for {self.lang}",
                    icon_name="view-refresh-symbolic",
                    relevance=1.0,
                    plugin_name=self.display_name,
                )
            ]

        # If data is not yet loaded and not downloading, try loading it
        if not self.emoji_data and not self._is_downloading:
            self._load_emoji_data()

        # Show status if downloading
        if self._is_downloading:
            results.append(
                Result(
                    title="Downloading Emoji Data...",
                    subtitle="Results will appear once finished",
                    icon_name="view-refresh-symbolic",
                    relevance=0.1,
                    plugin_name=self.display_name,
                )
            )

        # If no query, show recently used emojis
        if not query:
            if self.recent_emojis:
                for emoji in reversed(list(self.recent_emojis.keys())):
                    if emoji in self.emoji_data:
                        info = self.emoji_data[emoji]
                        results.append(self._create_emoji_result(emoji, info, 1.0))
            return results

        # Search by name, keywords, or the emoji itself
        for emoji, info in self.emoji_data.items():
            relevance = 0
            name = info.get("name", "").lower()
            keywords = info.get("keywords", [])

            # Exact match with emoji
            if query == emoji:
                relevance = 1.0
            # Exact match with name
            elif query == name:
                relevance = 0.95
            # Starts with name
            elif name.startswith(query):
                relevance = 0.9
            # Contains name
            elif query in name:
                relevance = 0.8
            # In keywords
            elif any(query == k.lower() for k in keywords):
                relevance = 0.7
            elif any(query in k.lower() for k in keywords):
                relevance = 0.6

            if relevance > 0:
                results.append(self._create_emoji_result(emoji, info, relevance))

        # Sort by relevance and limit
        results.sort(key=lambda x: x.relevance, reverse=True)
        return results[:20]

    def _create_emoji_result(self, emoji: str, info: Dict, relevance: float) -> Result:
        """Create a Result object for an emoji."""
        name = info.get("name", "").capitalize()
        keywords = ", ".join(info.get("keywords", [])[:3])

        is_recent = emoji in self.recent_emojis
        subtitle = f"{keywords}" + (" • Recent" if is_recent else "")

        # Use larger font size for emojis to make them visible
        icon_markup = f"<span size='xx-large'>{GLib.markup_escape_text(emoji)}</span>"

        return Result(
            title=name,
            subtitle=subtitle,
            icon_markup=icon_markup,
            action=lambda e=emoji: self._copy_to_clipboard(e),
            relevance=relevance,
            plugin_name=self.display_name,
            data={"emoji": emoji, "name": name, "recent": is_recent},
        )
