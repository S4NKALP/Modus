import subprocess
import time
import gi  # type: ignore

from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.box import Box
from utils.wayland import WaylandWindow as Window
from fabric.utils.helpers import exec_shell_command_async, get_relative_path
from gi.repository import Gtk, GdkPixbuf  # type: ignore

# from config.c import c


class About(Gtk.Window):
    """About app for envshell"""

    def __init__(self):
        super().__init__(title="About Menu")
        self.set_default_size(250, 335)
        self.set_size_request(250, 355)
        self.set_resizable(False)
        self.set_wmclass("modus-about-menu", "modus-about-menu")
        self.set_name("about-menu")
        self.set_visible(False)

        # Main vertical box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)

        # About logo
        logo_box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            get_relative_path("../config/assets/icons/imac.svg"),
            158,
            108,
            preserve_aspect_ratio=True,
        )
        logo = Gtk.Image.new_from_pixbuf(pixbuf)
        logo_box.pack_start(logo, False, False, 0)

        # Labels
        name_label = Gtk.Label(label="Modus")
        date_label = Gtk.Label(label="Modus, 2025")

        # Info Section
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        info_title_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER
        )
        info_box_labels = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER
        )

        # Titles
        info_title_box.pack_start(
            Gtk.Label(label="SO", halign=Gtk.Align.END), False, False, 0
        )
        info_title_box.pack_start(
            Gtk.Label(label="Chip", halign=Gtk.Align.END), False, False, 0
        )
        info_title_box.pack_start(
            Gtk.Label(label="Memory", halign=Gtk.Align.END), False, False, 0
        )

        # Values
        so_label = Gtk.Label(
            label=subprocess.run(
                "cat /etc/*-release | grep '^PRETTY_NAME=' | cut -d '\"' -f 2",
                shell=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            halign=Gtk.Align.START,
        )
        chip_label = Gtk.Label(
            label=subprocess.run(
                "lscpu | grep 'Model name:' | awk '{print $5}'",
                shell=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            halign=Gtk.Align.START,
        )
        mem_label = Gtk.Label(
            label=subprocess.run(
                "free -h --giga | grep Mem | tr -s ' ' | cut -d ' ' -f 2",
                shell=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            halign=Gtk.Align.START,
        )

        info_box_labels.pack_start(so_label, False, False, 0)
        info_box_labels.pack_start(chip_label, False, False, 0)
        info_box_labels.pack_start(mem_label, False, False, 0)

        info_box.pack_start(info_title_box, False, False, 10)
        info_box.pack_start(info_box_labels, False, False, 10)

        # More Info Button
        button_box = Gtk.Box(halign=Gtk.Align.CENTER)
        more_info_button = Gtk.Button(label="More Info...", name="more-info-button")
        more_info_button.connect("clicked", self.open_more_info)
        button_box.pack_start(more_info_button, False, False, 0)

        # Add everything to the main box
        main_box.pack_start(logo_box, False, False, 0)
        main_box.pack_start(name_label, False, False, 0)
        main_box.pack_start(date_label, False, False, 0)
        main_box.pack_start(info_box, False, False, 0)
        main_box.pack_start(button_box, False, False, 0)

        # Add main box to the window
        self.add(main_box)

    def open_more_info(self, button):
        # exec_shell_command_async(f"xdg-open {c.get_shell_rule('about-more-info')}")
        pass

    def toggle(self, b):
        if self.get_visible():
            self.hide()
        else:
            self.show_all()
