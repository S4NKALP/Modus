import calendar
import datetime
import urllib.parse
import httpx
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import psutil
from fabric.utils import GLib, invoke_repeater, time
from fabric.widgets.box import Box
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.datetime import DateTime
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.wayland import WaylandWindow as Window

from shared.data import load_config
from utils.debounce import sync_debounce
from utils.utils import svg_file
from window.desktop.constants import (
    CALENDAR_UPDATE_INTERVAL,
    LOCATION_APIS,
    LOCATION_CACHE_TIMEOUT,
    SYSTEM_UPDATE_INTERVAL,
    WEATHER_CACHE_TIMEOUT,
    WEATHER_DESC_MAP,
    WEATHER_GRADIENT_MAP,
    WEATHER_ICON_MAP,
    WEATHER_UPDATE_INTERVAL,
)

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=4)

# Global cache for weather data
_weather_cache: Dict[str, Tuple[Any, float]] = {}
_location_cache: Dict[str, Tuple[float, float, float]] = {}


def http_get_json(
    url: str, timeout: int = 3, headers: Optional[Dict] = None
) -> Optional[Dict]:
    """Helper to perform GET requests and return JSON using httpx."""
    try:
        # Some APIs require a User-Agent or they will return 403 Forbidden
        default_headers = {"User-Agent": "Modus-Desktop/1.0"}
        if headers:
            default_headers.update(headers)
        response = httpx.get(
            url, headers=default_headers, timeout=timeout, follow_redirects=True
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"HTTP Request to {url} failed: {e}")
    return None


def get_location() -> str:
    """Get current location from config or multiple IP geolocation APIs with fallback."""
    # Try to get location from config first
    try:
        config = load_config()
        manual_location = config.get("weather_location")
        if manual_location:
            return manual_location
    except Exception:
        pass

    # Fallback to IP geolocation APIs
    for api_url in LOCATION_APIS:
        data = http_get_json(api_url, timeout=2)
        if data:
            city = data.get("city", "")
            if city:
                return city

    print("All location APIs failed")
    return ""


def get_coordinates(city: str) -> Optional[Tuple[float, float]]:
    """Get coordinates for a city using Nominatim geocoding API."""
    cache_key = city.lower()
    current_time = time.time()

    if cache_key in _location_cache:
        lat, lon, timestamp = _location_cache[cache_key]
        if current_time - timestamp < LOCATION_CACHE_TIMEOUT:
            return lat, lon

    encoded_city = urllib.parse.quote(city)
    url = f"https://nominatim.openstreetmap.org/search?q={encoded_city}&format=json&limit=1"

    data = http_get_json(url, timeout=3, headers={"User-Agent": "Modus-Desktop/1.0"})

    if data and isinstance(data, list) and len(data) > 0:
        try:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            _location_cache[cache_key] = (lat, lon, current_time)
            return lat, lon
        except (ValueError, KeyError):
            pass

    return None


