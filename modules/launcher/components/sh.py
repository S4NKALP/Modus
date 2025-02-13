import os
import subprocess
from typing import List
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from snippets import MaterialIcon

CACHE_DIR = os.getenv(
    "XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache", "fabric")
)
BINS = os.path.join(CACHE_DIR, "binaries")


class Sh(Box):
    def __init__(self, **kwargs):
        super().__init__(
            all_visible=False,
            visible=False,
            **kwargs,
        )

        self.launcher = kwargs["launcher"]
        self._arranger_handler: int = 0
        self.shell_command_manager = ShellCommandManager(self)
        self.viewport = None

        self.search_entry = Entry(
            name="search-entry",
            h_expand=True,
            notify_text=lambda entry, *_: self.handle_search_input(entry.get_text()),
            on_activate=lambda entry, *_: self.handle_search_input(entry.get_text()),
        )

        self.header_box = Box(
            spacing=10,
            orientation="h",
            children=[self.search_entry, MaterialIcon("terminal")],
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
            self.viewport = Box(name="viewport", spacing=10, orientation="v")
            self.scrolled_window = ScrolledWindow(
                spacing=10,
                h_scrollbar_policy="never",
                v_scrollbar_policy="never",
                child=self.viewport,
            )
            self.launcher_box.add(self.scrolled_window)

        self.viewport.children = []
        self.shell_command_manager.show_shell_commands(self.viewport, "")

        self.viewport.show()
        self.search_entry.grab_focus()

    def handle_search_input(self, text: str):
        self.shell_command_manager.show_shell_commands(self.viewport, text)


class ShellCommandManager:
    def __init__(self, launcher):
        self.launcher = launcher
        self.binaries = set()
        self.reload_binaries()

    def reload_binaries(self):
        paths = os.getenv("PATH", "").split(":")
        self.binaries = set()

        for path in paths:
            self.binaries.update(self.list_binaries_in_path(path))

        with open(BINS, "w") as f:
            f.write("\n".join(self.binaries))

    def list_binaries_in_path(self, path):
        if not os.path.exists(path):
            return []
        try:
            return [
                entry
                for entry in os.listdir(path)
                if os.access(os.path.join(path, entry), os.X_OK)
            ]
        except OSError:
            return []

    def show_shell_commands(self, viewport, search_query: str):
        if not search_query:
            return

        viewport.children = []

        results = self.query_binaries(search_query)
        self.display_results(viewport, results)

    def query_binaries(self, filter_str: str) -> List[str]:
        filter_str = filter_str.lower()
        filtered_bins = (cmd for cmd in self.binaries if filter_str in cmd)
        return list(dict.fromkeys(filtered_bins))[:16]

    def display_results(self, viewport, results: List[str]):
        for command in results:
            button = Button(
                child=Label(
                    label=command,
                    v_align="center",
                    h_align="start",
                ),
                on_clicked=lambda _, cmd=command: self.execute_command(cmd),
                name="sh-item",
            )
            viewport.add(button)

    def close_menu(self):
        self.launcher.close()

    def execute_command(self, cmd: str):
        try:
            output = subprocess.check_output(cmd, shell=True, text=True)
            print(output)
        except subprocess.CalledProcessError as e:
            print(e.output)
        finally:
            self.close_menu()
