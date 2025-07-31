import subprocess
import re
import gi  # type: ignore

from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.box import Box
from widgets.wayland import WaylandWindow as Window
from fabric.utils.helpers import exec_shell_command_async, get_relative_path
from gi.repository import Gtk, GdkPixbuf  # type: ignore


def read_dmi(field):
    try:
        with open(f"/sys/class/dmi/id/{field}") as f:
            return f.read().strip()
    except Exception:
        return "Unknown"


def get_gpu_name():
    try:
        output = (
            subprocess.check_output(
                "lspci -nn | grep -i 'VGA compatible controller'", shell=True, text=True
            )
            .strip()
            .split("\n")
        )

        def clean(line):
            matches = re.findall(r"\[(.*?)\]", line)
            if len(matches) >= 2:
                return matches[1].strip()
            desc = line.split(":", 2)[-1]
            return desc.replace("Corporation", "").strip()

        for line in output:
            if any(vendor in line.lower() for vendor in ["nvidia", "amd", "radeon"]):
                return clean(line)

        if output:
            return clean(output[0])

        return "Unknown GPU"
    except Exception:
        return "Unknown GPU"


class About(Gtk.Window):
    def __init__(self):
        super().__init__(title="About Menu")
        self.set_default_size(300, 550)
        self.set_size_request(300, 500)
        self.set_resizable(False)
        self.set_wmclass("modus-about-menu", "modus-about-menu")
        self.set_name("about-menu")
        self.set_visible(False)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)

        # Logo
        logo_box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            get_relative_path("../config/assets/icons/misc/imac.svg"),
            158,
            108,
            preserve_aspect_ratio=True,
        )
        logo = Gtk.Image.new_from_pixbuf(pixbuf)
        logo_box.pack_start(logo, False, False, 0)
        logo_box.set_margin_top(60)

        # Product Name & Vendor
        name_label = Gtk.Label()
        name_label.set_margin_top(30)
        name_label.set_markup(
            f"<b><span size='16000'>{read_dmi('product_name')}</span></b>"
        )

        vendor_label = Gtk.Label(label=read_dmi("sys_vendor"))
        vendor_label.set_name("vendor-label")
        vendor_label.set_halign(Gtk.Align.CENTER)

        # Info Grid
        info_grid = Gtk.Grid()
        info_grid.set_row_spacing(6)
        info_grid.set_column_spacing(10)
        info_grid.set_valign(Gtk.Align.CENTER)
        info_grid.set_halign(Gtk.Align.FILL)

        def make_label(text, align_end=False, name=None):
            label = Gtk.Label(label=text)
            label.set_halign(Gtk.Align.END if align_end else Gtk.Align.START)
            if name:
                label.set_name(name)
            return label

        # Info values
        labels = [
            (
                "Kernel",
                subprocess.run(
                    "uname -r", shell=True, capture_output=True, text=True
                ).stdout.strip(),
            ),
            (
                "CPU",
                subprocess.run(
                    "lscpu | grep 'Model name:' | cut -d ':' -f2-",
                    shell=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
            ),
            (
                "Memory",
                subprocess.run(
                    "free -h --giga | grep Mem | tr -s ' ' | cut -d ' ' -f 2",
                    shell=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
            ),
            ("GPU", get_gpu_name()),
            (
                "Uptime",
                subprocess.run(
                    "uptime -p", shell=True, capture_output=True, text=True
                ).stdout.strip(),
            ),
        ]

        for i, (title, value) in enumerate(labels):
            title_label = make_label(title, align_end=True)
            value_label = make_label(value, align_end=False, name="info-label")
            info_grid.attach(title_label, 0, i, 1, 1)
            info_grid.attach(value_label, 1, i, 1, 1)

        # Button
        button_box = Gtk.Box(halign=Gtk.Align.CENTER)
        button_box.set_margin_top(20)
        more_info_button = Gtk.Button(label="More Info...", name="more-info-button")
        more_info_button.connect("clicked", self.open_more_info)
        button_box.pack_start(more_info_button, False, False, 0)

        # Info Footer
        info = Gtk.Label(
            label="™ and © 2025 Linux Inc.\nAll rights reserved.\n\n",
            justify=Gtk.Justification.CENTER,
            halign=Gtk.Align.CENTER,
        )
        info.set_name("info-label")
        info.set_margin_top(10)

        # Layout Order
        main_box.pack_start(logo_box, False, False, 0)
        main_box.pack_start(name_label, False, False, 0)
        main_box.pack_start(vendor_label, False, False, 0)
        main_box.pack_start(info_grid, False, False, 0)
        main_box.pack_start(button_box, False, False, 0)
        main_box.pack_start(info, False, False, 0)

        self.add(main_box)

    def open_more_info(self, button):
        # TODO: Implement the logic to open more information
        pass

    def toggle(self, b):
        if self.get_visible():
            self.hide()
        else:
            self.show_all()
