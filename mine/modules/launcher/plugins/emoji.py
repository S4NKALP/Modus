import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from fabric.utils import GLib, idle_add, os, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from thefuzz import fuzz, process

import config.data as data
from modules.launcher.base import LauncherPlugin
from utils.functions import (
    copy_text,
    read_json_file,
    trigger_paste_shortcut,
    write_json_file,
)


class EmojiData:
    def __init__(self, emoji_char: str, emoji_info: dict[str, Any]):
        self.emoji_char = emoji_char
        self.emoji_info = emoji_info
        self.search_text = self._build_search_text()

    def _build_search_text(self) -> str:
        return (
            self.emoji_info.get("en", "")
            + " "
            + " ".join(self.emoji_info.get("alias", []))
            + " "
            + " ".join(self.emoji_info.get("tags", []))
            + " "
            + self.emoji_info.get("category", "")
        ).casefold()

    def __str__(self):
        return self.search_text


class EmojiPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "emojis"

    @property
    def icon(self) -> str:
        return "face-smile-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["emoji", "em"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self._max_recent = 30

        cldr = self._load_cldr_annotations()
        self._all_emojis = cldr or {}
        self._emoji_data = [EmojiData(ec, ei) for ec, ei in self._all_emojis.items()]

    def on_search(self, text: str) -> None:
        self.query_emojis(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0

    def _load_cldr_annotations(self) -> dict[str, dict[str, Any]] | None:
        try:
            lang = "en"
            annotations_path = self._get_annotations_path(lang)

            if not annotations_path.exists():
                url = (
                    "https://raw.githubusercontent.com/unicode-org/cldr-json/main/"
                    f"cldr-json/cldr-annotations-full/annotations/{lang}/annotations.json"
                )
                if not self._download_annotations(url, annotations_path):
                    return None

            raw = self._read_annotations_file(annotations_path)
            if raw is None:
                return None

            return self._normalize_annotations(raw) or None
        except Exception:
            return None

    def _get_annotations_path(self, lang: str) -> Path:
        cache_dir = Path(data.plugins) / "emoji"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"annotations_full_{lang}.json"

    def _download_annotations(self, url: str, dest: Path) -> bool:
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=5) as response:
                if response.status == 200:
                    dest.write_bytes(response.read())
                    return True
            return False
        except Exception:
            return False

    def _read_annotations_file(self, path: Path) -> dict[str, Any] | None:
        raw = read_json_file(str(path))
        if raw:
            return raw
        with contextlib.suppress(OSError):
            os.remove(path)
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
                "en": title,
                "alias": [],
                "tags": default_list,
                "category": "",
            }

        return {k: v for k, v in normalized.items() if isinstance(v.get("en"), str)}

    def query_emojis(self, text: str) -> None:
        if not text.strip():
            return self._show_recent_emojis()

        self.handler.start("emojis")
        query = text.casefold()

        filtered_list = [
            emoji_data
            for emoji_data, _ in process.extract(
                query,
                self._emoji_data,
                scorer=fuzz.WRatio,
                processor=lambda e: e.search_text if hasattr(e, "search_text") else e,
                limit=50,
            )
        ]

        if not filtered_list:
            return self._show_no_results()
        filtered_emojis: Iterator[EmojiData] = iter(filtered_list)

        self._query_handler = idle_add(
            self._bake_next_emoji_slot, filtered_emojis, pin=True
        )

    def _show_recent_emojis(self) -> None:
        self.handler.start("emojis")
        recent_list = self._get_recent_emojis(limit=self._max_recent)
        if not recent_list:
            return self._show_no_results("No recent emoji found")

        recent_data: list[EmojiData] = []
        for emoji_char in recent_list:
            info = self._all_emojis.get(
                emoji_char, {"en": "", "alias": [], "tags": [], "category": ""}
            )
            recent_data.append(EmojiData(emoji_char, info))

        iterator: Iterator[EmojiData] = iter(recent_data)
        self._query_handler = idle_add(self._bake_next_emoji_slot, iterator, pin=True)

    def _show_no_results(self, message: str = "No emojis found"):
        self.handler.slot_ready(
            Button(
                style_classes="app-slot emoji-no-results",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=message,
                            style_classes="emoji-no-results-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "emojis",
        )
        self.handler.done()

    def _bake_next_emoji_slot(self, iterator: Iterator[EmojiData]) -> bool:
        emoji_data = next(iterator, None)
        if emoji_data is None:
            idle_add(self.handler.done)
            return False

        emoji_button = self._create_emoji_button(
            emoji_data.emoji_char, emoji_data.emoji_info
        )
        self.handler.slot_ready(emoji_button, "emojis")
        return True

    def _create_emoji_button(
        self, emoji_char: str, emoji_info: dict[str, Any]
    ) -> Button:
        emoji_name = self._format_emoji_name(emoji_info.get("en", "Unknown"))

        return Button(
            style_classes="app-slot emoji-slot",
            child=Box(
                orientation="h",
                spacing=12,
                children=[
                    Label(
                        label=emoji_char,
                        style_classes="emoji-char",
                        h_align="start",
                        v_align="center",
                    ),
                    Box(
                        orientation="v",
                        children=[
                            Label(
                                label=emoji_name,
                                style_classes="emoji-name",
                                h_align="start",
                                v_align="start",
                            )
                        ],
                    ),
                ],
            ),
            tooltip_text=f"Click to copy {emoji_char}",
            on_clicked=lambda *_: self._copy_to_clipboard(emoji_char),
        )

    def _format_emoji_name(self, name: str) -> str:
        return name.replace(":", "").replace("_", " ").title()

    def _copy_to_clipboard(self, emoji_char: str) -> None:
        copy_text(emoji_char)
        self._add_recent_emoji(emoji_char)
        self.handler.launched()
        GLib.timeout_add(5, lambda: (trigger_paste_shortcut(0), False)[1])

    def _get_recent_emojis(self, limit: int = 30) -> list[str]:
        try:
            store = read_json_file(data.RECENT_EMOJIS_FILE) or {}
            recent = store.get("recent", []) if isinstance(store, dict) else []
            filtered = [e for e in recent if isinstance(e, str)]
            return filtered[: max(limit, 0)]
        except Exception:
            return []

    def _add_recent_emoji(self, emoji_char: str) -> None:
        if not isinstance(emoji_char, str) or not emoji_char:
            return
        try:
            store = read_json_file(data.RECENT_EMOJIS_FILE) or {}
            recent = store.get("recent", []) if isinstance(store, dict) else []
            recent = [e for e in recent if isinstance(e, str) and e != emoji_char]
            recent.insert(0, emoji_char)
            if self._max_recent > 0:
                recent = recent[: self._max_recent]
            write_json_file({"recent": recent}, data.RECENT_EMOJIS_FILE)
        except Exception:
            pass

    def handle_external(self, command: str, args: str) -> None:
        # Map external commands if needed
        pass
