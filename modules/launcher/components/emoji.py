import subprocess
from typing import Generator, List

import ijson
from fabric.utils import remove_handler, get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow


class Emoji(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="emoji-launcher",
            all_visible=False,
            visible=False,
            **kwargs,
        )

        self.launcher = kwargs["launcher"]
        self._arranger_handler: int = 0
        self.emoji_manager = EmojiManager(self)
        self.viewport = None

        self.search_entry = Entry(
            name="search-entry",
            h_expand=True,
            notify_text=lambda entry, *_: self.handle_search_input(entry.get_text()),
            on_activate=lambda entry, *_: self.handle_search_input(entry.get_text()),
        )

        self.header_box = Box(
            name="header-box",
            spacing=10,
            orientation="h",
            children=[
                self.search_entry,
            ],
        )

        self.launcher_box = Box(
            spacing=10,
            orientation="v",
            h_expand=True,
            children=[self.header_box],
        )

        self.add(self.launcher_box)

    def open_launcher(self):
        if not self.viewport:
            self.viewport = Box(name="viewport", spacing=4, orientation="v")
            self.scrolled_window = ScrolledWindow(
                name="scrolled-window",
                spacing=10,
                h_scrollbar_policy="never",
                v_scrollbar_policy="never",
                child=self.viewport,
            )
            self.launcher_box.add(self.scrolled_window)

        self.viewport.children = []
        self.emoji_manager.arrange_viewport()

        self.viewport.show()
        self.search_entry.grab_focus()

    def close_launcher(self):
        self.launcher.close()

    def handle_search_input(self, text: str):
        self.emoji_manager.arrange_viewport(text)


class EmojiManager:
    def __init__(self, launcher):
        self.launcher = launcher
        self.emoji_file_path = get_relative_path("../../../config/assets/emoji.json")

    def load_emojis(self) -> Generator[tuple, None, None]:
        try:
            with open(self.emoji_file_path, "r") as file:
                for emoji_str, item in ijson.kvitems(file, ""):
                    yield emoji_str, item["name"], item["slug"], item["group"]
        except (ijson.JSONError, KeyError, OSError) as e:
            print(f"Error loading emojis: {e}")
            return

    def query_emojis(self, query: str) -> List[tuple]:
        query = query.lower()
        return [
            (emoji_str, name, slug, group)
            for emoji_str, name, slug, group in self.load_emojis()
            if query in name.lower() or query in slug.lower() or query in group.lower()
        ][:48]

    def copy_emoji(self, emoji: tuple):
        subprocess.run(["wl-copy"], input=emoji[0].encode(), check=True)
        self.launcher.close_launcher()

    def bake_emoji_slot(self, emoji: tuple, **kwargs) -> Button:
        return Button(
            name="emoji-item",
            child=Label(label=emoji[0], h_align="center"),
            tooltip_text=emoji[1],
            on_clicked=lambda *_: self.copy_emoji(emoji),
            **kwargs,
        )

    def arrange_viewport(self, query: str = ""):
        if not self.launcher.viewport:
            return

        (
            remove_handler(self.launcher._arranger_handler)
            if self.launcher._arranger_handler
            else None
        )
        self.launcher.viewport.children = []

        filtered_emojis = self.query_emojis(query)

        row = Box(name="emoji-row", spacing=10, orientation="h")
        for emoji in filtered_emojis:
            row.add(self.bake_emoji_slot(emoji))
            if len(row.children) >= 12:
                self.launcher.viewport.add(row)
                row = Box(name="emoji-row", spacing=10, orientation="h")

        if row.children:
            self.launcher.viewport.add(row)
