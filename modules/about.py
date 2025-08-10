import re
import subprocess
import os

import gi

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gtk  # type: ignore

from fabric.utils.helpers import get_relative_path
from utils.roam import modus_service
from utils.icon_resolver import IconResolver


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


def get_executable_path(exec_string):
    """Extract and find the actual executable path from Exec field"""
    if not exec_string:
        return None
    
    # Remove common exec modifiers and arguments
    exec_parts = exec_string.split()
    if not exec_parts:
        return None
    
    executable = exec_parts[0]
    
    # Remove common prefixes
    prefixes_to_remove = ['env', 'bash', 'sh', '/usr/bin/env']
    while executable in prefixes_to_remove and len(exec_parts) > 1:
        exec_parts.pop(0)
        executable = exec_parts[0]
    
    # If it's already an absolute path, check if it exists
    if executable.startswith('/'):
        if os.path.exists(executable):
            return executable
        return None
    
    # Search in PATH
    try:
        result = subprocess.run(['which', executable], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    
    return None


def get_app_info(wmclass):
    """Get comprehensive application information from .desktop file"""
    if not wmclass:
        return {
            "name": "Desktop",
            "version": "",
            "comment": "Desktop Environment",
            "icon": "desktop",
            "exec": "",
            "location": "",
            "categories": "",
            "desktop_file": ""
        }
    
    desktop_paths = [
        "/usr/share/applications",
        "/var/lib/flatpak/exports/share/applications",
        os.path.expanduser("~/.local/share/applications"),
        "/usr/local/share/applications"
    ]
    
    for path in desktop_paths:
        if not os.path.exists(path):
            continue
            
        # Try exact match first
        exact_matches = [f for f in os.listdir(path) 
                        if f.lower() == f"{wmclass.lower()}.desktop"]
        
        # Then try starts with
        startswith_matches = [f for f in os.listdir(path) 
                             if f.startswith(wmclass.lower()) and f.endswith('.desktop')]
        
        # Finally try contains
        contains_matches = [f for f in os.listdir(path) 
                           if wmclass.lower() in f.lower() and f.endswith('.desktop')]
        
        # Process matches in order of preference
        for matches in [exact_matches, startswith_matches, contains_matches]:
            for filename in matches:
                desktop_file = os.path.join(path, filename)
                try:
                    with open(desktop_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    name = wmclass.title()
                    version = ""
                    comment = ""
                    icon = wmclass.lower()
                    exec_cmd = ""
                    categories = ""
                    
                    # Parse desktop file
                    in_desktop_entry = False
                    for line in content.split('\n'):
                        line = line.strip()
                        if line == '[Desktop Entry]':
                            in_desktop_entry = True
                            continue
                        elif line.startswith('[') and line.endswith(']'):
                            in_desktop_entry = False
                            continue
                        
                        if not in_desktop_entry or '=' not in line:
                            continue
                            
                        key, value = line.split('=', 1)
                        if key == 'Name':
                            name = value
                        elif key == 'Version':
                            version = value
                        elif key == 'Comment':
                            comment = value
                        elif key == 'GenericName' and not comment:
                            # Use GenericName as fallback description
                            comment = value
                        elif key == 'Icon':
                            icon = value
                        elif key == 'Exec':
                            exec_cmd = value
                        elif key == 'Categories':
                            categories = value
                    
                    # Get executable location
                    location = get_executable_path(exec_cmd)
                    
                    return {
                        "name": name,
                        "version": version,
                        "comment": comment,
                        "icon": icon,
                        "exec": exec_cmd,
                        "location": location or "",
                        "categories": categories,
                        "desktop_file": desktop_file
                    }
                except Exception:
                    continue
    
    # Fallback: try to find executable in PATH
    location = ""
    try:
        result = subprocess.run(['which', wmclass.lower()], capture_output=True, text=True)
        if result.returncode == 0:
            location = result.stdout.strip()
    except Exception:
        pass
    
    return {
        "name": wmclass.title() if wmclass else "Unknown Application",
        "version": "",
        "comment": "",
        "icon": wmclass.lower() if wmclass else "application-x-executable",
        "exec": "",
        "location": location,
        "categories": "",
        "desktop_file": ""
    }


class AboutApp(Gtk.Window):
    def __init__(self, app_name="Unknown Application", wmclass=""):
        super().__init__(title=f"About {app_name}")
        self.app_name = app_name
        self.wmclass = wmclass
        self.icon_resolver = IconResolver()
        
        self.set_default_size(400, 500)
        self.set_size_request(400, 480)
        self.set_resizable(False)
        self.set_title(f"About {app_name}")
        self.set_name("about-app")
        self.set_visible(False)

        self.setup_ui()

    def setup_ui(self):
        app_info = get_app_info(self.wmclass)
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(25)
        main_box.set_margin_end(25)

        # App Icon
        logo_box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        try:
            # Use IconResolver's get_icon_pixbuf method like other parts of the project
            icon_pixbuf = self.icon_resolver.get_icon_pixbuf(app_info["icon"], 128)
            if icon_pixbuf:
                logo = Gtk.Image.new_from_pixbuf(icon_pixbuf)
            else:
                raise Exception("Icon pixbuf not found")
        except Exception:
            # Fallback: try direct file path if it's an absolute path
            try:
                if app_info["icon"].startswith('/') and os.path.exists(app_info["icon"]):
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        app_info["icon"], 128, 128, preserve_aspect_ratio=True
                    )
                    logo = Gtk.Image.new_from_pixbuf(pixbuf)
                else:
                    raise Exception("Direct path failed")
            except Exception:
                # Final fallback: emoji
                logo = Gtk.Label()
                logo.set_markup("<span size='72000'>📱</span>")
        
        logo_box.pack_start(logo, False, False, 0)
        logo_box.set_margin_bottom(15)

        # App Name
        app_name_label = Gtk.Label()
        app_name_label.set_markup(f"<b><span size='18000'>{app_info['name']}</span></b>")
        app_name_label.set_halign(Gtk.Align.CENTER)
        app_name_label.set_margin_bottom(5)

        # Version (if available)
        version_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if app_info["version"]:
            version_label = Gtk.Label(label=f"Version {app_info['version']}")
            version_label.set_name("version-label")
            version_label.set_halign(Gtk.Align.CENTER)
            version_box.pack_start(version_label, False, False, 0)
        
        version_box.set_margin_bottom(15)

        # Description/Comment - Make it more prominent
        description_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if app_info["comment"]:
            # Create a frame for the description to make it stand out
            desc_frame = Gtk.Frame()
            desc_frame.set_shadow_type(Gtk.ShadowType.IN)
            
            description_label = Gtk.Label()
            description_label.set_markup(f"<i>{app_info['comment']}</i>")
            description_label.set_justify(Gtk.Justification.CENTER)
            description_label.set_halign(Gtk.Align.CENTER)
            description_label.set_line_wrap(True)
            description_label.set_max_width_chars(45)
            description_label.set_margin_top(8)
            description_label.set_margin_bottom(8)
            description_label.set_margin_start(12)
            description_label.set_margin_end(12)
            
            desc_frame.add(description_label)
            description_box.pack_start(desc_frame, False, False, 0)
        else:
            # Show a placeholder if no description is available
            placeholder_label = Gtk.Label()
            placeholder_label.set_markup("<i><span foreground='#888888'>No description available</span></i>")
            placeholder_label.set_halign(Gtk.Align.CENTER)
            description_box.pack_start(placeholder_label, False, False, 0)
        
        description_box.set_margin_bottom(15)

        # Information Grid
        info_frame = Gtk.Frame()
        info_frame.set_label("Application Information")
        info_frame.set_label_align(0.5, 0.5)
        
        info_grid = Gtk.Grid()
        info_grid.set_row_spacing(8)
        info_grid.set_column_spacing(15)
        info_grid.set_margin_top(10)
        info_grid.set_margin_bottom(10)
        info_grid.set_margin_start(15)
        info_grid.set_margin_end(15)
        info_grid.set_valign(Gtk.Align.CENTER)
        info_grid.set_halign(Gtk.Align.FILL)

        def make_info_row(label_text, value_text, row):
            """Create a row in the info grid"""
            label = Gtk.Label(label=f"{label_text}:")
            label.set_halign(Gtk.Align.END)
            label.set_markup(f"<b>{label_text}:</b>")
            
            value = Gtk.Label(label=value_text)
            value.set_halign(Gtk.Align.START)
            value.set_line_wrap(True)
            value.set_max_width_chars(30)
            value.set_name("info-value-label")
            
            info_grid.attach(label, 0, row, 1, 1)
            info_grid.attach(value, 1, row, 1, 1)

        row = 0
        
        # Application Name
        make_info_row("Name", app_info["name"], row)
        row += 1
        
        # Version
        if app_info["version"]:
            make_info_row("Version", app_info["version"], row)
            row += 1
        
        # Executable Location
        if app_info["location"]:
            make_info_row("Location", app_info["location"], row)
            row += 1
        
        # Window Class
        if self.wmclass:
            make_info_row("Window Class", self.wmclass, row)
            row += 1
        
        # Categories
        if app_info["categories"]:
            categories = app_info["categories"].replace(";", ", ").strip(", ")
            make_info_row("Categories", categories, row)
            row += 1
        
        # Desktop File
        if app_info["desktop_file"]:
            desktop_file_name = os.path.basename(app_info["desktop_file"])
            make_info_row("Desktop File", desktop_file_name, row)
            row += 1

        info_frame.add(info_grid)

        # Layout
        main_box.pack_start(logo_box, False, False, 0)
        main_box.pack_start(app_name_label, False, False, 0)
        main_box.pack_start(version_box, False, False, 0)
        main_box.pack_start(description_box, False, False, 0)
        main_box.pack_start(info_frame, False, False, 0)

        self.add(main_box)

    def toggle(self, b):
        if self.get_visible():
            self.hide()
        else:
            self.show_all()


class About(Gtk.Window):
    def __init__(self):
        super().__init__(title="About Menu")
        self.set_default_size(300, 550)
        self.set_size_request(300, 500)
        self.set_resizable(False)
        self.set_title("About PC")
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
