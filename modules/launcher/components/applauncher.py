from collections.abc import Iterator
from fabric.utils import DesktopApp, get_desktop_applications, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.image import Image
from gi.repository import Gdk, GLib
import json
import os
import math
import re
import subprocess
import webbrowser
from functools import partial
from utils import read_config


class AppLauncher(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="app-launcher", visible=False, all_visible=False, **kwargs
        )

        self.scrolled_window = None
        self.launcher = kwargs["launcher"]
        self.selected_index = -1
        self._arranger_handler = 0
        self._all_apps = get_desktop_applications()
        self.config = read_config()

        self.calc_history_path = os.path.expanduser("~/.cache/modus/calc.json")
        self.calc_history = self._load_calc_history()

        self.viewport = Box(name="viewport", spacing=4, orientation="v")
        self.search_entry = Entry(
            name="search-entry",
            h_expand=True,
            notify_text=self._on_notify_text,
            on_activate=self._on_activate,
            on_key_press_event=self.on_search_entry_key_press,
        )

        self.header_box = Box(
            name="header-box", orientation="h", children=[self.search_entry]
        )

        self.launcher_box = Box(
            name="launcher-box",
            h_expand=True,
            orientation="v",
            children=[self.header_box],
        )

        self.add(self.launcher_box)
        self.show_all()

    def _load_calc_history(self):
        if os.path.exists(self.calc_history_path):
            with open(self.calc_history_path, "r") as f:
                return json.load(f)
        return []

    def _on_notify_text(self, entry, *args):
        self.arrange_viewport(entry.get_text())

    def _on_activate(self, entry, *args):
        self.on_search_entry_activate(entry.get_text())

    def close_launcher(self, *_):
        self.viewport.children = []
        self.selected_index = -1
        self.launcher.close()
        self.hide_scrolled_window()

    def open_launcher(self):
        self._all_apps = get_desktop_applications()
        self.arrange_viewport("")

    def arrange_viewport(self, query: str = ""):
        if query.startswith(":"):
            self.hide_scrolled_window()
            self.launcher.dashboard.hide()
            return

        if query.startswith("="):
            self.show_scrolled_window()
            self.update_calculator_viewport()
            self.launcher.dashboard.hide()
            return

        if self._arranger_handler:
            remove_handler(self._arranger_handler)
            self._arranger_handler = 0
        self.viewport.children = []
        self.selected_index = -1

        if query.strip():
            self.launcher.dashboard.hide()
            self.show_scrolled_window()
        else:
            self.launcher.dashboard.show()
            self.hide_scrolled_window()
            return False

        filtered_apps = [
            app
            for app in self._all_apps
            if query.casefold()
            in (
                (app.display_name or "")
                + " "
                + app.name
                + " "
                + (app.generic_name or "")
            ).casefold()
        ]
        filtered_apps_iter = iter(
            sorted(filtered_apps, key=lambda app: (app.display_name or "").casefold())
        )

        self._arranger_handler = idle_add(
            partial(self._arranger_callback, query=query), filtered_apps_iter, pin=True
        )

    def _arranger_callback(self, apps_iter: Iterator[DesktopApp], query: str):
        if self.add_next_application(apps_iter):
            return True
        return self.handle_arrange_complete(query)

    def show_scrolled_window(self):
        if self.scrolled_window is None:
            self.scrolled_window = ScrolledWindow(
                name="scrolled-window",
                style_classes="applauncher-scrolled-window",
                h_scrollbar_policy="never",
                child=self.viewport,
            )
            self.launcher_box.add(self.scrolled_window)

        self.scrolled_window.show_all()
        GLib.idle_add(self.update_scrolled_window_size)

    def hide_scrolled_window(self):
        if self.scrolled_window:
            self.scrolled_window.hide()

    def handle_arrange_complete(self, query):
        self.update_scrolled_window_size()
        if query.strip() and self.viewport.get_children():
            self.update_selection(0)
        return False

    def add_next_application(self, apps_iter: Iterator[DesktopApp]):
        app = next(apps_iter, None)
        if app is None:
            return False
        self.viewport.add(self.bake_application_slot(app))
        return True

    def bake_application_slot(self, app: DesktopApp) -> Button:
        return Button(
            name="launcher-app",
            child=Box(
                orientation="h",
                children=[
                    Image(pixbuf=app.get_icon_pixbuf(size=32), h_align="start"),
                    Label(
                        label=app.display_name or "Unknown",
                        ellipsization="end",
                        v_align="center",
                    ),
                ],
            ),
            tooltip_text=app.description,
            on_clicked=partial(self._on_app_clicked, app),
        )

    def _on_app_clicked(self, app, *args):
        app.launch()
        self.close_launcher()

    def update_selection(self, new_index: int):
        children = self.viewport.get_children()
        if self.selected_index >= 0 < len(children):
            children[self.selected_index].get_style_context().remove_class("selected")

        if 0 <= new_index < len(children):
            children[new_index].get_style_context().add_class("selected")
            self.selected_index = new_index
        else:
            self.selected_index = -1

    def update_scrolled_window_size(self):
        if self.scrolled_window is None:
            return

        children = self.viewport.get_children()
        item_count = len(children)

        if item_count == 0:
            self.scrolled_window.set_size_request(-1, 0)
            return

        first_child = children[0]
        first_child_height = first_child.get_allocation().height

        if first_child_height == 0:
            GLib.idle_add(self.update_scrolled_window_size)
            return

        spacing = self.viewport.props.spacing
        total_height = (item_count * first_child_height) + ((item_count - 1) * spacing)

        max_height = 400
        self.scrolled_window.set_size_request(-1, min(total_height, max_height))

    def on_search_entry_activate(self, text):
        if text.startswith(":i "):
            webbrowser.open(f"https://www.google.com/search?q={text[3:].strip()}")
            self.close_launcher()
            return

        if text.startswith("="):
            self.evaluate_calculator_expression(text)
            return

        children = self.viewport.get_children()
        if children:
            (children[self.selected_index or 0]).clicked()

    def on_search_entry_key_press(self, widget, event):
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            self.move_selection(1 if event.keyval == Gdk.KEY_Down else -1)
            return True
        if event.keyval == Gdk.KEY_Escape:
            self.close_launcher()
            return True
        return False

    def move_selection(self, delta: int):
        children = self.viewport.get_children()
        if not children:
            return
        new_index = max(0, min(self.selected_index + delta, len(children) - 1))
        self.update_selection(new_index)

    def evaluate_calculator_expression(self, text: str):
        expr = text.lstrip("=").replace("^", "**").replace("×", "*")
        expr = re.sub(r"(\d+)!", r"math.factorial(\1)", expr)
        result = eval(expr, {"__builtins__": None, "math": math})
        self.calc_history.insert(0, f"{text} => {result}")
        self.save_calc_history()
        self.update_calculator_viewport()

    def update_calculator_viewport(self):
        self.viewport.children = [
            Button(
                child=Label(label=item),
                on_clicked=partial(self.copy_text_to_clipboard, item),
            )
            for item in self.calc_history
        ]
        self.update_scrolled_window_size()

    def save_calc_history(self):
        with open(self.calc_history_path, "w") as f:
            json.dump(self.calc_history, f)

    def copy_text_to_clipboard(self, text: str, *args):
        subprocess.run(
            ["wl-copy"], input=text.split("=>", 1)[-1].strip().encode(), check=True
        )
