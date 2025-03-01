import psutil
from gi.repository import GLib

from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.overlay import Overlay
from fabric.widgets.circularprogressbar import CircularProgressBar
import utils.icons as icons


class Metrics(Box):
    ICONS = {
        "CPU": icons.cpu,
        "RAM": icons.memory,
        "Swap": icons.swap,
        "Disk": icons.disk,
        "Temp": icons.temp,
    }

    def __init__(self, **kwargs):
        super().__init__(
            name="metrics",
            spacing=8,
            h_align="center",
            v_align="fill",
            visible=True,
            all_visible=True,
        )

        self.progress_bars = {
            system: CircularProgressBar(
                name="metric-circle",
                line_style="round",
                line_width=2,
                size=28,
                start_angle=150,
                end_angle=390,
            )
            for system in self.ICONS
        }

        for system, icon_name in self.ICONS.items():
            overlay = Overlay(
                child=self.progress_bars[system],
                overlays=[Label(name="metric-icon", markup=icon_name)],
            )
            self.add(overlay)

        GLib.timeout_add_seconds(1, self._update_system_info)

    def _update_system_info(self):
        ram_usage = psutil.virtual_memory().percent
        swap_usage = psutil.swap_memory().percent
        disk_usage = psutil.disk_usage("/").percent
        cpu_usage = psutil.cpu_percent(interval=0)

        temp = self._get_device_temperature()
        temp_usage = temp if temp is not None else 0

        usages = {
            "CPU": cpu_usage,
            "RAM": ram_usage,
            "Swap": swap_usage,
            "Disk": disk_usage,
            "Temp": temp_usage,
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
                if key in temps and temps[key]:
                    return round(temps[key][0].current, 1)
        except Exception:
            pass
        return None
