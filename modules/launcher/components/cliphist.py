import os
import subprocess
from typing import List

from fabric import Fabricator
from fabric.utils import remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GLib
from snippets import MaterialIcon


class Cliphist(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="cliphist-launcher",
            all_visible=False,
            visible=False,
            **kwargs,
        )

        self._arranger_handler = 0
        self.cliphist_manager = CliphistManager(self)
        self.viewport = None
        self.launcher = kwargs["launcher"]

        self.search_entry = Entry(
            name="search-entry",
            h_expand=True,
            notify_text=lambda entry, *_: self.handle_search_input(entry.get_text()),
            on_activate=lambda entry, *_: self.handle_search_input(entry.get_text()),
        )

        self.toggle_button = Button(
            child=MaterialIcon("delete_forever"),
            name="clear-launcher-button",
            on_clicked=self.on_button_clicked,
        )

        self.header_box = Box(
            name="header-box",
            spacing=10,
            orientation="h",
            children=[self.search_entry, self.toggle_button],
        )

        self.launcher_box = Box(
            name="cliphist-launcher-box",
            spacing=10,
            orientation="v",
            h_expand=True,
            children=[self.header_box],
        )

        self.add(self.launcher_box)

    def on_button_clicked(self, *_):
        GLib.spawn_command_line_async("cliphist wipe")
        self.cliphist_manager.update_cliphist_history()

    def open_launcher(self):
        if not self.viewport:
            self.viewport = Box(name="viewport", spacing=4, orientation="v")
            self.scrolled_window = ScrolledWindow(
                name="cliphist-history",
                spacing=10,
                h_scrollbar_policy="never",
                child=self.viewport,
            )
            self.launcher_box.add(self.scrolled_window)

        self.viewport.children = []
        self.cliphist_manager.arrange_viewport()

        self.viewport.show()
        self.search_entry.grab_focus()

    def close_launcher(self):
        self.launcher.close()

    def handle_search_input(self, text: str):
        self.cliphist_manager.arrange_viewport(text)


class CliphistManager:
    def __init__(self, launcher):
        self.launcher = launcher
        self.cliphist_history = []
        self.wl_paste_watcher = Fabricator(
            poll_from="wl-paste --watch echo", stream=True, interval=-1
        )
        self.wl_paste_watcher.connect(
            "changed", lambda *_: self.update_cliphist_history()
        )

    def get_clip_history(self) -> List[dict]:
        try:
            result = subprocess.run(
                ["cliphist", "list"], capture_output=True, text=True, check=True
            )
            return self._parse_clip_history(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error fetching cliphist history: {e}")
            return []

    def _parse_clip_history(self, output: str) -> List[dict]:
        items = []
        for line in output.splitlines():
            if line.strip():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    items.append({"id": parts[0], "content": parts[1]})
        return items

    def copy_clip(self, clip_id: str):
        try:
            decode_result = subprocess.run(
                ["cliphist", "decode", clip_id], capture_output=True, check=True
            )
            subprocess.run(["wl-copy"], input=decode_result.stdout, check=True)
            self.launcher.close_launcher()
        except subprocess.CalledProcessError as e:
            print(f"Error copying clip {clip_id}: {e}")

    def save_image_file(self, clip_id: str) -> str:
        output_file = f"/tmp/cliphist-{clip_id}.png"
        os.makedirs("/tmp", exist_ok=True)

        try:
            decode_result = subprocess.run(
                ["cliphist", "decode", clip_id], capture_output=True, check=True
            )

            with open(output_file, "wb") as f:
                f.write(decode_result.stdout)

            return output_file
        except (subprocess.CalledProcessError, IOError) as e:
            print(f"Error saving image file for clip {clip_id}: {e}")
            return ""

    def query_clips(self, query: str = "") -> List[dict]:
        history = self.get_clip_history()

        if not query.strip():
            return history

        return [item for item in history if query.lower() in item["content"].lower()]

    def bake_clip_slot(self, item: dict) -> Button:
        if "[[ binary data" in item["content"].lower():
            return self._create_image_button(item)
        return self._create_text_button(item)

    def _create_image_button(self, item: dict) -> Button:
        output_file = self.save_image_file(item["id"])
        if output_file and os.path.exists(output_file):
            button = Button(
                h_align="start",
                name="clip-img-item",
                on_clicked=lambda _, clip_id=item["id"]: self.copy_clip(clip_id),
            )

            button.set_style(
                f"background-image: url('{output_file}'); background-size: cover; background-position: center;"
            )
            return button

        return None

    def _create_text_button(self, item: dict) -> Button:
        return Button(
            child=Label(
                label=item["content"][:55]
                + ("..." if len(item["content"]) > 55 else ""),
                h_expand=True,
                v_align="center",
                h_align="start",
            ),
            on_clicked=lambda _, clip_id=item["id"]: self.copy_clip(clip_id),
            name="clip-item",
        )

    def update_cliphist_history(self):
        self.cliphist_history = self.get_clip_history()
        if self.launcher.viewport:
            GLib.idle_add(self.arrange_viewport)

    def arrange_viewport(self, query: str = ""):
        if not self.launcher.viewport:
            return

        if self.launcher._arranger_handler:
            remove_handler(self.launcher._arranger_handler)

        self.launcher.viewport.children = []
        filtered_clips = self.query_clips(query)

        for clip in filtered_clips:
            button = self.bake_clip_slot(clip)
            if button:
                self.launcher.viewport.add(button)
