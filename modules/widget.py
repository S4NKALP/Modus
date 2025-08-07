import psutil
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.datetime import DateTime
from fabric.widgets.circularprogressbar import CircularProgressBar
from widgets.wayland import WaylandWindow as Window
from fabric.utils import invoke_repeater
import requests
import urllib.parse
import datetime
from gi.repository import GLib
from concurrent.futures import ThreadPoolExecutor
import time
from config.data import load_config
import subprocess
import calendar

executor = ThreadPoolExecutor(max_workers=4)


def get_location():
    """Fetch location from config file or IP API asynchronously."""
    for attempt in range(5):
        try:
            response = requests.get("https://ipinfo.io/json", timeout=3)
            if response.status_code == 200:
                return response.json().get("city", "").replace(" ", "")
        except requests.RequestException as e:
            print(f"Error getting location: {e}")
            if attempt < 4:
                time.sleep(10)
            else:
                return ""


def get_location_async(callback):
    """Fetch location asynchronously to prevent UI freeze."""
    executor.submit(lambda: GLib.idle_add(callback, get_location()))


def get_weather(callback):
    """Fetch weather data asynchronously and update UI."""

    def fetch_weather():
        location = get_location()
        if not location:
            return GLib.idle_add(callback, None)

        encoded_location = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded_location}?format=j1"
        urlemoji = f"https://wttr.in/{encoded_location}?format=%c"

        for attempt in range(5):
            try:
                response = requests.get(urlemoji, timeout=3)
                responseinfo = requests.get(url, timeout=3).json()

                if response.status_code == 200:
                    temp_unit = "C"
                    temp = (
                        responseinfo["current_condition"][0][f"temp_{temp_unit}"] + "°"
                    )
                    condition = responseinfo["current_condition"][0]["weatherDesc"][0][
                        "value"
                    ]
                    maxtemp = responseinfo["weather"][0]["maxtempC"] + "°"
                    mintemp = responseinfo["weather"][0]["mintempC"] + "°"
                    location = responseinfo["nearest_area"][0]["areaName"][0]["value"]
                    emoji = response.text.strip()

                    GLib.idle_add(
                        callback,
                        [
                            emoji,
                            temp,
                            condition,
                            location,
                            maxtemp,
                            mintemp,
                        ],
                    )
                    return
            except requests.RequestException as e:
                print(f"Error fetching weather (attempt {attempt + 1}): {e}")
                if attempt < 4:
                    time.sleep(10)
                else:
                    GLib.idle_add(callback, None)
                    return

    executor.submit(fetch_weather)


def update_weather(widget):
    def fetch_and_update():
        get_weather(lambda weather_info: update_widget(widget, weather_info))
        return True

    GLib.timeout_add_seconds(600, fetch_and_update)
    fetch_and_update()


def update_widget(widget, weather_info):
    if weather_info:
        widget.weatherinfo = weather_info
        widget.update_labels(weather_info)


class Weather(Box):
    def __init__(self, parent, **kwargs):
        super().__init__(
            name="weather-widget",
            h_expand=True,
            v_expand=True,
            justification="right",
            orientation="v",
            all_visible=False,
            **kwargs,
        )

        self.parent = parent
        self.city = Label(
            name="city", label="New York", justification="right", h_align="start"
        )
        self.temperature = Label(name="temperature", label="36", h_align="start")
        self.condition_em = Label(name="condition-emoji", label="☁️", h_align="start")
        self.condition = Label(name="condition", label="Cloudy", h_align="start")
        self.feels_like = Label(name="feels-like", label="H:28 L:20", h_align="start")
        self.add(self.city)
        self.add(self.temperature)
        self.add(self.condition_em)
        self.add(self.condition)
        self.add(self.feels_like)
        update_weather(self)

    def update_labels(self, weather_info):
        if not self.weatherinfo:
            return

        # Unpack weather info into variables for better readability
        emoji, temp, condition, location, maxtemp, mintemp = self.weatherinfo
        maxmin = f"H:{maxtemp} L:{mintemp}"

        # Store references to deeply nested children to avoid repeated lookups

        self.city.set_label(location)
        self.feels_like.set_label(maxmin)
        self.condition.set_label(condition)
        self.temperature.set_label(temp)
        self.condition_em.set_label(emoji)
        self.parent.set_visible(True)


