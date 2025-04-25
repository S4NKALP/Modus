import subprocess
import json
import psutil
from gi.repository import GLib, Gdk

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
        self.gpu = []
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
        info = self.get_gpu_info()
        self.gpu = [int(v["gpu_util"][:-1]) for v in info]

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

    def get_gpu_info(self):
        try:
            return json.loads(subprocess.check_output(["nvtop", "-s"]))
        except:
            return []


shared_provider = MetricsProvider()


class SingularMetric:
    def __init__(self, id, name, icon):
        self.is_vertical_layout = data.VERTICAL
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
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.circle_button.connect("enter-notify-event", self.on_button_enter)
        self.circle_button.connect("leave-notify-event", self.on_button_leave)

        self.circle_button.connect("clicked", self.on_circle_clicked)

        self.level = Label(
            name="metrics-level",
            style_classes=id,
            label="0%",
            style="margin: 4px 0px;" if self.is_vertical_layout else "margin: 0 4px;",
        )
        self.revealer = Revealer(
            name=f"metrics-{id}-revealer",
            transition_duration=250,
            transition_type="slide-up" if self.is_vertical_layout else "slide-left",
            child=self.level,
            child_revealed=False,
        )

        self.box = Box(
            name=f"metrics-{id}-box",
            orientation="v" if self.is_vertical_layout else "h",
            spacing=0,
            children=[self.circle_button, self.revealer],
        )

        # Connect events for cursor changes to the box as well
        self.box.connect("enter-notify-event", self.on_button_enter)
        self.box.connect("leave-notify-event", self.on_button_leave)

        # Set initial tooltip - moved after box is created
        self.update_tooltip("0%")

    def update_tooltip(self, value_text):
        tooltip = f"{self.icon_markup} {self.name_markup}: {value_text}"
        # self.box.set_tooltip_markup(tooltip)
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

    def on_circle_clicked(self, button):
        # Toggle the revealed state of the label
        current_state = self.revealer.get_child_revealed()
        self.revealer.set_reveal_child(not current_state)


class Metrics(Box):
    def __init__(self, **kwargs):
        # Determine if we should use vertical layout for components
        self.is_vertical_layout = data.VERTICAL

        super().__init__(
            name="metrics",
            spacing=0,
            orientation="h" if not self.is_vertical_layout else "v",
            visible=True,
            all_visible=True,
            style="padding:4px 0px" if self.is_vertical_layout else "padding: 0px 4px;",
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

        visible = getattr(
            data,
            "METRICS_VISIBLE",
            {"cpu": True, "ram": True, "disk": True, "gpu": False, "swap": True},
        )
        disks = (
            [
                SingularMetric(
                    "disk",
                    f"DISK ({path})" if len(data.BAR_METRICS_DISKS) != 1 else "DISK",
                    icons.disk,
                )
                for path in data.BAR_METRICS_DISKS
            ]
            if visible.get("disk", True)
            else []
        )
        gpu_info = shared_provider.get_gpu_info()
        gpus = (
            [
                SingularMetric(
                    f"gpu",
                    f"GPU ({v['device_name']})" if len(gpu_info) != 1 else "GPU",
                    icons.gpu,
                )
                for v in gpu_info
            ]
            if visible.get("gpu", True)
            else []
        )

        self.cpu = (
            SingularMetric("cpu", "CPU", icons.cpu)
            if visible.get("cpu", True)
            else None
        )
        self.ram = (
            SingularMetric("ram", "RAM", icons.memory)
            if visible.get("ram", True)
            else None
        )
        self.swap = (
            SingularMetric("swap", "SWAP", icons.swap)
            if visible.get("swap", True)
            else None
        )
        self.bat = (
            SingularMetric("bat", "BATTERY", icons.battery)
            if visible.get("bat", True)
            else None
        )
        self.disk = disks
        self.gpu = gpus

        # Add only enabled metrics
        for disk in self.disk:
            self.add(disk.box)
            self.add(Box(name="metrics-sep"))
        if self.ram:
            self.add(self.ram.box)
            self.add(Box(name="metrics-sep"))
        if self.cpu:
            self.add(self.cpu.box)
        for gpu in self.gpu:
            self.add(Box(name="metrics-sep"))
            self.add(gpu.box)
        if self.swap:
            self.add(Box(name="metrics-sep"))
            self.add(self.swap.box)
        if self.bat:
            self.add(Box(name="metrics-sep"))
            self.add(self.bat.box)

        # Connect events directly to the button
        self.connect("enter-notify-event", self.on_mouse_enter)
        self.connect("leave-notify-event", self.on_mouse_leave)

        GLib.timeout_add_seconds(1, self.update_metrics)

        self.hide_timer = None
        self.hover_counter = 0

    def _format_percentage(self, value: int) -> str:
        return f"{value}%"

    def on_mouse_enter(self, widget, event):
        window = widget.get_window()
        if window:
            window.set_cursor(Gdk.Cursor(Gdk.CursorType.HAND2))

        if not data.VERTICAL:
            self.hover_counter += 1
            if self.hide_timer is not None:
                GLib.source_remove(self.hide_timer)
                self.hide_timer = None
            if self.cpu:
                self.cpu.revealer.set_reveal_child(True)
            if self.ram:
                self.ram.revealer.set_reveal_child(True)
            for disk in self.disk:
                disk.revealer.set_reveal_child(True)
            for gpu in self.gpu:
                gpu.revealer.set_reveal_child(True)
            if self.swap:
                self.swap.revealer.set_reveal_child(True)
            if self.bat:
                self.bat.revealer.set_reveal_child(True)
            return False

    def on_mouse_leave(self, widget, event):
        window = widget.get_window()
        if window:
            window.set_cursor(None)

        if not data.VERTICAL:
            if self.hover_counter > 0:
                self.hover_counter -= 1
            if self.hover_counter == 0:
                if self.hide_timer is not None:
                    GLib.source_remove(self.hide_timer)
                self.hide_timer = GLib.timeout_add(500, self.hide_revealer)
            return False

    def hide_revealer(self):
        if not data.VERTICAL:
            if self.cpu:
                self.cpu.revealer.set_reveal_child(False)
            if self.ram:
                self.ram.revealer.set_reveal_child(False)
            for disk in self.disk:
                disk.revealer.set_reveal_child(False)
            for gpu in self.gpu:
                gpu.revealer.set_reveal_child(False)
            self.hide_timer = None
            return False

    def update_metrics(self):
        cpu, mem, swap, disk = shared_provider.get_metrics()
        gpu = shared_provider.gpu
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
        for i, gpu_metric in enumerate(self.gpu):
            if i < len(gpu):
                value_text = self._format_percentage(int(gpu[i]))
                gpu_metric.circle.set_value(gpu[i] / 100.0)
                gpu_metric.level.set_label(value_text)
                gpu_metric.update_tooltip(value_text)
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
        if self.gpu: tooltip_metrics.extend(self.gpu)
        self.set_tooltip_markup((" - " if not data.VERTICAL else "\n").join([v.markup() for v in tooltip_metrics]))

        return True

    def update_battery(self, sender, battery_data):
        if self.bat is None:
            return

        value, charging = battery_data
        if value == 0:
            if self.bat:
                self.bat.box.set_visible(False)
        else:
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
