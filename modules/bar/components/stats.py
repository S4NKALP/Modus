import psutil
from gi.repository import GLib

from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.overlay import Overlay
from fabric.widgets.circularprogressbar import CircularProgressBar

import snippets.iconss as icons


class SystemInfo(Box):
    ICONS = {
        "CPU": icons.cpu,
        "RAM": icons.memory,
        "Swap": icons.swap,
        "Disk": icons.disk,
        "Temp": icons.temp,
    }

    def __init__(self, **kwargs):
        super().__init__(
            name="system-info",
            spacing=8,
            h_align="center",
            v_align="fill",
            visible=True,
            all_visible=True,
        )

        self.progress_bars = {
            system: CircularProgressBar(
                name="stats-progress",
                line_style="round",
                line_width=3,
                size=28,
                start_at=0,
                end_at=0.5,
                start_angle=0,
                end_angle=180,
            )
            for system in self.ICONS
        }

        for system, icon_name in self.ICONS.items():
            overlay = Overlay(
                child=self.progress_bars[system],
                overlays=[Label(name="stats-icons", markup=icon_name)],
            )
            self.add(overlay)

        GLib.timeout_add_seconds(1, self._update_system_info)

    def _update_system_info(self):
        ram_usage = psutil.virtual_memory().percent
        swap_usage = psutil.swap_memory().percent
        disk_usage = psutil.disk_usage("/").percent
        cpu = psutil.cpu_percent(interval=0)

        usages = {
            "CPU": cpu,
            "RAM": ram_usage,
            "Swap": swap_usage,
            "Disk": disk_usage,
            "Temp": self._get_device_temperature(),
        }

        for system, usage in usages.items():
            self.progress_bars[system].value = usage / 100.0
            self.progress_bars[system].set_tooltip_text(f"{system} {usage:.1f}%")

        return True

    @staticmethod
    def _get_device_temperature():
        try:
            temps = psutil.sensors_temperatures()
            for key in ("coretemp", "cpu_thermal"):
                if key in temps:
                    return round(temps[key][0].current, 1)
        except Exception:
            pass
        return None
