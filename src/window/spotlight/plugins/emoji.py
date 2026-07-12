import contextlib
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from fabric.utils import GLib, logger

import shared.data as data
from utils.functions import copy_text, read_json_file, trigger_paste_shortcut
from window.spotlight.api import PluginContext, SearchResult, SpotlightPlugin


class EmojiPlugin(SpotlightPlugin):
    id = "emoji"
    name = "Emoji"
    icon = "face-smile-symbolic"
    keywords = ["emoji", "em"]
    searchable = True
    priority = 70

    def __init__(self, context: PluginContext):
        super().__init__(context)
        self._emoji_data: dict[str, dict[str, Any]] = {}

    def initialize(self) -> None:
        self._ensure_data()

    def cleanup(self) -> None:
        self._emoji_data.clear()

    def release_memory(self) -> None:
        self._emoji_data.clear()

    def _ensure_data(self):
        if self._emoji_data:
            return
        cldr = self._load_cldr_annotations()
        self._emoji_data = cldr or {}
        logger.info(f"[Emoji] Loaded {len(self._emoji_data)} emojis")

    def detect(self, text: str) -> bool:
        s = text.strip()
        if not s:
            return False
        for ch in s:
            cp = ord(ch)
            if (
                0x1F600 <= cp <= 0x1F64F
                or 0x1F300 <= cp <= 0x1F5FF
                or 0x1F680 <= cp <= 0x1F6FF
                or 0x1F1E0 <= cp <= 0x1F1FF
                or 0x2600 <= cp <= 0x27BF
                or 0xFE00 <= cp <= 0xFE0F
                or 0x1F900 <= cp <= 0x1F9FF
                or cp == 0x200D
                or cp == 0x20E3
                or 0xE0020 <= cp <= 0xE007F
            ):
                return True
        return False

    def search(self, query: str, token: Any) -> list[SearchResult]:
        q = query.strip()
        if not q:
            return []

        for prefix in ("emoji ", "em "):
            if q.lower().startswith(prefix):
                q = q[len(prefix) :].strip()
                break
        if q.lower() in ("emoji", "em"):
            q = ""

        if not q:
            return []

        self._ensure_data()
        if not self._emoji_data:
            logger.warning("[Emoji] No emoji data available")
            return []
        return self._query_emojis(q)

    def _query_emojis(self, text: str) -> list[SearchResult]:
        query = text.lower().strip()
        scored: list[tuple[str, dict, float]] = []

        for emoji_char, info in self._emoji_data.items():
            relevance = 0.0
            name = info.get("name", "").lower()
            keywords = info.get("keywords", [])

            if query == emoji_char:
                relevance = 1.0
            elif query == name:
                relevance = 0.95
            elif name.startswith(query):
                relevance = 0.9
            elif query in name:
                relevance = 0.8
            elif any(query == k.lower() for k in keywords):
                relevance = 0.7
            elif any(query in k.lower() for k in keywords):
                relevance = 0.6

            if relevance > 0:
                scored.append((emoji_char, info, relevance))

        if not scored:
            return []

        scored.sort(key=lambda x: x[2], reverse=True)

        results: list[SearchResult] = []
        for emoji_char, info, relevance in scored[:20]:
            name = info.get("name", "Unknown").replace("_", " ").title()
            keyword_list = info.get("keywords", [])

            results.append(
                SearchResult(
                    id=emoji_char,
                    title=emoji_char,
                    subtitle=name,
                    icon_name="",
                    score=relevance * 100,
                    render_type="emoji",
                    action=lambda e=emoji_char: self._copy_to_clipboard(e),
                    plugin_name=self.name,
                    plugin_id=self.id,
                    metadata={
                        "emoji": emoji_char,
                        "name": name,
                        "keywords": keyword_list,
                    },
                )
            )

        return results

    def _copy_to_clipboard(self, emoji_char: str) -> None:
        copy_text(emoji_char)
        GLib.timeout_add(5, lambda: (trigger_paste_shortcut(), False)[1])

    def handle_external(self, command: str, args: str) -> None:
        pass

    def _load_cldr_annotations(self) -> dict[str, dict[str, Any]] | None:
        try:
            lang = "en"
            annotations_path = self._get_annotations_path(lang)

            if not annotations_path.exists():
                url = (
                    "https://raw.githubusercontent.com/unicode-org/cldr-json/main/"
                    f"cldr-json/cldr-annotations-full/annotations/{lang}/annotations.json"
                )
                logger.info(f"[Emoji] Downloading CLDR annotations from {url}")
                if not self._download_annotations(url, annotations_path):
                    logger.error("[Emoji] Failed to download CLDR annotations")
                    return None

            raw = self._read_annotations_file(annotations_path)
            if raw is None:
                logger.error("[Emoji] Failed to read annotations file")
                return None

            result = self._normalize_annotations(raw) or None
            if result:
                logger.info(f"[Emoji] Normalized {len(result)} emojis")
            else:
                logger.error("[Emoji] Normalization returned empty")
            return result
        except Exception as e:
            logger.error(f"[Emoji] Error loading CLDR annotations: {e}")
            return None

    def _get_annotations_path(self, lang: str) -> Path:
        cache_dir = Path(data.CACHE_DIR) / "emoji"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"annotations_full_{lang}.json"

    def _download_annotations(self, url: str, dest: Path) -> bool:
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=10) as response:
                if response.status == 200:
                    dest.write_bytes(response.read())
                    return True
            return False
        except Exception as e:
            logger.error(f"[Emoji] Download error: {e}")
            return False

    def _read_annotations_file(self, path: Path) -> dict[str, Any] | None:
        raw = read_json_file(str(path))
        if raw:
            return raw
        with contextlib.suppress(OSError):
            path.unlink()
        return None

    def _normalize_annotations(self, raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
        annotations = (
            raw.get("annotations", {}).get("annotations", {})
            if isinstance(raw, dict)
            else {}
        )

        if not annotations:
            return {}

        normalized: dict[str, dict[str, Any]] = {}
        for emoji_char, info in annotations.items():
            if not isinstance(info, dict):
                continue
            tts_list = info.get("tts", []) or []
            default_list = info.get("default", []) or []

            title = tts_list[0] if tts_list else ""
            normalized[emoji_char] = {
                "name": title,
                "keywords": default_list,
            }

        return {k: v for k, v in normalized.items() if v.get("name")}
