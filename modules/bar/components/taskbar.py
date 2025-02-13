import json
import os
from typing import TypedDict

from fabric.hyprland.widgets import get_hyprland_connection
from fabric.utils import exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from gi.repository import GdkPixbuf, GLib, Gtk
from loguru import logger


class PagerClient(TypedDict):
    title: str
    initialClass: str
    mapped: bool
    hidden: bool
    address: str


class TaskBar(Box):
    def __init__(self, icon_size: int = 20, **kwargs):
        super().__init__(
            orientation="h",
            spacing=7,
            name="taskbar",
            **kwargs,
        )
        self.connection = get_hyprland_connection()
        self.icon_size = icon_size
        self.icon_theme = Gtk.IconTheme.get_default()

        self.set_visible(False)

        if self.connection.ready:
            self.render_with_delay()
        else:
            self.connection.connect("event::ready", lambda *_: self.render_with_delay())

        for event in (
            "activewindow",
            "openwindow",
            "closewindow",
            "changefloatingmode",
        ):
            self.connection.connect("event::" + event, lambda *_: self.render(None))

    def render_with_delay(self, *_):
        GLib.timeout_add(101, self.render)

    def render(self, *_):
        self.children = []

        clients = self.fetch_clients()
        active_window_address = self.get_active_window_address()

        visible_clients = [
            client for client in clients if client["mapped"] and not client["hidden"]
        ]

        if visible_clients:
            for client in visible_clients:
                window_class = client["initialClass"].lower()
                icon = self.bake_window_icon(window_class)

                button = Button(image=icon, tooltip_text=client["title"])
                if client["address"] == active_window_address:
                    button.add_style_class("activated")
                button.connect(
                    "button-press-event",
                    self.on_icon_click,
                    client["address"],
                )

                self.add(button)
            self.set_visible(True)
            self.show_all()
        else:
            self.set_visible(False)

        self.set_visible(len(self.children) > 0)
        if self.children:
            self.show_all()

    def get_active_window_address(self) -> str:
        active_window_info = json.loads(
            self.connection.send_command("j/activewindow").reply.decode()
        )
        return active_window_info.get("address", "")

    def on_icon_click(self, widget, event, address):
        exec_shell_command_async(
            f"hyprctl dispatch focuswindow address:{address}", lambda *_: None
        )

    def fetch_clients(self) -> list[PagerClient]:
        return json.loads(self.connection.send_command("j/clients").reply.decode())

    def bake_window_icon(
        self,
        window_class: str,
        fallback_icon: str = "image-missing",
    ) -> Image:
        icon_name = self.get_icon_from_desktop_entry(window_class)

        if icon_name:
            pixbuf = self.load_icon(icon_name)
        else:
            pixbuf = self.load_icon(window_class, fallback_icon)

        return Image(pixbuf=pixbuf, size=self.icon_size)

    def get_icon_from_desktop_entry(self, window_class: str) -> str:
        for data_dir in GLib.get_system_data_dirs():
            applications_dir = os.path.join(data_dir, "applications")

            if os.path.isdir(applications_dir):
                for desktop_file in os.listdir(applications_dir):
                    if desktop_file.endswith(".desktop"):
                        file_path = os.path.join(applications_dir, desktop_file)
                        try:
                            with open(file_path) as f:
                                app_name = None
                                icon_name = None
                                for line in f:
                                    if line.startswith("Name="):
                                        app_name = line.split("=", 2)[1].strip().lower()
                                    elif line.startswith("Icon=") and app_name:
                                        icon_name = line.split("=", 2)[1].strip()
                                        if window_class in app_name:
                                            return icon_name
                        except Exception as e:
                            logger.error(f"Error reading {file_path}: {e}")
        return None

    def load_icon(
        self,
        icon_name: str,
        fallback_icon: str = "image-missing",
    ) -> GdkPixbuf.Pixbuf:
        try:
            pixbuf = self.icon_theme.load_icon(
                icon_name,
                self.icon_size,
                Gtk.IconLookupFlags.FORCE_SIZE,
            )
        except Exception:
            pixbuf = self.icon_theme.load_icon(
                fallback_icon,
                self.icon_size,
                Gtk.IconLookupFlags.FORCE_SIZE,
            )
        return pixbuf
