import subprocess
import json
import psutil
from gi.repository import GLib, Gdk, Gtk

from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.revealer import Revealer
from fabric.core.fabricator import Fabricator
from fabric.widgets.button import Button
import utils.icons as icons
import config.data as data


class MetricsProvider:
    def __init__(self):
        self.cpu = 0.0
        self.mem = 0.0
        self.swap = 0.0
        self.disk = []
        self.bat_percent = 0.0
        self.bat_charging = None

        GLib.timeout_add_seconds(1, self._update)

    def _update(self):
        # Get non-blocking usage percentages (interval=0)
        # The first call may return 0, but subsequent calls will provide consistent values.
        self.cpu = psutil.cpu_percent(interval=0)
        mem = psutil.virtual_memory()
        self.mem = mem.percent
        swap = psutil.swap_memory()
        self.swap = swap.percent
        self.disk = [psutil.disk_usage(path).percent for path in data.BAR_METRICS_DISKS]

        battery = psutil.sensors_battery()
        if battery is None:
            self.bat_percent = 0.0
            self.bat_charging = None
        else:
            self.bat_percent = battery.percent
            self.bat_charging = battery.power_plugged
        return True

    def get_metrics(self):
        return (self.cpu, self.mem, self.swap, self.disk)

    def get_battery(self):
        return (self.bat_percent, self.bat_charging)


shared_provider = MetricsProvider()


class SingularMetric:
    def __init__(self, id, name, icon):
        self.name_markup = name
        self.icon_markup = icon

        self.icon = Label(name="metrics-icon", markup=icon)
        self.circle = CircularProgressBar(
            name="metrics-circle",
            value=0,
            size=26,
            line_width=2,
            start_angle=150,
            end_angle=390,
            style_classes=id,
            child=self.icon,
        )
        
        self.circle_button = Button(
            name=f"metrics-{id}-button",
            child=self.circle,
            style="padding: 0; margin: 0; background: none;",
        )

        self.circle_button.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK | Gdk.EventMask.BUTTON_PRESS_MASK
        )
        self.circle_button.connect("enter-notify-event", self.on_button_enter)
        self.circle_button.connect("leave-notify-event", self.on_button_leave)
        self.circle_button.connect("button-press-event", self.on_button_press)

        self.level = Label(
            name="metrics-level",
            style_classes=id,
            label="0%",
        )
        self.revealer = Revealer(
            name=f"metrics-{id}-revealer",
            transition_duration=250,
            transition_type="slide-left",
            child=self.level,
            child_revealed=False,
        )

        self.box = Box(
            name=f"metrics-{id}-box",
            orientation="h",
            spacing=0,
            children=[self.circle_button, self.revealer],
        )

        # Connect events for cursor changes to the box as well
        self.box.connect("enter-notify-event", self.on_button_enter)
        self.box.connect("leave-notify-event", self.on_button_leave)

        # Set initial tooltip
        self.update_tooltip("0%")

    def update_tooltip(self, value_text):
        tooltip = f"{self.icon_markup} {self.name_markup}: {value_text}"
        self.circle_button.set_tooltip_markup(tooltip)
        self.circle.set_tooltip_markup(tooltip)
        self.icon.set_tooltip_markup(tooltip)

    def markup(self):
        """Get formatted text for tooltip display"""
        return f"{self.icon_markup} {self.name_markup}: {self.level.get_label()}"

    def on_button_enter(self, widget, event):
        window = widget.get_window()
        if window:
            window.set_cursor(Gdk.Cursor(Gdk.CursorType.HAND2))

    def on_button_leave(self, widget, event):
        window = widget.get_window()
        if window:
            window.set_cursor(None)

    def on_button_press(self, widget, event):
        if event.button == 1:  # Left click
            # Get the parent Metrics instance
            parent = self.box.get_parent()
            while parent and not isinstance(parent, Metrics):
                parent = parent.get_parent()
            if parent:
                parent.toggle_all_metrics()
            return True  # Stop event propagation
        elif event.button == 3:  # Right click
            # Toggle only this metric's revealer
            current_state = self.revealer.get_child_revealed()
            self.revealer.set_reveal_child(not current_state)
            return True  # Stop event propagation
        return False


