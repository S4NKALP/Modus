from fabric.widgets.box import Box
from fabric.widgets.datetime import DateTime
from fabric.widgets.wayland import WaylandWindow as Window

import config.data as data
from services import has_config_changed, on_config_change


class ClockWidget(Box):
    def __init__(self, **kwargs):
        cfg = data.DATA()
        use_12hr = cfg["desktop_widget_time_format"] == "12 hrs"
        time_fmt = "%I:%M %p" if use_12hr else "%H:%M"
        date_fmt = cfg["desktop_widget_date_format"]

        self._date = DateTime(name="date", formatters=date_fmt, interval=10000)
        self._time = DateTime(name="time", formatters=time_fmt)

        children = [self._date, self._time]

        super().__init__(
            orientation="v",
            name="clock-widget",
            children=children,
            **kwargs,
        )

    def apply_config(self):
        cfg = data.DATA()
        use_12hr = cfg["desktop_widget_time_format"] == "12 hrs"
        time_fmt = "%I:%M %p" if use_12hr else "%H:%M"
        date_fmt = cfg["desktop_widget_date_format"]

        self._time.formatters = [time_fmt]
        self._time.interval = self._time.interval

        self._date.formatters = [date_fmt]
        self._date.interval = self._date.interval


class DesktopWidget(Window):
    def __init__(self, **kwargs):
        cfg = data.DATA()
        self._clock = ClockWidget()

        super().__init__(
            name="clock",
            layer="bottom",
            anchor=cfg["desktop_widget_anchor"],
            margin=cfg["desktop_widget_margin"],
            exclusivity="none",
            child=self._clock,
            pass_through=True,
            all_visible=True,
            visible=cfg["desktop_widget_enabled"],
        )

        on_config_change(self._on_config_change)

    def _on_config_change(self, new_config, old_config):
        config_paths = [
            "desktop_widget.enabled",
            "desktop_widget.time_format",
            "desktop_widget.date_format",
            "desktop_widget.anchor",
            "desktop_widget.margin",
        ]

        if not any(has_config_changed(old_config, new_config, p) for p in config_paths):
            return

        cfg = data.DATA()
        self.set_visible(cfg["desktop_widget_enabled"])
        self.set_property("anchor", cfg["desktop_widget_anchor"])
        self.set_property("margin", cfg["desktop_widget_margin"])
        self._clock.apply_config()
