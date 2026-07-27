from fabric.widgets.box import Box
from fabric.widgets.datetime import DateTime

from window.desktop.registry import DesktopWidgetRegistry


class DesktopDateWidget(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="date-widget",
            h_expand=True,
            v_expand=True,
            justification="center",
            h_align="center",
            v_align="start",
            orientation="v",
            **kwargs,
        )
        self.top = Box(orientation="h", name="date-top", h_expand=True)
        # Using a highly frequent interval (e.g. 10000ms/10s) causes the DateTime widget
        # (which inherits from Gtk.Button) to repeatedly call set_label.
        # In GTK3, repeatedly replacing a button's label can cause rendering glitches
        # where the layout engine drops the child label's visibility after some time.
        # Since this is just a date widget, we increase the interval to 100000ms (100 seconds)
        # which easily avoids the continuous redraw glitch while keeping the date accurate.
        date_interval = 100000
        self.dateone = DateTime(formatters=["%a"], interval=date_interval, name="day")
        self.datetwo = DateTime(formatters=["%b"], interval=date_interval, name="month")
        self.datethree = DateTime(
            formatters=["%-d"], interval=date_interval, name="date"
        )
        self.top.add(self.dateone)
        self.top.add(self.datetwo)
        self.add(self.top)
        self.add(self.datethree)


class DesktopDateContainer(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            name="date-container",
            v_expand=True,
            size=(170, 170),
            v_align="center",
            h_align="center",
            children=[DesktopDateWidget()],
            **kwargs,
        )


DesktopWidgetRegistry.register("date", DesktopDateContainer, (174, 174), (0.0, 0.0))
