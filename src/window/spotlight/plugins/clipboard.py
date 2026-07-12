import os
import threading
from typing import Any

from fabric.utils import Gio, GLib

from shared.data import CLIPBOARD_DB_PATH, CLIPBOARD_THUMBS_DIR
from utils.functions import copy_image, copy_text, run_command, trigger_paste_shortcut
from window.spotlight.api import PluginContext, SearchResult, SpotlightPlugin


class ClipboardPlugin(SpotlightPlugin):
    id = "clipboard"
    name = "Clipboard"
    icon = "edit-paste-symbolic"
    searchable = True
    priority = 80

    MAX_RESULTS: int = 30

    def __init__(self, context: PluginContext):
        super().__init__(context)
        self._history: list[dict] = []
        self._history_lock: threading.Lock = threading.Lock()
        self._cache_dir: str = CLIPBOARD_THUMBS_DIR
        self._monitor: Gio.FileMonitor | None = None
        self._db_debounce_id: int = 0

    def initialize(self) -> None:
        os.makedirs(self._cache_dir, exist_ok=True)
        self._load_history()
        self._setup_file_monitor()

    def cleanup(self) -> None:
        if self._monitor:
            self._monitor.cancel()
            self._monitor = None
        if self._db_debounce_id:
            GLib.source_remove(self._db_debounce_id)
            self._db_debounce_id = 0

    def release_memory(self) -> None:
        with self._history_lock:
            self._history.clear()

    def search(self, query: str, token: Any) -> list[SearchResult]:
        q = query.strip()
        if q.lower().startswith("clip "):
            q = q[5:].strip()
        elif q.lower() == "clip":
            q = ""

        self._ensure_history()
        return self._build_results(self._filter_entries(q), q)

    def _ensure_history(self) -> None:
        with self._history_lock:
            if self._history:
                return
        self._load_history()

    def _setup_file_monitor(self) -> None:
        if not os.path.exists(CLIPBOARD_DB_PATH):
            return
        f = Gio.File.new_for_path(CLIPBOARD_DB_PATH)
        self._monitor = f.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self._monitor.connect("changed", self._on_db_changed)

    def _on_db_changed(self, _monitor, _file, _other_file, event_type):
        if event_type not in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CREATED,
        ):
            return
        if self._db_debounce_id:
            GLib.source_remove(self._db_debounce_id)
        self._db_debounce_id = GLib.timeout_add(300, self._on_debounced_db_change)

    def _on_debounced_db_change(self):
        self._db_debounce_id = 0
        self._load_history()

    def _load_history(self) -> None:
        result = run_command(["cliphist", "list"], timeout=5)
        raw = result.stdout if isinstance(result.stdout, str) else ""
        lines = raw.splitlines()
        new_entries = []
        for line in lines[:100]:
            if "\t" not in line:
                continue
            identifier, content = line.split("\t", 1)
            content = content.strip()
            entry = {
                "type": "text",
                "identifier": identifier,
                "raw": line,
                "content": content,
            }
            if "binary data" in content:
                entry["type"] = "image"
            new_entries.append(entry)
        with self._history_lock:
            self._history.clear()
            self._history.extend(new_entries)

    def _filter_entries(self, query: str) -> list[dict]:
        q = query.strip().lower()
        with self._history_lock:
            if not q:
                return [
                    e
                    for e in self._history
                    if not self._is_toml_data(e.get("content", ""))
                ]
            return [
                e
                for e in self._history
                if q in e.get("content", "").lower()
                and not self._is_toml_data(e.get("content", ""))
            ]

    def _build_results(
        self, entries: list[dict], query: str = ""
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        for entry in entries[: self.MAX_RESULTS]:
            content = entry["content"]
            is_image = entry["type"] == "image"
            render_type = "clipboard_image" if is_image else "clipboard_text"
            display = content[:50] + "..." if len(content) > 50 else content

            metadata: dict[str, Any] = {
                "raw": entry["raw"],
                "identifier": entry["identifier"],
                "type": entry["type"],
                "image_path": "",
            }

            if is_image:
                image_path = entry.get("path", "")
                if not image_path or not os.path.exists(image_path):
                    image_path = (
                        self._cache_image(entry["raw"], entry["identifier"]) or ""
                    )
                    if image_path:
                        entry["path"] = image_path
                if image_path:
                    metadata["image_path"] = image_path

            results.append(
                SearchResult(
                    id=f"clip_{entry['identifier']}",
                    title="Image" if is_image and not image_path else display,
                    subtitle=content[:80],
                    icon_name="edit-paste-symbolic",
                    score=self._score_entry(entry, query),
                    render_type=render_type,
                    plugin_id=self.id,
                    action=self._make_action(entry),
                    metadata=metadata,
                )
            )
        return results

    @staticmethod
    def _score_entry(entry: dict, query: str) -> float:
        if not query.strip():
            return 80.0
        content_lower = entry["content"].lower()
        q = query.lower()
        pos = content_lower.find(q)
        if pos == -1:
            return 60.0
        if pos == 0:
            return 100.0
        return max(60.0, 95.0 - pos * 0.5)

    @staticmethod
    def _cliphist_decode(raw: str) -> bytes | None:
        result = run_command(["cliphist", "decode"], input=raw.encode(), text=False)
        return result.stdout if isinstance(result.stdout, (bytes, bytearray)) else None

    def _cache_image(self, raw_data: str, identifier: str) -> str | None:
        img_path = os.path.join(self._cache_dir, f"{identifier}.png")
        if os.path.exists(img_path):
            return img_path
        decoded = self._cliphist_decode(raw_data)
        if not decoded:
            return None
        with open(img_path, "wb") as f:
            f.write(decoded)
        return str(img_path)

    def _make_action(self, entry: dict):
        def _action():
            if entry["type"] == "image" and entry.get("path"):
                copy_image(entry["path"])
            else:
                decoded = self._cliphist_decode(entry["raw"])
                if not decoded:
                    return
                copy_text(decoded.decode())
            GLib.timeout_add(5, lambda: (trigger_paste_shortcut(), False)[1])

        return _action

    @staticmethod
    def _is_toml_data(content: str) -> bool:
        lines = content.strip().splitlines()
        if len(lines) < 2:
            return False
        bracket_lines = sum(
            1 for ln in lines if ln.strip().startswith("[") and "]" in ln
        )
        equals_lines = sum(
            1
            for ln in lines
            if "=" in ln and ln.strip() and not ln.strip().startswith("[")
        )
        return bracket_lines >= 1 and equals_lines >= 2


PLUGIN = ClipboardPlugin