class WeatherContainer(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            name="weather-container",
            v_expand=True,
            v_align="center",
            size=(170, 170),
            visible=True,
            h_align="center",
            children=[
                Weather(self),
            ],
            **kwargs,
        )
        # TODO: Background Colours according to weather condtions?

        # self.set_style("background-color: rgba(0, 0, 0, 0.5);")
        # self.add(Weather())


class Date(Box):
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
        self.dateone = DateTime(formatters=["%a"], interval=10000, name="day")
        self.datetwo = DateTime(formatters=["%b"], interval=10000, name="month")
        self.datethree = DateTime(formatters=["%-d"], interval=10000, name="date")
        self.top.add(self.dateone)
        self.top.add(self.datetwo)
        self.add(self.top)
        self.add(self.datethree)


class DateContainer(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            name="date-container",
            v_expand=True,
            size=(170, 170),
            v_align="center",
            h_align="center",
            children=[Date()],
            **kwargs,
        )


class Calendar(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="calendar-widget",
            h_expand=True,
            v_expand=True,
            orientation="v",
            **kwargs,
        )

        # Create current date for calendar
        now = datetime.datetime.now()
        self.current_month = now.month
        self.current_year = now.year
        self.current_day = now.day

        # Month and year header
        self.month_label = Label(
            name="calendar-month",
            label=f"{calendar.month_name[self.current_month]}",
            h_align="start",
            justification="left",
        )

        # Day abbreviations
        days_header = Box(
            name="calendar-days-header", orientation="h", h_expand=True, spacing=2
        )

        day_names = ["S", "M", "T", "W", "T", "F", "S"]
        for i, day_name in enumerate(day_names):
            # Saturday (6) and Sunday (0) get weekend styling
            is_weekend = i == 0 or i == 6
            day_label = Label(
                name=(
                    "calendar-day-header-weekend"
                    if is_weekend
                    else "calendar-day-header"
                ),
                label=day_name,
                h_align="center",
                h_expand=True,
            )
            days_header.add(day_label)

        # Calendar grid
        self.calendar_grid = Box(name="calendar-grid", orientation="v", spacing=1)

        self.update_calendar()

        self.add(self.month_label)
        self.add(days_header)
        self.add(self.calendar_grid)

        # Update calendar daily
        invoke_repeater(86400000, self.update_calendar_if_needed)  # 24 hours

    def update_calendar_if_needed(self):
        """Check if date changed and update calendar if needed."""
        now = datetime.datetime.now()
        if (
            now.month != self.current_month
            or now.year != self.current_year
            or now.day != self.current_day
        ):
            self.current_month = now.month
            self.current_year = now.year
            self.current_day = now.day
            self.update_calendar()
        return True

    def update_calendar(self):
        """Update the calendar grid with current month."""
        # Clear existing calendar
        for child in self.calendar_grid.get_children():
            self.calendar_grid.remove(child)

        # Update month label
        self.month_label.set_label(f"{calendar.month_name[self.current_month]}")

        # Get calendar for current month
        cal = calendar.monthcalendar(self.current_year, self.current_month)

        for week in cal:
            week_box = Box(orientation="h", spacing=2, h_expand=True)

            for day_index, day in enumerate(week):
                if day == 0:
                    # Empty day
                    day_label = Label(
                        name="calendar-day-empty",
                        label="",
                        h_align="center",
                        h_expand=True,
                    )
                else:
                    # Regular day
                    is_today = (
                        day == self.current_day
                        and self.current_month == datetime.datetime.now().month
                        and self.current_year == datetime.datetime.now().year
                    )

                    # Saturday (6) and Sunday (0) get weekend styling
                    is_weekend = day_index == 0 or day_index == 6

                    if is_today:
                        name = "calendar-day-today"
                    elif is_weekend:
                        name = "calendar-day-weekend"
                    else:
                        name = "calendar-day"

                    day_label = Label(
                        name=name, label=str(day), h_align="center", h_expand=True
                    )

                week_box.add(day_label)

            self.calendar_grid.add(week_box)


