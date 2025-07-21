import gi
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GLib, Gtk

from config.settings.utils import bind_vars

gi.require_version("Gtk", "3.0")


class SystemTab:
    """System settings and metrics management tab for settings"""

    def __init__(self, show_lock_checkbox=False, show_idle_checkbox=False, window_size_enforcer=None):
        self.show_lock_checkbox = show_lock_checkbox
        self.show_idle_checkbox = show_idle_checkbox
        self.window_size_enforcer = window_size_enforcer
        
        # Widget references
        self.terminal_entry = None
        self.lock_switch = None
        self.idle_switch = None
        self.limited_apps_entry = None
        self.ignored_apps_entry = None
        self.metrics_switches = {}
        self.disk_entries = None
        self._create_disk_edit_entry_func = None

    def create_system_tab(self):
        """Create the System tab content"""
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

        vbox = Box(orientation="v", spacing=15, style="margin: 15px;")
        scrolled_window.add(vbox)

        # Create terminal and hyprland settings section
        self._create_terminal_hyprland_section(vbox)

        # Create notification settings section
        self._create_notification_settings_section(vbox)

        # Create system metrics section
        self._create_system_metrics_section(vbox)

        return scrolled_window

    def _create_terminal_hyprland_section(self, vbox):
        """Create terminal and Hyprland integration section"""
        system_grid = Gtk.Grid()
        system_grid.set_column_spacing(20)
        system_grid.set_row_spacing(10)
        system_grid.set_margin_bottom(15)
        vbox.add(system_grid)

        # Terminal settings
        terminal_header = Label(markup="<b>Terminal Settings</b>", h_align="start")
        system_grid.attach(terminal_header, 0, 0, 2, 1)
        terminal_label = Label(label="Command:", h_align="start", v_align="center")
        system_grid.attach(terminal_label, 0, 1, 1, 1)
        self.terminal_entry = Entry(
            text=bind_vars.get("terminal_command", "kitty -e"),
            tooltip_text="Command used to launch terminal apps (e.g., 'kitty -e')",
            h_expand=True,
        )
        system_grid.attach(self.terminal_entry, 1, 1, 1, 1)
        hint_label = Label(
            markup="<small>Examples: 'kitty -e', 'alacritty -e', 'foot -e'</small>",
            h_align="start",
        )
        system_grid.attach(hint_label, 0, 2, 2, 1)

        # Hyprland integration
        hypr_header = Label(markup="<b>Hyprland Integration</b>", h_align="start")
        system_grid.attach(hypr_header, 2, 0, 2, 1)
        row = 1
        self.lock_switch = None
        if self.show_lock_checkbox:
            lock_label = Label(
                label="Replace Hyprlock config", h_align="start", v_align="center"
            )
            system_grid.attach(lock_label, 2, row, 1, 1)
            lock_switch_container = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
            )
            self.lock_switch = Gtk.Switch(
                tooltip_text="Replace Hyprlock configuration with Modus's custom config"
            )
            lock_switch_container.add(self.lock_switch)
            system_grid.attach(lock_switch_container, 3, row, 1, 1)
            row += 1
        self.idle_switch = None
        if self.show_idle_checkbox:
            idle_label = Label(
                label="Replace Hypridle config", h_align="start", v_align="center"
            )
            system_grid.attach(idle_label, 2, row, 1, 1)
            idle_switch_container = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
            )
            self.idle_switch = Gtk.Switch(
                tooltip_text="Replace Hypridle configuration with Modus's custom config"
            )
            idle_switch_container.add(self.idle_switch)
            system_grid.attach(idle_switch_container, 3, row, 1, 1)
            row += 1
        if self.show_lock_checkbox or self.show_idle_checkbox:
            note_label = Label(
                markup="<small>Existing configs will be backed up</small>",
                h_align="start",
            )
            system_grid.attach(note_label, 2, row, 2, 1)

    def _create_notification_settings_section(self, vbox):
        """Create notification settings section"""
        notifications_header = Label(
            markup="<b>Notification Settings</b>", h_align="start"
        )
        vbox.add(notifications_header)

        notif_grid = Gtk.Grid()
        notif_grid.set_column_spacing(20)
        notif_grid.set_row_spacing(10)
        notif_grid.set_margin_start(10)
        notif_grid.set_margin_top(5)
        notif_grid.set_margin_bottom(15)
        vbox.add(notif_grid)

        # Limited Apps History
        limited_apps_label = Label(
            label="Limited Apps History:", h_align="start", v_align="center"
        )
        notif_grid.attach(limited_apps_label, 0, 0, 1, 1)

        limited_apps_list = bind_vars.get("limited_apps_history", ["Spotify"])
        limited_apps_text = ", ".join(f'"{app}"' for app in limited_apps_list)
        self.limited_apps_entry = Entry(
            text=limited_apps_text,
            tooltip_text='Enter app names separated by commas, e.g: "Spotify", "Discord"',
            h_expand=True,
        )
        notif_grid.attach(self.limited_apps_entry, 1, 0, 1, 1)

        limited_apps_hint = Label(
            markup='<small>Apps with limited notification history (format: "App1", "App2")</small>',
            h_align="start",
        )
        notif_grid.attach(limited_apps_hint, 0, 1, 2, 1)

        # History Ignored Apps
        ignored_apps_label = Label(
            label="History Ignored Apps:", h_align="start", v_align="center"
        )
        notif_grid.attach(ignored_apps_label, 0, 2, 1, 1)

        ignored_apps_list = bind_vars.get("history_ignored_apps", ["Modus"])
        ignored_apps_text = ", ".join(f'"{app}"' for app in ignored_apps_list)
        self.ignored_apps_entry = Entry(
            text=ignored_apps_text,
            tooltip_text='Enter app names separated by commas, e.g: "Modus", "Screenshot"',
            h_expand=True,
        )
        notif_grid.attach(self.ignored_apps_entry, 1, 2, 1, 1)

        ignored_apps_hint = Label(
            markup='<small>Apps whose notifications are ignored in history (format: "App1", "App2")</small>',
            h_align="start",
        )
        notif_grid.attach(ignored_apps_hint, 0, 3, 2, 1)

    def _create_system_metrics_section(self, vbox):
        """Create system metrics section"""
        metrics_header = Label(markup="<b>System Metrics Options</b>", h_align="start")
        vbox.add(metrics_header)
        metrics_grid = Gtk.Grid(
            column_spacing=15, row_spacing=8, margin_start=10, margin_top=5
        )
        vbox.add(metrics_grid)

        self.metrics_switches = {}
        metric_names = {
            "cpu": "CPU",
            "ram": "RAM",
            "swap": "Swap",
            "disk": "Disk",
            "gpu": "GPU",
        }

        metrics_grid.attach(Label(label="Show in Metrics", h_align="start"), 0, 0, 1, 1)
        for i, (key, label_text) in enumerate(metric_names.items()):
            switch = Gtk.Switch(
                active=bind_vars.get("metrics_visible", {}).get(key, True)
            )
            self.metrics_switches[key] = switch
            metrics_grid.attach(
                Label(label=label_text, h_align="start"), 0, i + 1, 1, 1
            )
            metrics_grid.attach(switch, 1, i + 1, 1, 1)

        def enforce_minimum_metrics(switch_dict):
            enabled_switches = [s for s in switch_dict.values() if s.get_active()]
            can_disable = len(enabled_switches) > 1
            for s in switch_dict.values():
                s.set_sensitive(True if can_disable or not s.get_active() else False)

        def on_metric_toggle(_switch, _gparam, switch_dict):
            enforce_minimum_metrics(switch_dict)

        for s_s in self.metrics_switches.values():
            s_s.connect("notify::active", on_metric_toggle, self.metrics_switches)
        enforce_minimum_metrics(self.metrics_switches)

        # Disk directories section
        disks_label = Label(
            label="Disk directories for Metrics", h_align="start", v_align="center"
        )
        vbox.add(disks_label)

        # Create a scrolled container for disk entries to prevent overflow
        disk_entries_scrolled = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=False,
            v_expand=False,
            propagate_width=False,
            propagate_height=False,
        )
        # Set fixed size for disk entries container
        disk_entries_scrolled.set_size_request(550, 120)

        self.disk_entries = Box(orientation="v", spacing=8, h_align="start")
        # Set size constraints for the disk entries box
        self.disk_entries.set_size_request(530, -1)
        disk_entries_scrolled.add(self.disk_entries)

        self._create_disk_edit_entry_func = lambda path: self._add_disk_entry_widget(path)

        for p in bind_vars.get("metrics_disks", ["/"]):
            self._create_disk_edit_entry_func(p)
        vbox.add(disk_entries_scrolled)

        add_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )
        add_btn = Button(
            label="Add new disk",
            on_clicked=lambda _: self._create_disk_edit_entry_func("/"),
        )
        add_container.add(add_btn)
        vbox.add(add_container)

    def _add_disk_entry_widget(self, path):
        """Helper to add a disk entry row to the disk_entries Box."""
        bar = Box(orientation="h", spacing=10, h_align="start")
        # Set fixed height for disk entry rows
        bar.set_size_request(-1, 30)
        entry = Entry(text=path, h_expand=True)
        bar.add(entry)
        x_btn = Button(label="X")
        x_btn.connect(
            "clicked",
            lambda _, current_bar_to_remove=bar: self._remove_disk_entry(current_bar_to_remove),
        )
        bar.add(x_btn)
        self.disk_entries.add(bar)
        self.disk_entries.show_all()
        # Enforce window size after adding content
        if self.window_size_enforcer:
            GLib.idle_add(self.window_size_enforcer)

    def _remove_disk_entry(self, bar_to_remove):
        """Helper to remove a disk entry and enforce window size"""
        self.disk_entries.remove(bar_to_remove)
        # Enforce window size after removing content
        if self.window_size_enforcer:
            GLib.idle_add(self.window_size_enforcer)

    def get_system_values(self):
        """Get current system values from widgets"""
        values = {}

        values["terminal_command"] = self.terminal_entry.get_text()

        values["metrics_visible"] = {
            k: s.get_active() for k, s in self.metrics_switches.items()
        }
        values["metrics_disks"] = [
            child.get_children()[0].get_text()
            for child in self.disk_entries.get_children()
            if isinstance(child, Gtk.Box)
            and child.get_children()
            and isinstance(child.get_children()[0], Entry)
        ]

        # Parse notification app lists
        def parse_app_list(text):
            """Parse comma-separated app names with quotes"""
            if not text.strip():
                return []
            apps = []
            for app in text.split(","):
                app = app.strip()
                if app.startswith('"') and app.endswith('"'):
                    app = app[1:-1]
                elif app.startswith("'") and app.endswith("'"):
                    app = app[1:-1]
                if app:
                    apps.append(app)
            return apps

        values["limited_apps_history"] = parse_app_list(
            self.limited_apps_entry.get_text()
        )
        values["history_ignored_apps"] = parse_app_list(
            self.ignored_apps_entry.get_text()
        )

        return values

    def get_hyprland_switches(self):
        """Get the state of Hyprland integration switches"""
        return {
            "replace_lock": self.lock_switch and self.lock_switch.get_active(),
            "replace_idle": self.idle_switch and self.idle_switch.get_active()
        }

    def reset_to_defaults(self, defaults):
        """Reset system settings to default values"""
        self.terminal_entry.set_text(defaults.get("terminal_command", "kitty -e"))

        metrics_vis_defaults = defaults.get("metrics_visible", {})
        for k, s_widget in self.metrics_switches.items():
            s_widget.set_active(metrics_vis_defaults.get(k, True))

        def enforce_minimum_metrics(switch_dict):
            enabled_switches = [s for s in switch_dict.values() if s.get_active()]
            can_disable = len(enabled_switches) > 1
            for s in switch_dict.values():
                s.set_sensitive(
                    True if can_disable or not s.get_active() else False
                )

        enforce_minimum_metrics(self.metrics_switches)

        # Reset disk entries
        for child in list(self.disk_entries.get_children()):
            self.disk_entries.remove(child)

        for p in defaults.get("metrics_disks", ["/"]):
            self._create_disk_edit_entry_func(p)

        # Reset notification app lists
        limited_apps_list = defaults.get("limited_apps_history", ["Spotify"])
        limited_apps_text = ", ".join(f'"{app}"' for app in limited_apps_list)
        self.limited_apps_entry.set_text(limited_apps_text)

        ignored_apps_list = defaults.get("history_ignored_apps", ["Modus"])
        ignored_apps_text = ", ".join(f'"{app}"' for app in ignored_apps_list)
        self.ignored_apps_entry.set_text(ignored_apps_text)

        # Reset Hyprland switches
        if self.lock_switch:
            self.lock_switch.set_active(False)
        if self.idle_switch:
            self.idle_switch.set_active(False)
