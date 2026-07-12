from collections.abc import Iterator

from fabric.utils import Gdk, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin
from services import BookmarkManager
from utils.functions import copy_text


class BookmarkPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "bookmarks"

    @property
    def icon(self) -> str:
        return "user-bookmarks-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["bm"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self.current_slots: list = []
        self.bookmarks: dict = {}
        self.bookmark_manager = BookmarkManager()

    def on_search(self, text: str) -> None:
        self.query_bookmarks(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        self.current_slots.clear()

    def query_bookmarks(self, text: str) -> None:
        self.handler.start("bookmarks")
        self.current_slots.clear()
        text_stripped = text.strip()

        commands = {
            "add": self._handle_add_command,
            "remove": self._handle_remove_command,
            "update": self._handle_update_command,
            "help": lambda t: self._show_command_help(),
        }

        for prefix, handler in commands.items():
            if text_stripped.startswith(prefix):
                handler(text)
                return

        self._load_and_display_bookmarks(text)

    def _load_and_display_bookmarks(self, text: str) -> None:
        result = self.bookmark_manager.list_bookmarks()
        if not result["success"]:
            self._show_error_message(f"Failed to load bookmarks: {result['error']}")
            return

        self.bookmarks = result["data"]

        if not self.bookmarks:
            self._show_no_bookmarks()
            return

        filtered_bookmarks = self._filter_bookmarks(text)
        if not filtered_bookmarks:
            self._show_no_results()
            return

        self._query_handler = idle_add(
            self._bake_next_bookmark_slot, iter(filtered_bookmarks), pin=True
        )

    def _filter_bookmarks(self, text: str) -> Iterator[tuple[str, dict]]:
        if not text.strip():
            return iter(self.bookmarks.items())

        text_lower = text.lower()
        return iter(
            (name, data)
            for name, data in self.bookmarks.items()
            if (
                text_lower in name.lower()
                or text_lower in data.get("content", "").lower()
            )
        )

    def _show_no_bookmarks(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot bookmark-no-bookmarks",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No bookmarks found",
                            style_classes="bookmark-no-bookmarks-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="Use 'add name content' to add bookmarks",
            ),
            "bookmarks",
        )
        self.handler.done()

    def _show_no_results(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot bookmark-no-results",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No bookmarks match your search",
                            style_classes="bookmark-no-results-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "bookmarks",
        )
        self.handler.done()

    def _bake_next_bookmark_slot(self, iterator: Iterator[tuple[str, dict]]) -> bool:
        try:
            bookmark_name, bookmark_data = next(iterator)
        except StopIteration:
            idle_add(self.handler.done)
            return False

        self._create_bookmark_slot(bookmark_name, bookmark_data)
        return True

    def _create_bookmark_slot(self, bookmark_name: str, bookmark_data: dict) -> None:
        content = bookmark_data.get("content", "")

        name_label = Label(
            label=bookmark_name,
            style_classes="bookmark-name",
            h_align="start",
            max_chars_width=25,
            ellipsization="end",
        )

        content_label = Label(
            label=content if content else "No content",
            style_classes="bookmark-content",
            h_align="start",
            max_chars_width=40,
            ellipsization="end",
        )

        slot_widget = Button(
            style_classes="app-slot bookmark-slot",
            child=Box(
                orientation="v",
                spacing=4,
                children=[
                    name_label,
                    content_label,
                ],
            ),
            tooltip_text=f"Click to copy content\nContent: {content}",
            on_clicked=lambda *_: self._copy_bookmark(bookmark_name),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, bm_name=bookmark_name: self._on_slot_key_press(
                widget, event, bm_name
            ),
        )

        slot_info = {
            "widget": slot_widget,
            "name_label": name_label,
            "content_label": content_label,
            "bookmark_name": bookmark_name,
            "bookmark_data": bookmark_data,
        }
        self.current_slots.append(slot_info)
        self.handler.slot_ready(slot_widget, "bookmarks")

    def _copy_bookmark(self, bookmark_name: str) -> None:
        """Copy bookmark content to clipboard"""
        result = self.bookmark_manager.get_bookmark(bookmark_name)
        if not result["success"]:
            self._show_error_message(f"Failed to get bookmark: {result['error']}")
            return

        content = result["data"]["content"]
        self.handler.launched()

        if not copy_text(content):
            self._show_error_message("Failed to copy content to clipboard")

    def _on_slot_key_press(self, widget, event, bookmark_name: str) -> bool:
        if not event:
            return False
        return (
            (event.keyval == Gdk.KEY_Return or event.keyval == Gdk.KEY_KP_Enter)
            and event.state & Gdk.ModifierType.SHIFT_MASK
            and (self._handle_remove_command(f"remove {bookmark_name}") or True)
        )

    def _handle_add_command(self, text: str) -> None:
        if text.strip() == "add":
            self._load_and_display_bookmarks("")
            return

        if not text.strip().endswith(";"):
            self._show_error_message(
                "Bookmark command must end with ';'\n\nUsage: add name content;"
            )
            return

        command_text = text.strip()[:-1]
        parts = command_text.split()
        if len(parts) < 3:
            self._show_command_help("add")
            return

        name = parts[1]
        content = parts[2]
        result = self.bookmark_manager.add_bookmark(name, content)
        if result["success"]:
            if hasattr(self.handler, "clear_input"):
                self.handler.clear_input()
            self._refresh_bookmark_list()
        else:
            self._show_error_message(f"Error adding bookmark: {result['error']}")

    def _handle_remove_command(self, text: str) -> None:
        if text.strip() == "remove":
            self._load_and_display_bookmarks("")
            return

        if not text.strip().endswith(";"):
            self._show_error_message(
                "Bookmark command must end with ';'\n\nUsage: remove name;"
            )
            return

        command_text = text.strip()[:-1]
        parts = command_text.split()
        if len(parts) < 2:
            self._show_command_help("remove")
            return

        bookmark_name = parts[1]
        result = self.bookmark_manager.delete_bookmark(bookmark_name)
        if result["success"]:
            if hasattr(self.handler, "clear_input"):
                self.handler.clear_input()
            self._refresh_bookmark_list()
        else:
            self._show_error_message(f"Error removing bookmark: {result['error']}")

    def _handle_update_command(self, text: str) -> None:
        if text.strip() == "update":
            self._load_and_display_bookmarks("")
            return

        if not text.strip().endswith(";"):
            self._show_error_message(
                "Bookmark command must end with ';'\n\nUsage: update name content new_value;"
            )
            return

        command_text = text.strip()[:-1]
        parts = command_text.split()
        if len(parts) < 4:
            self._show_command_help("update")
            return

        bookmark_name = parts[1]
        field = parts[2]
        if field != "content":
            self._show_error_message("Invalid field. Only 'content' is supported")
            return

        new_value = " ".join(parts[3:])

        result = self.bookmark_manager.update_bookmark(bookmark_name, content=new_value)
        if result["success"]:
            if hasattr(self.handler, "clear_input"):
                self.handler.clear_input()
            self._refresh_bookmark_list()
        else:
            self._show_error_message(f"Error updating bookmark: {result['error']}")

    def _show_command_help(self, command: str = None) -> None:
        help_texts = {
            "add": "Usage: add name content;\nExample: add github https://github.com;\nContent can be URLs, file paths, commands, or any text!",
            "remove": "Usage: remove name;\nExample: remove github;",
            "update": "Usage: update name content new_value;\nExample: update github content https://github.com/new;",
        }

        help_text = help_texts.get(
            command,
            """Available commands:
• add name content; (Add new bookmark)
• remove name; (Remove bookmark)
• update name content new_value; (Update bookmark)
• help (Show this help)

Commands with arguments must end with semicolon (;)
Content can be URLs, file paths, commands, or any text!
Click on any bookmark to copy it to clipboard!""",
        )

        self.handler.slot_ready(
            Button(
                style_classes="app-slot bookmark-help",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=help_text,
                            style_classes="bookmark-help-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "bookmarks",
        )
        self.handler.done()

    def _show_error_message(self, message: str) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot bookmark-error",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=message,
                            style_classes="bookmark-error-text",
                            h_align="center",
                        ),
                    ],
                ),
                on_clicked=lambda *_: self.handler.launched(),
            ),
            "bookmarks",
        )
        self.handler.done()

    def _refresh_bookmark_list(self) -> None:
        self.current_slots.clear()
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        idle_add(self._show_bookmark_list)

    def _show_bookmark_list(self) -> None:
        self.handler.start("bookmarks")
        self._load_and_display_bookmarks("")

    def handle_external(self, command: str, args: str) -> None:
        # Map external commands if needed
        pass