class CalendarContainer(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            name="calendar-box-widget",
            v_expand=True,
            size=(170, 170),
            v_align="center",
            h_align="center",
            children=[Calendar()],
            **kwargs,
        )


class RamInfo(Box):
    @staticmethod
    def bake_progress_bar(name: str = "progress-bar", size: int = 80, **kwargs):
        return CircularProgressBar(
            name=name,
            start_angle=270,
            end_angle=630,
            min_value=0,
            max_value=100,
            size=size,
            **kwargs,
        )

    def __init__(self, **kwargs):
        super().__init__(
            layer="bottom",
            title="sysinfo",
            name="info-box-widget",
            visible=True,
            size=(170, 170),
            h_expand=True,
            v_expand=True,
            all_visible=True,
            **kwargs,
        )

        self.ram_progress = self.bake_progress_bar(name="progress")
        self.ram_label = Label(
            label="15%\nRam", justification="center", name="progress-label"
        )

        # Create info with color indicators
        self.used_indicator = Label(label="■", name="used-color-indicator")
        self.free_indicator = Label(label="■", name="free-color-indicator")

        # Create the info labels
        self.used_info = Label(label="Used", name="info-text")
        self.used_value = Label(label="0.0GB", name="info-value")
        self.free_info = Label(label="Free ", name="info-text")
        self.free_value = Label(label="0.0GB", name="info-value")

        # Create horizontal boxes for each info line
        self.used_line = Box(
            orientation="h",
            spacing=4,
            h_align="start",
            children=[
                self.used_indicator,
                self.used_info,
                self.used_value,
            ],
        )

        self.free_line = Box(
            orientation="h",
            spacing=4,
            h_align="center",
            justification="start",
            children=[
                self.free_indicator,
                self.free_info,
                self.free_value,
            ],
        )

        self.ram_info_container = Box(
            name="info-container",
            orientation="v",
            spacing=2,
            h_align="center",
            children=[
                self.used_line,
                self.free_line,
            ],
        )

        self.progress_container = Box(
            name="progress-bar-container",
            h_expand=True,
            v_expand=True,
            orientation="v",
            spacing=12,
            h_align="center",
            v_align="center",
            children=[
                Box(
                    children=[
                        Overlay(
                            child=self.ram_progress,
                            tooltip_text="",
                            overlays=self.ram_label,
                        ),
                    ],
                ),
                Box(
                    h_align="center",
                    justification="centre",
                    orientation="v",
                    children=[
                        self.ram_info_container,
                    ],
                ),
            ],
        )
        self.add(self.progress_container)
        invoke_repeater(1000, self.update)

    def update(self):
        mem = psutil.virtual_memory()
        self.ram_label.set_label(f" {round(mem.percent):<2} %\nRAM")

        used_gb = mem.used / (1024**3)
        free_gb = mem.available / (1024**3)

        self.used_value.set_label(f"{round(used_gb, 1)}GB")
        self.free_value.set_label(f"{round(free_gb, 1)}GB")

        GLib.idle_add(self.ram_progress.set_value, mem.percent)
        # executor.submit(update)
        return True


