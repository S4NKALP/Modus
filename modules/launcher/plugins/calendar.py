"""
Calendar plugin for the launcher.
Calendar with visual dates and working Enter key navigation.
"""

import calendar
import datetime
from typing import List

import gi
import utils.icons as icons
from fabric.widgets.label import Label
from gi.repository import Gtk
from fabric.widgets.button import Button
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result

gi.require_version("Gtk", "3.0")


class CalendarWidget(Gtk.Box):
    """Visual calendar widget showing month grid with dates and navigation buttons."""

    def __init__(self, month: int, year: int, plugin_instance=None):
        super().__init__(name="calendar-widget", orientation=Gtk.Orientation.VERTICAL, spacing=2)

        # Set size constraints to fit within launcher (following CSS)
        self.set_size_request(540, 240)
        self.set_vexpand(False)
        self.set_hexpand(True)

        self.display_month = month
        self.display_year = year
        self.today = datetime.date.today()
        self.plugin = plugin_instance

        # Make widget focusable for keyboard events
        self.set_can_focus(True)
        self.connect("key-press-event", self._on_key_press)

        self.setup_ui()

    def setup_ui(self):
        """Setup the calendar UI with navigation buttons."""
        # Header with navigation buttons
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_box.set_halign(Gtk.Align.CENTER)
        header_box.set_name("calendar-header-box")

        # Previous button
        prev_button = Gtk.Button(child=Label(markup=icons.chevron_left, name="calendar-nav-button"))
        prev_button.connect("clicked", self._on_previous_clicked)

        # Month/Year label (following CSS naming)
        month_name = calendar.month_name[self.display_month]
        self.month_label = Label(
            name="calendar-month-year",
            label=f"{month_name} {self.display_year}",
            h_align="center"
        )
        self.month_label.set_size_request(150, -1)  # Fixed width for consistent layout

        # Next button
        next_button = Gtk.Button(child = Label(markup=icons.chevron_right, name="calendar-nav-button"))
        next_button.connect("clicked", self._on_next_clicked)

        # Add to header box
        header_box.pack_start(prev_button, False, False, 0)
        header_box.pack_start(self.month_label, True, True, 0)
        header_box.pack_start(next_button, False, False, 0)

        # Calendar grid (following CSS naming)
        grid = Gtk.Grid(
            name="calendar-grid",
            column_spacing=1,
            row_spacing=1,
            column_homogeneous=True,
            row_homogeneous=True
        )

        # Day headers (following CSS naming)
        day_names = ['Sun','Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        for i, day_name in enumerate(day_names):
            day_header = Label(
                name="calendar-day-header",
                label=day_name,
                h_align="center"
            )
            grid.attach(day_header, i, 0, 1, 1)

        # Calendar days (following CSS naming)
        cal = calendar.monthcalendar(self.display_year, self.display_month)
        for week_num, week in enumerate(cal, start=1):
            for day_num, day in enumerate(week):
                if day == 0:
                    # Empty cell (following CSS naming)
                    empty = Label(name="calendar-day-empty", label="")
                    grid.attach(empty, day_num, week_num, 1, 1)
                else:
                    # Day label (following CSS naming)
                    day_label = Label(
                        name="calendar-day-label",
                        label=str(day),
                        h_align="center"
                    )

                    # Highlight today (CSS class)
                    if (day == self.today.day and
                        self.display_month == self.today.month and
                        self.display_year == self.today.year):
                        day_label.get_style_context().add_class("today")

                    # Highlight weekends (CSS class)
                    if day_num in [6]:  # Saturday
                        day_label.get_style_context().add_class("weekend")

                    grid.attach(day_label, day_num, week_num, 1, 1)

        # Add to main box
        self.pack_start(header_box, False, False, 0)
        self.pack_start(grid, True, True, 0)
        self.show_all()

    def _on_previous_clicked(self, button):
        """Handle previous month button click."""
        if self.plugin:
            self.plugin._navigate_to_previous()

    def _on_next_clicked(self, button):
        """Handle next month button click."""
        if self.plugin:
            self.plugin._navigate_to_next()

    def _on_key_press(self, widget, event):
        """Handle keyboard navigation for calendar."""
        from gi.repository import Gdk

        keyval = event.keyval

        # Left arrow - previous month
        if keyval == Gdk.KEY_Left:
            if self.plugin:
                self.plugin._navigate_to_previous()
            return True

        # Right arrow - next month
        if keyval == Gdk.KEY_Right:
            if self.plugin:
                self.plugin._navigate_to_next()
            return True

        # Home - go to current month
        if keyval == Gdk.KEY_Home:
            if self.plugin:
                self.plugin._reset_to_current_month()
                self.plugin._force_launcher_refresh()
            return True

        return False

    def update_display(self, month: int, year: int):
        """Update the calendar to show a different month/year."""
        self.display_month = month
        self.display_year = year

        # Update month label
        month_name = calendar.month_name[month]
        self.month_label.set_label(f"{month_name} {year}")

        # Rebuild the calendar grid
        # Find and remove the old grid
        for child in self.get_children():
            if isinstance(child, Gtk.Grid):
                self.remove(child)
                child.destroy()
                break

        # Create new grid (following CSS naming)
        grid = Gtk.Grid(
            name="calendar-grid",
            column_spacing=1,
            row_spacing=1,
            column_homogeneous=True,
            row_homogeneous=True
        )

        # Day headers (following CSS naming)
        day_names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        for i, day_name in enumerate(day_names):
            day_header = Label(
                name="calendar-day-header",
                label=day_name,
                h_align="center"
            )
            grid.attach(day_header, i, 0, 1, 1)

        # Calendar days (following CSS naming)
        cal = calendar.monthcalendar(year, month)
        for week_num, week in enumerate(cal, start=1):
            for day_num, day in enumerate(week):
                if day == 0:
                    # Empty cell (following CSS naming)
                    empty = Label(name="calendar-day-empty", label="")
                    grid.attach(empty, day_num, week_num, 1, 1)
                else:
                    # Day label (following CSS naming)
                    day_label = Label(
                        name="calendar-day-label",
                        label=str(day),
                        h_align="center"
                    )

                    # Highlight today (CSS class)
                    if (day == self.today.day and
                        month == self.today.month and
                        year == self.today.year):
                        day_label.get_style_context().add_class("today")

                    # Highlight weekends (CSS class)
                    if day_num in [6]:  # Saturday and Sunday
                        day_label.get_style_context().add_class("weekend")

                    grid.attach(day_label, day_num, week_num, 1, 1)

        # Add new grid
        self.pack_start(grid, True, True, 0)
        grid.show_all()


class CalendarPlugin(PluginBase):
    """
    Calendar plugin for the launcher.
    Simple text-based calendar with working Enter key navigation.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Calendar"
        self.description = "Calendar with visual dates and navigation buttons"
        self._current_widget = None
        # Current display state
        self._current_month = None
        self._current_year = None

    def initialize(self):
        """Initialize the Calendar plugin."""
        self.set_triggers(["cal", "cal "])
        self.description = "Calendar with visual dates and navigation. Use ← → arrows for months, Home for current month"

    def cleanup(self):
        """Cleanup the Calendar plugin."""
        if self._current_widget:
            if self._current_widget.get_parent():
                self._current_widget.get_parent().remove(self._current_widget)
            self._current_widget.destroy()
            self._current_widget = None
        # Reset to current month when cleaning up
        self._reset_to_current_month()

    def query(self, query_string: str) -> List[Result]:
        """Process Calendar queries."""
        results = []
        query = query_string.strip().lower()
        today = datetime.date.today()

        # Handle date queries
        if query in ["today", "now"]:
            date_str = today.strftime("%A, %B %d, %Y")
            results.append(
                Result(
                    title=date_str,
                    subtitle="Today's date • Click to copy",
                    icon_markup=icons.calendar,
                    action=lambda: self._copy_to_clipboard(date_str),
                    relevance=1.0,
                    plugin_name=self.display_name
                )
            )
            return results

        elif query == "tomorrow":
            tomorrow = today + datetime.timedelta(days=1)
            date_str = tomorrow.strftime("%A, %B %d, %Y")
            results.append(
                Result(
                    title=date_str,
                    subtitle="Tomorrow's date • Click to copy",
                    icon_markup=icons.calendar,
                    action=lambda: self._copy_to_clipboard(date_str),
                    relevance=1.0,
                    plugin_name=self.display_name
                )
            )
            return results

        elif query == "yesterday":
            yesterday = today - datetime.timedelta(days=1)
            date_str = yesterday.strftime("%A, %B %d, %Y")
            results.append(
                Result(
                    title=date_str,
                    subtitle="Yesterday's date • Click to copy",
                    icon_markup=icons.calendar,
                    action=lambda: self._copy_to_clipboard(date_str),
                    relevance=1.0,
                    plugin_name=self.display_name
                )
            )
            return results

        # Clean up previous widget
        self.cleanup()

        # Check if we should reset to current month
        # This happens when the query is empty or just the trigger
        if not query or query in ["", "cal"]:
            self._reset_to_current_month()

        # Determine which month to show
        if self._current_month is None:
            # First time - show current month
            display_month = today.month
            display_year = today.year
        else:
            # Use stored month/year
            display_month = self._current_month
            display_year = self._current_year

        # Update stored state
        self._current_month = display_month
        self._current_year = display_year

        # Create calendar widget with navigation buttons
        calendar_widget = CalendarWidget(display_month, display_year, self)
        self._current_widget = calendar_widget

        month_name = calendar.month_name[display_month]
        results.append(
            Result(
                title=f"Calendar - {month_name} {display_year}",
                subtitle="← → navigate months, Home for current month",
                icon_markup=icons.calendar,
                action=lambda: None,
                relevance=1.0,
                plugin_name=self.display_name,
                custom_widget=calendar_widget,
                data={"type": "calendar_display"}
            )
        )

        return results

    def _navigate_to_next(self):
        """Navigate to next month (called by button click)."""
        if self._current_month and self._current_year:
            next_month, next_year = self._advance_month(self._current_month, self._current_year, 1)
            self._current_month = next_month
            self._current_year = next_year

            # Update the calendar widget display
            if self._current_widget:
                self._current_widget.update_display(next_month, next_year)

    def _navigate_to_previous(self):
        """Navigate to previous month (called by button click)."""
        if self._current_month and self._current_year:
            prev_month, prev_year = self._advance_month(self._current_month, self._current_year, -1)
            self._current_month = prev_month
            self._current_year = prev_year

            # Update the calendar widget display
            if self._current_widget:
                self._current_widget.update_display(prev_month, prev_year)

    def _advance_month(self, month: int, year: int, direction: int) -> tuple[int, int]:
        """Advance month by direction (1 for next, -1 for previous)."""
        if direction > 0:  # Next
            if month == 12:
                return 1, year + 1
            else:
                return month + 1, year
        else:  # Previous
            if month == 1:
                return 12, year - 1
            else:
                return month - 1, year

    def _reset_to_current_month(self):
        """Reset calendar to current month."""
        today = datetime.date.today()
        self._current_month = today.month
        self._current_year = today.year

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        try:
            import subprocess
            subprocess.run(["wl-copy"], input=text.encode(), check=True)
            print(f"Copied to clipboard: {text}")
        except subprocess.CalledProcessError:
            print(f"Failed to copy to clipboard: {text}")
