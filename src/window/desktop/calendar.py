import calendar
import datetime

from fabric.utils import GLib
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from window.desktop.registry import DesktopWidgetRegistry

MAX_WEEKS = 6


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
        self._schedule_calendar_update()

    def destroy(self):
        """Cleanup calendar update timer"""
        if hasattr(self, "_calendar_timer_id") and self._calendar_timer_id:
            GLib.source_remove(self._calendar_timer_id)
            self._calendar_timer_id = None
        super().destroy()

    def _ms_until_next_day(self) -> int:
        now = datetime.datetime.now()
        midnight = datetime.datetime.combine(
            now.date() + datetime.timedelta(days=1), datetime.time.min
        )
        return int((midnight - now).total_seconds() * 1000)

    def _schedule_calendar_update(self):
        self._calendar_timer_id = GLib.timeout_add(
            self._ms_until_next_day(), self._on_calendar_timer
        )

    def _on_calendar_timer(self) -> bool:
        self.update_calendar_if_needed()
        self._schedule_calendar_update()
        return False

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
        self._week_boxes = []
        self._day_labels = []
        for _ in range(MAX_WEEKS):
            week_box = Box(orientation="h", spacing=2, h_expand=True)
            labels = []
            for _ in range(7):
                label = Label(
                    name="calendar-day-empty",
                    label="",
                    h_align="center",
                    h_expand=True,
                )
                labels.append(label)
                week_box.add(label)
            self._week_boxes.append(week_box)
            self._day_labels.append(labels)
            self.calendar_grid.add(week_box)
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
        now = datetime.datetime.now()
        self.month_label.set_label(calendar.month_name[self.current_month])
        cal = calendar.monthcalendar(self.current_year, self.current_month)
        for week_idx, week in enumerate(cal):
            self._week_boxes[week_idx].set_visible(True)
            for i, day in enumerate(week):
                label = self._day_labels[week_idx][i]
                if day == 0:
                    label.set_label("")
                    label.set_name("calendar-day-empty")
                else:
                    is_today = (
                        day == self.current_day
                        and self.current_month == now.month
                        and self.current_year == now.year
                    )
                    name = (
                        "calendar-day-today"
                        if is_today
                        else ("calendar-day-weekend" if i in (0, 6) else "calendar-day")
                    )
                    label.set_label(str(day))
                    label.set_name(name)
        for week_idx in range(len(cal), MAX_WEEKS):
            self._week_boxes[week_idx].set_visible(False)


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
