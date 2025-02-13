from time import sleep
import psutil
from fabric import Fabricator
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from snippets import MaterialIcon


class SystemInfo(Button):
    ICONS = [
        ("CPU", "settings_motion_mode"),
        ("Swap", "swap_horiz"),
        ("RAM", "memory_alt"),
        ("Temp", "thermometer"),
    ]

    def __init__(self):
        super().__init__(child=self._initialize_content())

        Fabricator(
            poll_from=self._refresh_system_info,
            stream=True,
            on_changed=lambda fab, data: self._update_ui(data),
        )

    def _initialize_content(self):
        self.box = Box(orientation="h", name="tray")
        self.progress_bars = {}
        self.labels = {}
        self.icons = {}

        for system, icon_name in self.ICONS:
            self._create_system_item(system, icon_name)

        return self.box

    def _create_system_item(self, system, icon_name):
        self.progress_bars[system] = self._create_progress_bar()
        self.labels[system] = self._create_label()
        self.icons[system] = self._create_icon(icon_name)

        overlay = Overlay(
            child=self.progress_bars[system], overlays=[self.icons[system]]
        )
        self.box.pack_start(overlay, False, False, 0)
        self.box.pack_start(self.labels[system], False, False, 0)

    def _create_progress_bar(self):
        return CircularProgressBar(
            name="progress", line_style="round", line_width=1, size=24
        )

    def _create_label(self):
        return Label(style="font-size:14px; margin: 4px;")

    def _create_icon(self, icon_name):
        return MaterialIcon(icon_name, size=16)

    def _refresh_system_info(self, fab: Fabricator):
        while True:
            yield {
                "CPU": round(psutil.cpu_percent()),
                "RAM": round(psutil.virtual_memory().percent),
                "Swap": round(psutil.swap_memory().percent),
                "Temp": self._get_device_temperature(),
            }
            sleep(1)

    @staticmethod
    def _get_device_temperature():
        try:
            temps = psutil.sensors_temperatures()
            if "coretemp" in temps:
                return round(temps["coretemp"][0].current, 1)
            elif "cpu_thermal" in temps:
                return round(temps["cpu_thermal"][0].current, 1)
            return None
        except Exception:
            return None

    def _update_ui(self, usages):
        for system, usage in usages.items():
            if usage is None:
                usage = 0
                self.labels[system].set_label("N/A")
            else:
                usage = int(usage)

            self.progress_bars[system].value = usage / 100
            self.labels[system].set_label(f"{usage}")
            self.progress_bars[system].set_tooltip_text(f"{system} Usage: {usage}%")