class CpuInfo(Box):
    @staticmethod
    def bake_progress_bar(name: str = "progress-bar", size: int = 80, **kwargs):
        return CircularProgressBar(
            name=name,
            start_angle=270,
            end_angle=630,
            min_value=0,
            max_value=100,
            size=size,
            **kwargs,
        )

    def __init__(self, **kwargs):
        super().__init__(
            layer="bottom",
            title="sysinfo",
            name="info-box-widget",
            visible=True,
            size=(170, 170),
            h_expand=True,
            v_expand=True,
            all_visible=True,
            **kwargs,
        )

        self.cpu_progress = self.bake_progress_bar(name="progress")
        self.cpu_label = Label(
            label="15%\nCPU", justification="center", name="progress-label"
        )

        # Create temp info with color indicator
        self.temp_indicator = Label(label="■", name="temp-color-indicator")
        self.temp_info = Label(label="Temp", name="info-text")
        self.temp_value = Label(label="0°C", name="info-value")

        self.temp_line = Box(
            orientation="h",
            spacing=4,
            h_align="start",
            children=[
                # self.temp_indicator,
                self.temp_info,
                self.temp_value,
            ],
        )

        self.cpu_info_container = Box(
            name="info-container",
            orientation="v",
            h_align="center",
            children=[
                self.temp_line,
            ],
        )

        self.progress_container = Box(
            name="progress-bar-container",
            h_expand=True,
            v_expand=True,
            orientation="v",
            spacing=12,
            h_align="center",
            v_align="center",
            children=[
                Box(
                    children=[
                        Overlay(
                            child=self.cpu_progress,
                            tooltip_text="",
                            overlays=self.cpu_label,
                        ),
                    ],
                ),
                Box(
                    h_align="center",
                    justification="centre",
                    orientation="v",
                    children=[
                        self.cpu_info_container,
                    ],
                ),
            ],
        )
        self.add(self.progress_container)
        invoke_repeater(1000, self.update)

    def get_cpu_temp(self):
        temps = psutil.sensors_temperatures()
        if not temps:
            return None

        for name, entries in temps.items():
            if (
                "coretemp" in name.lower()
                or "k10temp" in name.lower()
                or "cpu" in name.lower()
            ):
                for entry in entries:
                    # Match common CPU temp labels
                    if (
                        "package id 0" in (entry.label or "").lower()
                        or "core 0" in (entry.label or "").lower()
                        or (entry.label is None or entry.label.strip() == "")
                    ):
                        return round(entry.current, 1)

        return None

    def update(self):
        cpu = psutil.cpu_percent()
        self.cpu_label.set_label(f" {round(cpu):<2} %\nCPU")

        temp = self.get_cpu_temp()
        if temp is not None:
            self.temp_value.set_label(f"{temp}°C")
        else:
            self.temp_value.set_label("N/A")

        GLib.idle_add(self.cpu_progress.set_value, cpu)
        # executor.submit(update)
        return True


# FIX: GTK ERRORS


class Deskwidgets(Window):
    config = load_config()

    def __init__(self, **kwargs):
        top_left = Window(
            anchor="top left",
            title="modus-widgets-topleft",
            orientation="h",
            layer="bottom",
            visible=False,  # Start hidden until content ready
            child=Box(
                name="desktop-widgets-container",
                children=[
                    DateContainer(),
                    WeatherContainer(),
                    CalendarContainer(),
                ],
            ),
        )

        bottom_left = Window(
            anchor="bottom right",
            title="modus-widgets-bottomright",
            orientation="h",
            layer="bottom",
            visible=False,  # Start hidden until content ready
            child=Box(
                name="desktop-widgets-container",
                children=[
                    CpuInfo(),
                    RamInfo(),
                ],
            ),
        )

        container = Box(
            orientation="v",
            children=[
                top_left,
                bottom_left,
            ],
        )

        super().__init__(
            name="desktop",
            layer="bottom",
            title="modus-desktop-widgets",
            orientation="v",
            exclusivity="none",
            visible=False,  # Start hidden until content ready
            child=container,
            **kwargs,
        )
        
        # Show widgets after initialization is complete
        self.set_visible(True)
        top_left.set_visible(True)
        bottom_left.set_visible(True)
