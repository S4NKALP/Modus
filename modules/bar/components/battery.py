import psutil
from fabric import Fabricator
from fabric.widgets.box import Box
from fabric.widgets.overlay import Overlay
from fabric.widgets.label import Label
from fabric.widgets.circularprogressbar import CircularProgressBar
from snippets import MaterialIcon


class BatteryLabel(Box):
    ICONS_CHARGING = [
        "battery_charging_20",
        "battery_charging_20",
        "battery_charging_20",
        "battery_charging_30",
        "battery_charging_30",
        "battery_charging_50",
        "battery_charging_60",
        "battery_charging_80",
        "battery_charging_80",
        "battery_charging_90",
        "battery_charging_full",
    ]
    ICONS_NOT_CHARGING = [
        "battery_alert",
        "battery_1_bar",
        "battery_1_bar",
        "battery_2_bar",
        "battery_2_bar",
        "battery_3_bar",
        "battery_4_bar",
        "battery_4_bar",
        "battery_5_bar",
        "battery_6_bar",
        "battery_full",
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Fabricator(interval=1000, poll_from=self.update_battery_status)

    def update_battery_status(self, *_):
        battery = psutil.sensors_battery()
        if battery is None:
            self.hide()
            return
        is_charging = battery.power_plugged if battery else False
        icons = self.ICONS_CHARGING if is_charging else self.ICONS_NOT_CHARGING
        battery_percent = round(battery.percent)
        index = min(max(battery_percent // 10, 0), 10)
        battery_icon = MaterialIcon(icons[index], size=16)

        self.progress_bar = CircularProgressBar(
            name="progress", line_style="round", line_width=1, size=24
        )

        self.battery_overlay = Overlay(child=self.progress_bar, overlays=battery_icon)
        self.battery_label = Label(label=f"{battery_percent}%", name="battery-label")

        self.children = self.battery_label, self.battery_overlay

        battery_percent = round(battery.percent)
        self.progress_bar.value = battery_percent / 100
        # self.show() if battery_percent < 100 else self.hide()

        self.set_tooltip_text(
            f"Battery: {battery_percent}%\nStatus: {'Charging' if is_charging else 'Discharging'}"
        )

        return True
