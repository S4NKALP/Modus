import json
import subprocess

import config.data as data
import psutil
import utils.icons as icons
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from gi.repository import GLib


class MetricsProvider:
    def __init__(self):
        self.gpu = []
        self.cpu = 0.0
        self.mem = 0.0
        self.swap = 0.0
        self.disk = []

        self.bat_percent = 0.0
        self.bat_charging = None
        self.bat_time = 0

        self._gpu_update_running = False

        GLib.timeout_add_seconds(1, self._update)

    def _update(self):
        self.cpu = psutil.cpu_percent(interval=0)
        self.mem = psutil.virtual_memory().percent
        self.swap = psutil.swap_memory().percent
        self.disk = [psutil.disk_usage(path).percent for path in data.METRICS_DISKS]

        if not self._gpu_update_running:
            self._start_gpu_update_async()

        return True

    def _start_gpu_update_async(self):
        self._gpu_update_running = True

        GLib.Thread.new("nvtop-thread", lambda _: self._run_nvtop_in_thread(), None)

    def _run_nvtop_in_thread(self):
        output = None
        error_message = None
        try:
            result = subprocess.check_output(["nvtop", "-s"], text=True, timeout=10)
            output = result
        except FileNotFoundError:
            error_message = "nvtop command not found."
        except subprocess.CalledProcessError as e:
            error_message = (
                f"nvtop failed with exit code {e.returncode}: {e.stderr.strip()}"
            )
        except subprocess.TimeoutExpired:
            error_message = "nvtop command timed out."
        except Exception as e:
            error_message = f"Unexpected error running nvtop: {e}"

        GLib.idle_add(self._process_gpu_output, output, error_message)
        self._gpu_update_running = False

    def _process_gpu_output(self, output, error_message):
        try:
            if error_message:
                self.gpu = []
            elif output:
                try:
                    info = json.loads(output)
                    if not info or not isinstance(info, list):
                        self.gpu = []
                        return False

                    gpu_utils = []
                    for gpu in info:
                        if not isinstance(gpu, dict):
                            continue
                        util = gpu.get("gpu_util", "0%")
                        if not isinstance(util, str):
                            continue
                        try:
                            # Remove % and convert to int, default to 0 if fails
                            util_value = int(util.rstrip("%") or 0)
                            gpu_utils.append(util_value)
                        except (ValueError, TypeError):
                            continue

                    self.gpu = gpu_utils if gpu_utils else []
                except (KeyError, ValueError, TypeError, AttributeError):
                    self.gpu = []
            else:
                self.gpu = []
        except json.JSONDecodeError:
            self.gpu = []
        except Exception:
            self.gpu = []

        return False

    def get_metrics(self):
        return (self.cpu, self.mem, self.swap, self.disk, self.gpu)

    def get_battery(self):
        return (self.bat_percent, self.bat_charging, self.bat_time)

    def get_gpu_info(self):
        try:
            result = subprocess.check_output(["nvtop", "-s"], text=True, timeout=5)
            if not result.strip():
                return []

            info = json.loads(result)
            if not info or not isinstance(info, list):
                return []

            valid_gpus = []
            for gpu in info:
                if not isinstance(gpu, dict):
                    continue

                gpu_data = {
                    "device_name": gpu.get("device_name", "GPU"),
                    "gpu_util": gpu.get("gpu_util", "0%"),
                    "mem_util": gpu.get("mem_util", "0%"),
                    "temperature": gpu.get("temperature", "0 C"),
                    "power": gpu.get("power", "0 W"),
                }
                valid_gpus.append(gpu_data)

            return valid_gpus

        except FileNotFoundError:
            return []
        except subprocess.CalledProcessError:
            return []
        except subprocess.TimeoutExpired:
            return []
        except json.JSONDecodeError:
            return []
        except Exception:
            return []


shared_provider = MetricsProvider()