def get_weather_data(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Fetch weather data from Open-Meteo API."""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current_weather=true"
        f"&daily=temperature_2m_max,temperature_2m_min"
        f"&timezone=auto"
        f"&forecast_days=1"
    )
    return http_get_json(url, timeout=3)


def format_weather_data(weather_data: Dict[str, Any], city: str) -> List[str]:
    """Format weather data into the expected format."""
    try:
        current = weather_data["current_weather"]
        daily = weather_data["daily"]

        weather_code = current["weathercode"]
        is_day = current.get("is_day", 1)  # Default to day if missing

        base_icon = WEATHER_ICON_MAP.get(weather_code, "weather-none-available")

        # Determine day/night variant if applicable
        icon_name = base_icon
        if not is_day:
            night_variant = f"{base_icon}-night"

            # Fast check if night variant exists using predefined list or checking the path
            # Since we know the variants from earlier, let's just optimistically build it
            # then logic in svg_file will handle resolution seamlessly (fallbacks can be tricky, but we assume it's correct)
            if base_icon in [
                "weather-clear",
                "weather-clouds",
                "weather-few-clouds",
                "weather-overcast",
                "weather-showers",
                "weather-showers-scattered",
                "weather-snow",
                "weather-snow-scattered",
                "weather-storm",
            ]:
                icon_name = night_variant

        condition = WEATHER_DESC_MAP.get(weather_code, "Unknown")
        gradient_class = WEATHER_GRADIENT_MAP.get(weather_code, "weather-clear")

        temp = f"{round(current['temperature'])}°"
        max_temp = f"{round(daily['temperature_2m_max'][0])}°"
        min_temp = f"{round(daily['temperature_2m_min'][0])}°"

        return [icon_name, temp, condition, city, max_temp, min_temp, gradient_class]
    except (KeyError, IndexError, TypeError) as e:
        print(f"Error formatting weather data: {e}")
        return None


def get_weather(callback):
    """Fetch weather data asynchronously."""

    def fetch_weather():
        location = get_location()
        if not location:
            return GLib.idle_add(callback, None)

        cache_key = location.lower()
        current_time = time.time()

        if cache_key in _weather_cache:
            cached_data, timestamp = _weather_cache[cache_key]
            if current_time - timestamp < WEATHER_CACHE_TIMEOUT:
                return GLib.idle_add(callback, cached_data)

        coords = get_coordinates(location)
        if not coords:
            return GLib.idle_add(callback, None)

        lat, lon = coords
        weather_data = get_weather_data(lat, lon)
        if not weather_data:
            return GLib.idle_add(callback, None)

        formatted_data = format_weather_data(weather_data, location)
        if formatted_data:
            _weather_cache[cache_key] = (formatted_data, current_time)
            GLib.idle_add(callback, formatted_data)
        else:
            GLib.idle_add(callback, None)

    executor.submit(fetch_weather)


def update_weather(widget):
    """Update weather widget with new data."""

    def perform_fetch():
        get_weather(lambda weather_info: update_widget(widget, weather_info))

    debounced_perform_fetch = sync_debounce(1000, immediate=True)(perform_fetch)

    def fetch_and_update():
        debounced_perform_fetch()
        return True

    def initial_fetch():
        debounced_perform_fetch()
        return False

    # Trigger first fetch immediately - MUST return False to not loop in idle
    GLib.idle_add(initial_fetch)

    return GLib.timeout_add_seconds(WEATHER_UPDATE_INTERVAL, fetch_and_update)


def update_widget(widget, weather_info):
    """Update widget labels with weather information."""
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
        self.weatherinfo = None
        self._weather_timer_id = None
        self._create_labels()
        self._layout_labels()
        self._weather_timer_id = update_weather(self)

    def _create_labels(self):
        self.header = Box(orientation="h", h_expand=True)
        self.body = Box(orientation="v", v_expand=True, valign="end")

        self.city = Label(
            name="city",
            label="Loading...",
            justification="left",
            h_align="start",
            max_chars_width=15,
            ellipsization="end",
        )
        self.temperature = Label(name="temperature", label="--°", h_align="start")
        self.condition_em = svg_file(
            "weather/weather-none-available.svg", size=(35, 35), name="condition-emoji"
        )
        self.condition = Label(
            name="condition",
            label="Loading...",
            max_chars_width=18,
            ellipsization="end",
            h_align="start",
        )
        self.feels_like = Label(name="feels-like", label="L:-- H:--", h_align="start")

    def _layout_labels(self):
        # Header: City (left) and Icon (right)
        self.header.add(self.city)
        self.header.pack_end(self.condition_em, False, False, 0)

        # Body: Temp, Condition, High/Low
        self.body.add(self.temperature)
        self.body.add(self.condition)
        self.body.add(self.feels_like)

        self.add(self.header)
        self.add(self.body)

    def update_labels(self, weather_info: List[str]):
        if not weather_info or len(weather_info) != 7:
            return
        icon_name, temp, condition, location, maxtemp, mintemp, gradient_class = (
            weather_info
        )
        maxmin = f"L:{mintemp} H:{maxtemp}"

        self.city.set_label(location)
        self.temperature.set_label(temp)

        # update SVG File
        self.condition_em.dynamic_file(f"weather/{icon_name}.svg")

        self.condition.set_label(condition)
        self.feels_like.set_label(maxmin)

        # Apply gradient class to container
        if hasattr(self, "parent") and self.parent:
            # Remove old weather classes
            for cls in self.parent.get_style_context().list_classes():
                if cls.startswith("weather-"):
                    self.parent.remove_style_class(cls)
            # Add new one
            self.parent.add_style_class(gradient_class)

        self.parent.set_visible(True)

    def destroy(self):
        """Cleanup weather update timer"""
        if self._weather_timer_id:
            GLib.source_remove(self._weather_timer_id)
            self._weather_timer_id = None
        super().destroy()


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
            children=[Weather(self)],
            **kwargs,
        )


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
        date_interval = 10000
        self.dateone = DateTime(formatters=["%a"], interval=date_interval, name="day")
        self.datetwo = DateTime(formatters=["%b"], interval=date_interval, name="month")
        self.datethree = DateTime(
            formatters=["%-d"], interval=date_interval, name="date"
        )
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
        for child in self.calendar_grid.get_children():
            self.calendar_grid.remove(child)
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


class SystemInfoBase(Box):
    @staticmethod
    def create_progress_bar(name: str = "progress-bar", size: int = 80, **kwargs):
        return CircularProgressBar(
            name=name,
            start_angle=270,
            end_angle=630,
            min_value=0,
            max_value=100,
            size=size,
            **kwargs,
        )

    def __init__(self, name: str, **kwargs):
        super().__init__(
            layer="bottom",
            title="sysinfo",
            name=name,
            visible=True,
            size=(170, 170),
            h_expand=True,
            v_expand=True,
            all_visible=True,
            **kwargs,
        )
        self.progress = self.create_progress_bar(name="progress")
        self.main_label = Label(
            label="0%\nLoading", justification="center", name="progress-label"
        )
        self.info_container = Box(
            name="info-container", orientation="v", spacing=2, h_align="center"
        )
        self.add(
            Box(
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
                                child=self.progress,
                                tooltip_text="",
                                overlays=self.main_label,
                            )
                        ]
                    ),
                    Box(
                        h_align="center",
                        justification="centre",
                        orientation="v",
                        children=[self.info_container],
                    ),
                ],
            )
        )

    def start_updates(self):
        self._system_timer_id = invoke_repeater(SYSTEM_UPDATE_INTERVAL, self.update)

    def destroy(self):
        """Cleanup system info update timer"""
        if hasattr(self, "_system_timer_id") and self._system_timer_id:
            GLib.source_remove(self._system_timer_id)
            self._system_timer_id = None
        super().destroy()

    def create_info_line(
        self, indicator_name: str, info_text: str, value_text: str
    ) -> Box:
        line = Box(
            orientation="h",
            spacing=4,
            h_align="start",
            children=[
                Label(label="■", name=indicator_name),
                Label(label=info_text, name="info-text"),
                Label(label=value_text, name="info-value"),
            ],
        )
        line.value_label = line.get_children()[2]
        return line

    def update(self) -> bool:
        raise NotImplementedError


class RamInfo(SystemInfoBase):
    def __init__(self, **kwargs):
        super().__init__("info-box-widget", **kwargs)
        self.used_line = self.create_info_line("used-color-indicator", "Used", "0.0GB")
        self.free_line = self.create_info_line("free-color-indicator", "Free", "0.0GB")
        self.info_container.add(self.used_line)
        self.info_container.add(self.free_line)
        self.start_updates()

    def update(self) -> bool:
        try:
            mem = psutil.virtual_memory()
            self.main_label.set_label(f" {round(mem.percent):<2} %\nRAM")
            self.used_line.value_label.set_label(f"{round(mem.used / (1024**3), 1)}GB")
            self.free_line.value_label.set_label(
                f"{round(mem.available / (1024**3), 1)}GB"
            )
            GLib.idle_add(self.progress.set_value, mem.percent)
        except Exception as e:
            print(f"Error: {e}")
        return True


class CpuInfo(SystemInfoBase):
    def __init__(self, **kwargs):
        super().__init__("info-box-widget", **kwargs)
        self.temp_value = Label(label="0°C", name="info-value")
        self.info_container.add(
            Box(
                orientation="h",
                spacing=4,
                h_align="start",
                children=[Label(label="Temp", name="info-text"), self.temp_value],
            )
        )
        self.start_updates()

    def get_cpu_temp(self) -> Optional[float]:
        try:
            temps = psutil.sensors_temperatures()
            for name, entries in temps.items():
                if any(s in name.lower() for s in ["coretemp", "k10temp", "cpu"]):
                    for entry in entries:
                        if any(
                            p in (entry.label or "").lower()
                            for p in ["package id 0", "core 0", ""]
                        ):
                            return round(entry.current, 1)
        except Exception:
            pass
        return None

    def update(self) -> bool:
        try:
            cpu = psutil.cpu_percent()
            self.main_label.set_label(f" {round(cpu):<2} %\nCPU")
            temp = self.get_cpu_temp()
            self.temp_value.set_label(f"{temp}°C" if temp else "N/A")
            GLib.idle_add(self.progress.set_value, cpu)
        except Exception as e:
            print(f"Error: {e}")
        return True


class Deskwidgets:
    """Desktop widgets manager - handles all desktop widgets."""

    config = load_config()

    def __init__(self):
        # This class now just manages other windows instead of being one itself

        # Create separate independent windows as attributes
        self.top_left = Window(
            anchor="top left",
            title="modus-widgets-topleft",
            exclusivity="none",
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

        self.bottom_left = Window(
            anchor="bottom right",
            title="modus-widgets-bottomright",
            orientation="h",
            layer="bottom",
            exclusivity="none",
            visible=False,  # Start hidden until content ready
            child=Box(
                name="desktop-widgets-container",
                children=[
                    CpuInfo(),
                    RamInfo(),
                ],
            ),
        )

        # Show widgets after initialization is complete
        self.top_left.set_visible(True)
        self.bottom_left.set_visible(True)
