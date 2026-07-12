from collections.abc import Iterator

from fabric.utils import Gio, GLib, idle_add, os, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from config.data import CLIPBOARD_DB_PATH, CLIPBOARD_THUMBS_DIR
from modules.launcher.base import LauncherPlugin
from utils.functions import copy_image, copy_text, run_command, trigger_paste_shortcut


class ClipboardPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "clipboard"

    @property
    def icon(self) -> str:
        return "edit-paste-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["clip"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self.history: list[dict] = []
        self.cache_dir = CLIPBOARD_THUMBS_DIR
        self.monitor: Gio.FileMonitor | None = None
        self.max_slots_to_render: int = 30
        self._rendered_slots_count: int = 0

        os.makedirs(self.cache_dir, exist_ok=True)
        self._setup_file_monitor()

    def on_search(self, text: str) -> None:
        self.query_clipboard(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0

        if self.monitor:
            self.monitor.cancel()
            self.monitor = None

    def _setup_file_monitor(self) -> None:
        if not os.path.exists(CLIPBOARD_DB_PATH):
            return

        file = Gio.File.new_for_path(CLIPBOARD_DB_PATH)
        self.monitor = file.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self._on_db_changed)

    def _on_db_changed(self, _monitor, _file, _other_file, event_type):
        if event_type in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CREATED,
        ):
            idle_add(self.refresh_history)

    def refresh_history(self) -> None:
        self._load_history()

    def _load_history(self) -> None:
        self.history.clear()

        result = run_command(["cliphist", "list"], timeout=5)
        output = result.stdout if isinstance(result.stdout, str) else ""

        lines = output.splitlines()[:100]

        for line in lines:
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

            self.history.append(entry)

    def _cliphist_decode(self, raw: str) -> bytes | None:
        result = run_command(["cliphist", "decode"], input=raw.encode(), text=False)
        return result.stdout if isinstance(result.stdout, (bytes, bytearray)) else None

    def _cache_image(self, raw_data: str, identifier: str) -> str | None:
        img_path = os.path.join(self.cache_dir, f"{identifier}.png")
        if os.path.exists(img_path):
            return str(img_path)

        decoded = self._cliphist_decode(raw_data)
        if not decoded:
            return None
        with open(img_path, "wb") as f:
            f.write(decoded)
        return str(img_path)

    def query_clipboard(self, text: str) -> None:
        self.handler.start("clipboard")
        self.refresh_history()
        self._rendered_slots_count = 0

        if not self.history:
            self._show_no_results()
            return

        filtered_entries = self._filter_entries(text)
        self._query_handler = idle_add(
            self._bake_next_clipboard_slot, filtered_entries, pin=True
        )

    def _show_no_results(self):
        self.handler.slot_ready(
            Button(
                style_classes="app-slot clipboard-no-results",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No clipboard history found",
                            style_classes="clipboard-no-results-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "clipboard",
        )
        self.handler.done()

    def _filter_entries(self, text: str) -> Iterator[dict]:
        if not text.strip():
            return iter(self.history)

        return iter(
            entry
            for entry in self.history
            if text.lower() in entry.get("content", "").lower()
        )

    def _bake_next_clipboard_slot(self, iterator: Iterator[dict]) -> bool:
        if self._rendered_slots_count >= self.max_slots_to_render:
            idle_add(self.handler.done)
            return False

        entry = next(iterator, None)
        if entry is None:
            idle_add(self.handler.done)
            return False

        self._create_clipboard_slot(entry)
        self._rendered_slots_count += 1
        return True

    def _create_clipboard_slot(self, entry: dict) -> None:
        if not self._is_image_entry(entry):
            self._create_text_slot(entry)
            return
        self._create_image_slot(entry)

    def _is_image_entry(self, entry: dict) -> bool:
        return entry["type"] == "image"

    def _create_image_slot(self, entry: dict) -> None:
        image_path = entry.get("path")
        if not image_path or not os.path.exists(image_path):
            image_path = self._cache_image(entry["raw"], entry["identifier"]) or ""
            if image_path:
                entry["path"] = image_path

        if not image_path:
            self.handler.slot_ready(
                Button(
                    style_classes="app-slot clipboard-text",
                    child=Box(
                        orientation="h",
                        children=[
                            Label(
                                label="Image",
                                style_classes="clipboard-content",
                                h_align="center",
                                v_align="center",
                                max_chars_width=40,
                                ellipsization="end",
                            )
                        ],
                    ),
                    on_clicked=lambda *_: self._copy_clipboard_entry(entry),
                ),
                "clipboard",
            )
            return

        self.handler.slot_ready(
            Button(
                style_classes="app-slot wallpaper clipboard-image",
                child=Box(h_expand=True, v_expand=True)
                .build()
                .set_style(
                    f"background-image: url('file://{image_path}');",
                    compile=False,
                )
                .unwrap(),
                on_clicked=lambda *_: self._copy_clipboard_entry(entry),
            ),
            "clipboard",
        )

    def _create_text_slot(self, entry: dict) -> None:
        content = entry["content"]
        display_content = content[:50] + "..." if len(content) > 50 else content

        self.handler.slot_ready(
            Button(
                style_classes="app-slot clipboard-text",
                child=Box(
                    orientation="h",
                    children=[
                        Label(
                            label=display_content,
                            style_classes="clipboard-content",
                            h_align="center",
                            v_align="center",
                            max_chars_width=40,
                            ellipsization="end",
                        )
                    ],
                ),
                tooltip_text=entry["content"],
                on_clicked=lambda *_: self._copy_clipboard_entry(entry),
            ),
            "clipboard",
        )

    def _copy_clipboard_entry(self, entry: dict) -> None:
        if entry["type"] == "image" and entry.get("path"):
            copy_image(entry["path"])
        else:
            decoded = self._cliphist_decode(entry["raw"])
            if not decoded:
                return
            copy_text(decoded.decode())
        self.handler.launched()
        GLib.timeout_add(5, lambda: (trigger_paste_shortcut(0), False)[1])

    def handle_external(self, command: str, args: str) -> None:
        # Map external commands if needed
        pass
