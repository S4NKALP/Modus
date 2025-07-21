from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.grid import Grid
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from config.data import APP_NAME_CAP
from config.settings.utils import bind_vars


class KeyBindingsTab:
    """Key bindings management tab for settings"""

    def __init__(self):
        self.entries = []

    def create_key_bindings_tab(self):
        """Create the Key Bindings tab content"""
        scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=False,
            v_expand=False,
            propagate_width=False,
            propagate_height=False,
        )
        # Set fixed size to match tab stack dimensions
        scrolled_window.set_size_request(580, 580)

        main_vbox = Box(orientation="v", spacing=10, style="margin: 15px;")
        scrolled_window.add(main_vbox)

        keybind_grid = Grid(column_spacing=10, row_spacing=8, style="margin: 5px;")

        action_label = Label(
            markup="<b>Action</b>", h_align="start", style="margin-bottom: 5px;"
        )
        modifier_label = Label(
            markup="<b>Modifier</b>", h_align="start", style="margin-bottom: 5px;"
        )
        separator_label = Label(
            label="+", h_align="center", style="margin-bottom: 5px;"
        )
        key_label = Label(
            markup="<b>Key</b>", h_align="start", style="margin-bottom: 5px;"
        )

        keybind_grid.attach(action_label, 0, 0, 1, 1)
        keybind_grid.attach(modifier_label, 1, 0, 1, 1)
        keybind_grid.attach(separator_label, 2, 0, 1, 1)
        keybind_grid.attach(key_label, 3, 0, 1, 1)

        self.entries = []
        bindings = [
            (f"Reload {APP_NAME_CAP}", "prefix_restart", "suffix_restart"),
            ("Message", "prefix_msg", "suffix_msg"),
            (
                "Application Switcher",
                "prefix_application_switcher",
                "suffix_application_switcher",
            ),
            ("Launcher", "prefix_launcher", "suffix_launcher"),
            ("App Launcher", "prefix_app_launcher", "suffix_app_launcher"),
            ("Clipboard History", "prefix_cliphist", "suffix_cliphist"),
            ("Wallpapers", "prefix_wallpapers", "suffix_wallpapers"),
            ("Random Wallpaper", "prefix_randwall", "suffix_randwall"),
            ("Emoji Picker", "prefix_emoji", "suffix_emoji"),
            ("Kanban", "prefix_kanban", "suffix_kanban"),
            ("Power Menu", "prefix_power", "suffix_power"),
            ("Toggle Caffeine", "prefix_caffeine", "suffix_caffeine"),
            ("Settings", "prefix_settings", "suffix_settings"),
            (
                "Restart with inspector",
                "prefix_restart_inspector",
                "suffix_restart_inspector",
            ),
        ]

        for i, (label_text, prefix_key, suffix_key) in enumerate(bindings):
            row = i + 1
            binding_label = Label(label=label_text, h_align="start")
            keybind_grid.attach(binding_label, 0, row, 1, 1)
            prefix_entry = Entry(text=bind_vars.get(prefix_key, ""))
            keybind_grid.attach(prefix_entry, 1, row, 1, 1)
            plus_label = Label(label="+", h_align="center")
            keybind_grid.attach(plus_label, 2, row, 1, 1)
            suffix_entry = Entry(text=bind_vars.get(suffix_key, ""))
            keybind_grid.attach(suffix_entry, 3, row, 1, 1)
            self.entries.append((prefix_key, suffix_key, prefix_entry, suffix_entry))

        main_vbox.add(keybind_grid)
        return scrolled_window

    def get_key_binding_values(self):
        """Get current key binding values from entries"""
        values = {}
        for prefix_key, suffix_key, prefix_entry, suffix_entry in self.entries:
            values[prefix_key] = prefix_entry.get_text()
            values[suffix_key] = suffix_entry.get_text()
        return values

    def reset_to_defaults(self, defaults):
        """Reset key bindings to default values"""
        for prefix_key, suffix_key, prefix_entry, suffix_entry in self.entries:
            prefix_entry.set_text(defaults.get(prefix_key, ""))
            suffix_entry.set_text(defaults.get(suffix_key, ""))
