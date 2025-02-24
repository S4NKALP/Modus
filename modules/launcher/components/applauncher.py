from collections.abc import Iterator
import operator
from fabric.utils import DesktopApp, get_desktop_applications, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GLib, Gdk
from snippets import read_config
from fabric.widgets.image import Image
import json
import os
import re
import math
import subprocess
import webbrowser


class AppLauncher(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="app-launcher",
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.launcher = kwargs["launcher"]
        self.selected_index = -1
        self._arranger_handler: int = 0
        self._all_apps = get_desktop_applications()
        self.config = read_config()

        # Calculator history initialization
        self.calc_history_path = os.path.expanduser("~/.cache/modus/calc.json")
        if os.path.exists(self.calc_history_path):
            with open(self.calc_history_path, "r") as f:
                self.calc_history = json.load(f)
        else:
            self.calc_history = []

        self.viewport = Box(name="viewport", spacing=4, orientation="v")
        self.search_entry = Entry(
            name="search-entry",
            h_expand=True,
            notify_text=lambda entry, *_: self.arrange_viewport(entry.get_text()),
            on_activate=lambda entry, *_: self.on_search_entry_activate(
                entry.get_text()
            ),
            on_key_press_event=self.on_search_entry_key_press,
        )

        self.scrolled_window = None

        self.header_box = Box(
            name="header-box",
            orientation="h",
            children=[self.search_entry],
        )

        self.launcher_box = Box(
            name="launcher-box",
            h_expand=True,
            orientation="v",
            children=[self.header_box],
        )

        self.add(self.launcher_box)
        self.show_all()

    def close_launcher(self, *_):
        self.viewport.children = []
        self.selected_index = -1
        self.launcher.close()

    def open_launcher(self):
        self._all_apps = get_desktop_applications()
        self.arrange_viewport("")

    def arrange_viewport(self, query: str = ""):
        if query.startswith(":"):  # Don't show ScrolledWindow for web search
            self.destroy_scrolled_window()
            self.launcher.dashboard.hide()
            return
        if query.startswith("="):
            self.show_scrolled_window()
            # In calculator mode, update history view once (not per keystroke)
            self.update_calculator_viewport()
            self.launcher.dashboard.hide()
            return

        remove_handler(self._arranger_handler) if self._arranger_handler else None
        self.viewport.children = []
        self.selected_index = -1

        if query.strip():
            self.launcher.dashboard.hide()
            self.show_scrolled_window()
        else:
            self.launcher.dashboard.show()
            self.destroy_scrolled_window()
            return False

        filtered_apps_iter = iter(
            sorted(
                [
                    app
                    for app in self._all_apps
                    if query.casefold()
                    in (
                        (app.display_name or "")
                        + (" " + app.name + " ")
                        + (app.generic_name or "")
                    ).casefold()
                ],
                key=lambda app: (app.display_name or "").casefold(),
            )
        )
        should_resize = operator.length_hint(filtered_apps_iter) == len(self._all_apps)

        self._arranger_handler = idle_add(
            lambda apps_iter: self.add_next_application(apps_iter)
            or self.handle_arrange_complete(should_resize, query),
            filtered_apps_iter,
            pin=True,
        )

    def show_scrolled_window(self):
        if self.scrolled_window is None:
            self.scrolled_window = ScrolledWindow(
                name="scrolled-window",
                spacing=10,
                min_content_size=(-1, -1),
                h_scrollbar_policy="never",
                child=self.viewport,
                v_expand=True,
            )
            self.launcher_box.add(self.scrolled_window)
            self.scrolled_window.show_all()
            self.get_style_context().add_class("applauncher")

    def destroy_scrolled_window(self):
        if hasattr(self, "scrolled_window") and self.scrolled_window:
            # self.scrolled_window.destroy()
            self.launcher_box.remove(self.scrolled_window)
            self.scrolled_window = None

        self.get_style_context().remove_class("applauncher")

    def handle_arrange_complete(self, should_resize, query):
        if should_resize:
            self.resize_viewport()
        # Only auto-select first item if query exists
        if query.strip() != "" and self.viewport.get_children():
            self.update_selection(0)
        return False

    def add_next_application(self, apps_iter: Iterator[DesktopApp]):
        if not (app := next(apps_iter, None)):
            return False

        self.viewport.add(self.bake_application_slot(app))
        return True

    def bake_application_slot(self, app: DesktopApp, **kwargs) -> Button:
        button = Button(
            name="launcher-app",
            child=Box(
                orientation="h",
                children=[
                    Image(
                        pixbuf=app.get_icon_pixbuf(size=32),
                        h_align="start",
                        name="launcher-app-icon",
                    ),
                    Label(
                        label=app.display_name or "Unknown",
                        ellipsization="end",
                        v_align="center",
                        h_align="center",
                    ),
                ],
            ),
            tooltip_text=app.description,
            on_clicked=lambda *_: (app.launch(), self.close_launcher()),
            **kwargs,
        )
        return button

    def update_selection(self, new_index: int):
        if self.selected_index != -1 and self.selected_index < len(
            self.viewport.get_children()
        ):
            current_button = self.viewport.get_children()[self.selected_index]
            current_button.get_style_context().remove_class("selected")

        if new_index != -1 and new_index < len(self.viewport.get_children()):
            new_button = self.viewport.get_children()[new_index]
            new_button.get_style_context().add_class("selected")
            self.selected_index = new_index
            self.scroll_to_selected(new_button)
        else:
            self.selected_index = -1

    def scroll_to_selected(self, button):
        def scroll():
            adj = self.scrolled_window.get_vadjustment()
            alloc = button.get_allocation()
            if alloc.height == 0:
                return False

            y = alloc.y
            height = alloc.height
            page_size = adj.get_page_size()
            current_value = adj.get_value()

            visible_top = current_value
            visible_bottom = current_value + page_size

            if y < visible_top:
                adj.set_value(y)
            elif y + height > visible_bottom:
                new_value = y + height - page_size
                adj.set_value(new_value)
            return False

        GLib.idle_add(scroll)

    def on_search_entry_activate(self, text):
        commands = self.config.get("commands", {})
        if text.startswith(":i "):  # Detecting ':i' search
            search_query = text[3:].strip()  # Extract query after ':i '
            if search_query:
                url = f"https://www.google.com/search?q={search_query}"
                webbrowser.open(url)
                self.close_launcher()
            return

        if text.startswith("="):
            # If in calculator mode and no history item is selected, evaluate new expression.
            if self.selected_index == -1:
                self.evaluate_calculator_expression(text)
            return

        if text in commands:
            command = commands[text]
            exec(command, {"launcher": self.launcher})
        else:
            children = self.viewport.get_children()
            if children:
                if text.strip() == "" and self.selected_index == -1:
                    return
                selected_index = self.selected_index if self.selected_index != -1 else 0
                if 0 <= selected_index < len(children):
                    children[selected_index].clicked()

    def on_search_entry_key_press(self, widget, event):
        keyval = event.keyval
        if keyval == Gdk.KEY_Down:
            self.move_selection(1)
            return True
        elif keyval == Gdk.KEY_Up:
            self.move_selection(-1)
            return True
        elif keyval == Gdk.KEY_Escape:
            self.close_launcher()
            return True
        return False

    def move_selection(self, delta: int):
        children = self.viewport.get_children()
        if not children:
            return
        if self.selected_index == -1 and delta == 1:
            new_index = 0
        else:
            new_index = self.selected_index + delta
        new_index = max(0, min(new_index, len(children) - 1))
        self.update_selection(new_index)

    def save_calc_history(self):
        with open(self.calc_history_path, "w") as f:
            json.dump(self.calc_history, f)

    def evaluate_calculator_expression(self, text: str):
        # Remove the '=' prefix and extra spaces
        expr = text.lstrip("=").strip()
        if not expr:
            return
        # Replace operators: '^' -> '**', and '×' -> '*'
        expr = expr.replace("^", "**").replace("×", "*")
        # Replace factorial: e.g. 5! -> math.factorial(5)
        expr = re.sub(r"(\d+)!", r"math.factorial(\1)", expr)
        # Replace brackets: allow [] and {} as ()
        for old, new in [("[", "("), ("]", ")"), ("{", "("), ("}", ")")]:
            expr = expr.replace(old, new)
        try:
            result = eval(expr, {"__builtins__": None, "math": math})
        except Exception as e:
            result = f"Error: {e}"
        # Prepend to history (newest first)
        self.calc_history.insert(0, f"{text} => {result}")
        self.save_calc_history()
        self.update_calculator_viewport()

    def update_calculator_viewport(self):
        self.viewport.children = []
        for item in self.calc_history:
            btn = self.create_calc_history_button(item)
            self.viewport.add(btn)
        # Remove resetting selected_index unconditionally so that a highlighted result isn't lost.
        # Optionally, only reset if the input is not more than "=".
        # if self.search_entry.get_text().strip() != "=":
        #     self.selected_index = -1

    def create_calc_history_button(self, text: str) -> Button:
        btn = Button(
            name="app-slot-button",  # reuse existing CSS styling
            child=Box(
                name="calc-slot-box",
                orientation="h",
                spacing=10,
                children=[
                    Label(
                        name="calc-label",
                        label=text,
                        ellipsization="end",
                        v_align="center",
                        h_align="center",
                    ),
                ],
            ),
            tooltip_text=text,
            on_clicked=lambda *_: self.copy_text_to_clipboard(text),
        )
        return btn

    def copy_text_to_clipboard(self, text: str):
        # Split the text on "=>" and copy only the result part if available
        parts = text.split("=>", 1)
        copy_text = parts[1].strip() if len(parts) > 1 else text
        try:
            subprocess.run(["wl-copy"], input=copy_text.encode(), check=True)
        except subprocess.CalledProcessError as e:
            print(f"Clipboard copy failed: {e}")

    def delete_selected_calc_history(self):
        if self.selected_index != -1 and self.selected_index < len(self.calc_history):
            del self.calc_history[self.selected_index]
            self.save_calc_history()
            self.update_calculator_viewport()