class Metrics(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="metrics",
            spacing=0,
            orientation="h",
            visible=True,
            all_visible=True,
            **kwargs,
        )

        self.batt_fabricator = Fabricator(
            poll_from=lambda v: shared_provider.get_battery(),
            on_changed=lambda f, v: self.update_battery,
            interval=1000,
            stream=False,
            default_value=0,
        )
        self.batt_fabricator.changed.connect(self.update_battery)
        GLib.idle_add(self.update_battery, None, shared_provider.get_battery())

        # Initialize all metrics
        disks = [
            SingularMetric(
                "disk",
                f"DISK ({path})" if len(data.BAR_METRICS_DISKS) != 1 else "DISK",
                icons.disk,
            )
            for path in data.BAR_METRICS_DISKS
        ]

        self.ram = SingularMetric("ram", "RAM", icons.memory)
        self.cpu = SingularMetric("cpu", "CPU", icons.cpu)
        self.swap = SingularMetric("swap", "SWAP", icons.swap)
        self.bat = SingularMetric("bat", "BATTERY", icons.battery)
        self.disk = disks

        # Create container for all metrics
        self.metrics_container = Box(name="metrics-container", orientation="h", spacing=0)
        self.add(self.metrics_container)

        # Create revealers for metrics
        self.cpu_revealer = Revealer(
            name="cpu-revealer",
            transition_duration=250,
            transition_type="slide-left",
            child=self.cpu.box,
            child_revealed=False,
        )
        self.swap_revealer = Revealer(
            name="swap-revealer",
            transition_duration=250,
            transition_type="slide-left",
            child=self.swap.box,
            child_revealed=False,
        )
        self.disk_revealers = [
            Revealer(
                name=f"disk-revealer-{i}",
                transition_duration=250,
                transition_type="slide-left",
                child=disk.box,
                child_revealed=False,
            )
            for i, disk in enumerate(self.disk)
        ]

        # Create permanent separator between memory and battery
        self.memory_battery_sep = Box(name="metrics-sep")

        # Create container for revealed metrics
        self.revealed_metrics = Box(name="revealed-metrics", orientation="h", spacing=0)
        self.revealed_metrics.add(self.cpu_revealer)
        for disk_revealer in self.disk_revealers:
            self.revealed_metrics.add(disk_revealer)
        self.revealed_metrics.add(self.swap_revealer)

        # Create container for memory and battery
        self.memory_battery_container = Box(name="memory-battery-container", orientation="h", spacing=0)
        if self.ram:
            self.memory_battery_container.add(self.ram.box)
        self.memory_battery_container.add(self.memory_battery_sep)
        if self.bat:
            self.memory_battery_container.add(self.bat.box)

        # Add metrics in the correct order
        self.metrics_container.add(self.revealed_metrics)
        self.metrics_container.add(self.memory_battery_container)

        # Initially hide all non-visible metrics
        self.cpu_revealer.set_reveal_child(False)
        self.swap_revealer.set_reveal_child(False)
        for disk_revealer in self.disk_revealers:
            disk_revealer.set_reveal_child(False)

        self.showing_all_metrics = False

        GLib.timeout_add_seconds(1, self.update_metrics)

    def toggle_all_metrics(self):
        self.showing_all_metrics = not self.showing_all_metrics
        
        # Toggle all revealers
        self.cpu_revealer.set_reveal_child(self.showing_all_metrics)
        self.swap_revealer.set_reveal_child(self.showing_all_metrics)
        for disk_revealer in self.disk_revealers:
            disk_revealer.set_reveal_child(self.showing_all_metrics)

        # Toggle spacing for revealed metrics and memory-battery container
        spacing = 6 if self.showing_all_metrics else 0
        self.revealed_metrics.set_spacing(spacing)
        self.metrics_container.set_spacing(spacing)

    def _format_percentage(self, value: int) -> str:
        return f"{value}%"

    def update_metrics(self):
        cpu, mem, swap, disk = shared_provider.get_metrics()
        if self.cpu:
            self.cpu.circle.set_value(cpu / 100.0)
            value_text = self._format_percentage(int(cpu))
            self.cpu.level.set_label(value_text)
            self.cpu.update_tooltip(value_text)
        if self.ram:
            self.ram.circle.set_value(mem / 100.0)
            value_text = self._format_percentage(int(mem))
            self.ram.level.set_label(value_text)
            self.ram.update_tooltip(value_text)
        for i, disk_metric in enumerate(self.disk):
            if i < len(disk):
                value_text = self._format_percentage(int(disk[i]))
                disk_metric.circle.set_value(disk[i] / 100.0)
                disk_metric.level.set_label(value_text)
                disk_metric.update_tooltip(value_text)
        if self.swap:
            self.swap.circle.set_value(swap / 100.0)
            value_text = self._format_percentage(int(swap))
            self.swap.level.set_label(value_text)
            self.swap.update_tooltip(value_text)
        if self.bat:
            bat_percent, _ = shared_provider.get_battery()
            self.bat.circle.set_value(bat_percent / 100.0)
            value_text = self._format_percentage(int(bat_percent))
            self.bat.level.set_label(value_text)
            self.bat.update_tooltip(value_text)

        # Tooltip: only show enabled metrics
        tooltip_metrics = []
        if self.disk: tooltip_metrics.extend(self.disk)
        if self.swap: tooltip_metrics.append(self.swap)
        if self.bat: tooltip_metrics.append(self.bat)
        if self.ram: tooltip_metrics.append(self.ram)
        if self.cpu: tooltip_metrics.append(self.cpu)

        return True

    def update_battery(self, sender, battery_data):
        if self.bat is None:
            return

        value, charging = battery_data
        # Always show battery, even if value is 0
        if self.bat:
            self.bat.box.set_visible(True)
            self.bat.circle.set_value(value / 100)
        percentage = int(value)
        self.bat.level.set_label(self._format_percentage(percentage))

        # Apply alert styling if battery is low AND not charging
        if percentage <= 15 and charging == False:
            self.bat.icon.add_style_class("alert")
            self.bat.circle.add_style_class("alert")
        else:
            self.bat.icon.remove_style_class("alert")
            self.bat.circle.remove_style_class("alert")

        # Choose the icon based on charging state first, then battery level
        if percentage == 100:
            self.bat.icon.set_markup(icons.battery)
            charging_status = f"{icons.bat_full} Fully Charged"
        elif charging == True:
            self.bat.icon.set_markup(icons.charging)
            charging_status = f"{icons.bat_charging} Charging"
        elif percentage <= 15 and charging == False:
            self.bat.icon.set_markup(icons.alert)
            charging_status = f"{icons.bat_low} Low Battery"
        elif charging == False:
            self.bat.icon.set_markup(icons.discharging)
            charging_status = f"{icons.bat_discharging} Discharging"
        else:
            self.bat.icon.set_markup(icons.battery)
            charging_status = "Battery"
            
        # Update individual tooltip for battery
        self.bat.update_tooltip(f"{charging_status}: {self._format_percentage(percentage)}")
        
        # Update the combined tooltip
        self.update_metrics()
