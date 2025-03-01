import calendar
from datetime import datetime
import gi
from fabric.widgets.label import Label

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
import utils.icons as icons


class Calendar(Gtk.Box):
    def __init__(self):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL, spacing=8, name="calendar"
        )

        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        self.current_day = datetime.now().day
        self.previous_key = (self.current_year, self.current_month)

        self.cache_threshold = 1  # Allow current month +/- 1 month
        self.month_views = {}

        self.header = Gtk.Box(spacing=4, name="header")
        self.pack_start(self.header, False, False, 0)

        self.prev_month_button = Gtk.Button(
            name="prev-month-button",
            child=Label(name="month-button-label", markup=icons.chevron_left),
        )
        self.prev_month_button.connect("clicked", self.on_prev_month_clicked)
        self.header.pack_start(self.prev_month_button, False, False, 0)

        self.month_label = Gtk.Label(name="month-label")
        self.header.pack_start(self.month_label, True, True, 0)

        self.next_month_button = Gtk.Button(
            name="next-month-button",
            child=Label(name="month-button-label", markup=icons.chevron_right),
        )
        self.next_month_button.connect("clicked", self.on_next_month_clicked)
        self.header.pack_start(self.next_month_button, False, False, 0)

        self.weekday_row = Gtk.Box(spacing=4, name="weekday-row")
        self.pack_start(self.weekday_row, False, False, 0)

        self.stack = Gtk.Stack(name="calendar-stack")
        self.stack.set_transition_duration(500)
        self.pack_start(self.stack, True, True, 0)

        self.update_header()
        self.update_calendar()
        GLib.timeout_add_seconds(60, self.check_date_change)

    def update_header(self):
        self.month_label.set_text(
            datetime(self.current_year, self.current_month, 1)
            .strftime("%B %Y")
            .capitalize()
        )
        for child in self.weekday_row.get_children():
            self.weekday_row.remove(child)

        days = self.get_weekday_initials()
        for day in days:
            label = Gtk.Label(label=day.upper(), name="weekday-label")
            self.weekday_row.pack_start(label, True, True, 0)
        self.weekday_row.show_all()

    def update_calendar(self):
        new_key = (self.current_year, self.current_month)

        if new_key > self.previous_key:
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        elif new_key < self.previous_key:
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_RIGHT)

        self.previous_key = new_key

        if new_key not in self.month_views:
            month_view = self.create_month_view(self.current_year, self.current_month)
            self.month_views[new_key] = month_view
            self.stack.add_titled(
                month_view,
                f"{self.current_year}_{self.current_month}",
                f"{self.current_year}_{self.current_month}",
            )

        self.stack.set_visible_child_name(f"{self.current_year}_{self.current_month}")
        self.update_header()
        self.stack.show_all()
        self.prune_cache()

    def prune_cache(self):
        def month_index(key):
            year, month = key
            return year * 12 + (month - 1)

        current_index = month_index((self.current_year, self.current_month))
        keys_to_remove = [
            key
            for key in self.month_views
            if abs(month_index(key) - current_index) > self.cache_threshold
        ]

        for key in keys_to_remove:
            widget = self.month_views.pop(key)
            self.stack.remove(widget)

    def create_month_view(self, year, month):
        grid = Gtk.Grid(
            column_homogeneous=True, row_homogeneous=False, name="calendar-grid"
        )

        cal = calendar.Calendar(firstweekday=6)
        month_days = cal.monthdayscalendar(year, month)

        prev_month = month - 1 if month > 1 else 12
        next_month = month + 1 if month < 12 else 1
        prev_year = year if month > 1 else year - 1
        next_year = year if month < 12 else year + 1

        prev_month_days_count = calendar.monthrange(prev_year, prev_month)[1]
        next_month_day = 1

        for row, week in enumerate(month_days):
            for col, day in enumerate(week):
                day_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, name="day-box")
                top_spacer = Gtk.Box(hexpand=True, vexpand=True)
                middle_box = Gtk.Box(hexpand=True, vexpand=True)
                bottom_spacer = Gtk.Box(hexpand=True, vexpand=True)

                if day == 0:
                    if row == 0:
                        day_num = prev_month_days_count - week[:col].count(0)
                        label = Gtk.Label(label=str(day_num), name="prev-month-day")
                    else:
                        label = Gtk.Label(
                            label=str(next_month_day), name="next-month-day"
                        )
                        next_month_day += 1
                else:
                    label = Gtk.Label(label=str(day), name="day-label")
                    if (
                        day == self.current_day
                        and month == datetime.now().month
                        and year == datetime.now().year
                    ):
                        label.get_style_context().add_class("current-day")

                middle_box.pack_start(
                    Gtk.Box(hexpand=True, vexpand=True), True, True, 0
                )
                middle_box.pack_start(label, False, False, 0)
                middle_box.pack_start(
                    Gtk.Box(hexpand=True, vexpand=True), True, True, 0
                )

                day_box.pack_start(top_spacer, True, True, 0)
                day_box.pack_start(middle_box, True, True, 0)
                day_box.pack_start(bottom_spacer, True, True, 0)

                grid.attach(day_box, col, row, 1, 1)

        grid.show_all()
        return grid

    def get_weekday_initials(self):
        return [datetime(2023, 1, i + 1).strftime("%a")[:1] for i in range(7)]

    def on_prev_month_clicked(self, widget):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self.update_calendar()

    def on_next_month_clicked(self, widget):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self.update_calendar()

    def check_date_change(self):
        now = datetime.now()
        if (
            now.day != self.current_day
            or now.month != self.current_month
            or now.year != self.current_year
        ):
            self.current_day = now.day
            self.current_month = now.month
            self.current_year = now.year
            self.update_calendar()
        return True
