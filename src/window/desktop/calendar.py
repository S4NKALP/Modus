import calendar
import datetime

from fabric.utils import GLib, invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from utils.functions import clear_children
from window.desktop.registry import DesktopWidgetRegistry

CALENDAR_UPDATE_INTERVAL = int(
    (
        (
            datetime.datetime.combine(
                datetime.date.today() + datetime.timedelta(days=1), datetime.time.min
            )
            - datetime.datetime.now()
        ).total_seconds()
    )
    * 1000
)


class DesktopCalendarWidget(Box):
    def __init__(self, **kwargs):
        calendar.setfirstweekday(6)
        super().__init__(
            name="calendar-widget",
            h_expand=True,
            v_expand=True,
            orientation="v",
            **kwargs,
        )

        self._update_current_date()
        self._create_header()
        self._create_days_header()
        self._create_calendar_grid()
        self.add(self.month_label)
        self.add(self.days_header)
        self.add(self.calendar_grid)
        self._calendar_timer_id = invoke_repeater(
            CALENDAR_UPDATE_INTERVAL, self.update_calendar_if_needed
        )

    def destroy(self):
        """Cleanup calendar update timer"""
        if hasattr(self, "_calendar_timer_id") and self._calendar_timer_id:
            GLib.source_remove(self._calendar_timer_id)
            self._calendar_timer_id = None
        super().destroy()

    def _update_current_date(self):
        now = datetime.datetime.now()
        self.current_month, self.current_year, self.current_day = (
            now.month,
            now.year,
            now.day,
        )

    def _create_header(self):
        self.month_label = Label(
            name="calendar-month",
            label=calendar.month_name[self.current_month],
            h_align="start",
            justification="left",
        )

    def _create_days_header(self):
        self.days_header = Box(
            name="calendar-days-header", orientation="h", h_expand=True, spacing=2
        )
        for i, day_name in enumerate(["S", "M", "T", "W", "T", "F", "S"]):
            self.days_header.add(
                Label(
                    name="calendar-day-header-weekend"
                    if i in (0, 6)
                    else "calendar-day-header",
                    label=day_name,
                    h_align="center",
                    h_expand=True,
                )
            )

    def _create_calendar_grid(self):
        self.calendar_grid = Box(name="calendar-grid", orientation="v", spacing=1)
        self.update_calendar()

    def update_calendar_if_needed(self) -> bool:
        now = datetime.datetime.now()
        if (now.month, now.year, now.day) != (
            self.current_month,
            self.current_year,
            self.current_day,
        ):
            self._update_current_date()
            self.update_calendar()
        return True

    def update_calendar(self):

        clear_children(self.calendar_grid)
        self.month_label.set_label(calendar.month_name[self.current_month])
        cal = calendar.monthcalendar(self.current_year, self.current_month)
        for week in cal:
            week_box = Box(orientation="h", spacing=2, h_expand=True)
            for i, day in enumerate(week):
                if day == 0:
                    label = Label(
                        name="calendar-day-empty",
                        label="",
                        h_align="center",
                        h_expand=True,
                    )
                else:
                    is_today = (
                        day == self.current_day
                        and self.current_month == datetime.datetime.now().month
                    )
                    name = (
                        "calendar-day-today"
                        if is_today
                        else ("calendar-day-weekend" if i in (0, 6) else "calendar-day")
                    )
                    label = Label(
                        name=name, label=str(day), h_align="center", h_expand=True
                    )
                week_box.add(label)
            self.calendar_grid.add(week_box)


class DesktopCalendarContainer(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            name="calendar-box-widget",
            v_expand=True,
            size=(170, 170),
            v_align="center",
            h_align="center",
            children=[DesktopCalendarWidget()],
            **kwargs,
        )


DesktopWidgetRegistry.register(
    "calendar", DesktopCalendarContainer, (174, 174), (0.19375, 0.00949)
)
