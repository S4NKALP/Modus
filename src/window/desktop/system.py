from typing import Optional

import psutil
from fabric.utils import GLib, invoke_repeater, logger
from fabric.widgets.box import Box
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay

from window.desktop.registry import DesktopWidgetRegistry

SYSTEM_UPDATE_INTERVAL = 2000


class SystemInfoBase(Box):
    @staticmethod
    def create_progress_bar(name: str = "progress-bar", size: int = 80, **kwargs):
        return CircularProgressBar(
            name=name,
            start_angle=270,
            end_angle=630,
            min_value=0,
            max_value=100,
            size=size,
            **kwargs,
        )

    def __init__(self, name: str, **kwargs):
        super().__init__(
            layer="bottom",
            title="sysinfo",
            name=name,
            visible=True,
            size=(170, 170),
            h_expand=True,
            v_expand=True,
            all_visible=True,
            **kwargs,
        )
        self.progress = self.create_progress_bar(name="progress")
        self.main_label = Label(
            label="0%\nLoading", justification="center", name="progress-label"
        )
        self.info_container = Box(
            name="info-container", orientation="v", spacing=2, h_align="center"
        )
        self.add(
            Box(
                name="progress-bar-container",
                h_expand=True,
                v_expand=True,
                orientation="v",
                spacing=12,
                h_align="center",
                v_align="center",
                children=[
                    Box(
                        children=[
                            Overlay(
                                child=self.progress,
                                tooltip_text="",
                                overlays=self.main_label,
                            )
                        ]
                    ),
                    Box(
                        h_align="center",
                        justification="centre",
                        orientation="v",
                        children=[self.info_container],
                    ),
                ],
            )
        )

    def start_updates(self):
        self.update()
        self._system_timer_id = invoke_repeater(SYSTEM_UPDATE_INTERVAL, self.update)

    def destroy(self):
        """Cleanup system info update timer"""
        if hasattr(self, "_system_timer_id") and self._system_timer_id:
            GLib.source_remove(self._system_timer_id)
            self._system_timer_id = None
        super().destroy()

    def create_info_line(
        self, indicator_name: str, info_text: str, value_text: str
    ) -> Box:
        line = Box(
            orientation="h",
            spacing=4,
            h_align="start",
            children=[
                Label(label="■", name=indicator_name),
                Label(label=info_text, name="info-text"),
                Label(label=value_text, name="info-value"),
            ],
        )
        line.value_label = line.get_children()[2]
        return line

    def update(self) -> bool:
        raise NotImplementedError


class DesktopRamInfoWidget(SystemInfoBase):
    def __init__(self, **kwargs):
        super().__init__("info-box-widget", **kwargs)
        self.used_line = self.create_info_line("used-color-indicator", "Used", "0.0GB")
        self.free_line = self.create_info_line("free-color-indicator", "Free", "0.0GB")
        self.info_container.add(self.used_line)
        self.info_container.add(self.free_line)
        self.start_updates()

    def update(self) -> bool:
        try:
            mem = psutil.virtual_memory()
            self.main_label.set_label(f" {round(mem.percent):<2} %\nRAM")
            self.used_line.value_label.set_label(f"{round(mem.used / (1024**3), 1)}GB")
            self.free_line.value_label.set_label(
                f"{round(mem.available / (1024**3), 1)}GB"
            )
            GLib.idle_add(self.progress.set_value, mem.percent)
        except Exception as e:
            logger.error(f"Error: {e}")
        return True


class DesktopCpuInfoWidget(SystemInfoBase):
    def __init__(self, **kwargs):
        super().__init__("info-box-widget", **kwargs)
        self.temp_value = Label(label="0°C", name="info-value")
        self.info_container.add(
            Box(
                orientation="h",
                spacing=4,
                h_align="start",
                children=[Label(label="Temp", name="info-text"), self.temp_value],
            )
        )
        self.start_updates()

    def get_cpu_temp(self) -> Optional[float]:
        try:
            temps = psutil.sensors_temperatures()
            for name, entries in temps.items():
                if any(s in name.lower() for s in ["coretemp", "k10temp", "cpu"]):
                    for entry in entries:
                        if any(
                            p in (entry.label or "").lower()
                            for p in ["package id 0", "core 0", ""]
                        ):
                            return round(entry.current, 1)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        return None

    def update(self) -> bool:
        try:
            cpu = psutil.cpu_percent()
            self.main_label.set_label(f" {round(cpu):<2} %\nCPU")
            temp = self.get_cpu_temp()
            self.temp_value.set_label(f"{temp}°C" if temp else "N/A")
            GLib.idle_add(self.progress.set_value, cpu)
        except Exception as e:
            logger.error(f"Error: {e}")
        return True


DesktopWidgetRegistry.register(
    "ram_info", DesktopRamInfoWidget, (174, 174), (0.80729, 0.82827)
)
DesktopWidgetRegistry.register(
    "cpu_info", DesktopCpuInfoWidget, (174, 174), (0.90573, 0.82638)
)