class SingularMetric:
    def __init__(self, id, name, icon):
        self.name_markup = name
        self.icon_markup = icon

        self.icon = Label(name="metrics-icon", markup=icon)
        self.circle = CircularProgressBar(
            name="metrics-circle",
            value=0,
            size=28,
            line_width=2,
            start_angle=150,
            end_angle=390,
            style_classes=id,
            child=self.icon,
        )

        self.level = Label(name="metrics-level", style_classes=id, label="0%")
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
            children=[self.circle, self.revealer],
        )

    def markup(self):
        return f"{self.icon_markup} {self.name_markup}: {self.level.get_label()}"


class Metrics(Button):
    def __init__(self, **kwargs):
        super().__init__(name="metrics", **kwargs)

        main_box = Box(
            spacing=0,
            orientation="h" if not data.VERTICAL else "v",
            visible=True,
            all_visible=True,
        )

        visible = getattr(
            data,
            "METRICS_VISIBLE",
            {"cpu": True, "ram": True, "swap": True, "disk": True, "gpu": True},
        )
        disks = (
            [
                SingularMetric(
                    "disk",
                    f"DISK ({path})" if len(data.METRICS_DISKS) != 1 else "DISK",
                    icons.disk,
                )
                for path in data.METRICS_DISKS
            ]
            if visible.get("disk", True)
            else []
        )

        gpu_info = shared_provider.get_gpu_info()
        gpus = (
            [
                SingularMetric(
                    "gpu",
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
        self.disk = disks
        self.gpu = gpus

        for disk in self.disk:
            main_box.add(disk.box)
            main_box.add(Box(name="metrics-sep"))
        if self.ram:
            main_box.add(self.ram.box)
            main_box.add(Box(name="metrics-sep"))
        if self.swap:
            main_box.add(self.swap.box)
            main_box.add(Box(name="metrics-sep"))
        if self.cpu:
            main_box.add(self.cpu.box)
        for gpu in self.gpu:
            main_box.add(Box(name="metrics-sep"))
            main_box.add(gpu.box)

        self.add(main_box)

        self.connect("clicked", self.on_click)
        self.labels_visible = False

        GLib.timeout_add_seconds(1, self.update_metrics)

    def _format_percentage(self, value: int) -> str:
        """Formato natural del porcentaje sin forzar ancho fijo."""
        return f"{value}%"

    def on_click(self, widget):
        if not data.VERTICAL:
            self.labels_visible = not self.labels_visible
            if self.cpu:
                self.cpu.revealer.set_reveal_child(self.labels_visible)
            if self.ram:
                self.ram.revealer.set_reveal_child(self.labels_visible)
            if self.swap:
                self.swap.revealer.set_reveal_child(self.labels_visible)
            for disk in self.disk:
                disk.revealer.set_reveal_child(self.labels_visible)
            for gpu in self.gpu:
                gpu.revealer.set_reveal_child(self.labels_visible)

    def update_metrics(self):
        cpu, mem, swap, disks, gpus = shared_provider.get_metrics()

        if self.cpu:
            self.cpu.circle.set_value(cpu / 100.0)
            self.cpu.level.set_label(self._format_percentage(int(cpu)))
        if self.ram:
            self.ram.circle.set_value(mem / 100.0)
            self.ram.level.set_label(self._format_percentage(int(mem)))
        if self.swap:
            self.swap.circle.set_value(swap / 100.0)
            self.swap.level.set_label(self._format_percentage(int(swap)))
        for i, disk in enumerate(self.disk):
            if i < len(disks):
                disk.circle.set_value(disks[i] / 100.0)
                disk.level.set_label(self._format_percentage(int(disks[i])))
        for i, gpu in enumerate(self.gpu):
            if i < len(gpus):
                gpu.circle.set_value(gpus[i] / 100.0)
                gpu.level.set_label(self._format_percentage(int(gpus[i])))

        tooltip_metrics = []
        if self.disk:
            tooltip_metrics.extend(self.disk)
        if self.ram:
            tooltip_metrics.append(self.ram)
        if self.swap:
            tooltip_metrics.append(self.swap)
        if self.cpu:
            tooltip_metrics.append(self.cpu)
        if self.gpu:
            tooltip_metrics.extend(self.gpu)
        self.set_tooltip_markup(
            (" - " if not data.VERTICAL else "\n").join(
                [v.markup() for v in tooltip_metrics]
            )
        )

        return True
