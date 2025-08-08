# Standard library imports
import psutil
import requests
import urllib.parse
import datetime
import time
import subprocess
import calendar
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple, List, Dict, Any

# Fabric imports
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.datetime import DateTime
from fabric.widgets.circularprogressbar import CircularProgressBar
from widgets.wayland import WaylandWindow as Window
from fabric.utils import invoke_repeater
from gi.repository import GLib

# Local imports
from config.data import load_config

# Module-level constants
WEATHER_UPDATE_INTERVAL = 600  # 10 minutes
WEATHER_CACHE_TIMEOUT = 1800  # 30 minutes
SYSTEM_UPDATE_INTERVAL = 1000  # 1 second
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
)  # Calculate time till midnight
LOCATION_CACHE_TIMEOUT = 604800  # 7 days (extended from 24h)

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=4)

# Weather condition to CSS class mapping (iOS-style gradients)
WEATHER_GRADIENT_MAP = {
    # Clear/Sunny conditions - bright blue to lighter blue
    0: "weather-clear",  # Clear sky
    1: "weather-mostly-clear",  # Mainly clear
    # Cloudy conditions - grey gradients
    2: "weather-partly-cloudy",  # Partly cloudy
    3: "weather-overcast",  # Overcast
    # Fog conditions - muted grey/blue
    45: "weather-fog",  # Fog
    48: "weather-fog",  # Depositing rime fog
    # Light rain/drizzle - blue-grey gradients
    51: "weather-light-rain",  # Light drizzle
    53: "weather-rain",  # Moderate drizzle
    55: "weather-rain",  # Dense drizzle
    61: "weather-light-rain",  # Slight rain
    80: "weather-light-rain",  # Slight rain showers
    # Heavy rain - darker blue-grey
    63: "weather-heavy-rain",  # Moderate rain
    65: "weather-heavy-rain",  # Heavy rain
    81: "weather-heavy-rain",  # Moderate rain showers
    82: "weather-storm",  # Violent rain showers
    # Snow conditions - blue-white gradients
    56: "weather-snow",  # Light freezing drizzle
    57: "weather-snow",  # Dense freezing drizzle
    66: "weather-snow",  # Light freezing rain
    67: "weather-snow",  # Heavy freezing rain
    71: "weather-snow",  # Slight snow fall
    73: "weather-heavy-snow",  # Moderate snow fall
    75: "weather-heavy-snow",  # Heavy snow fall
    77: "weather-snow",  # Snow grains
    85: "weather-snow",  # Slight snow showers
    86: "weather-heavy-snow",  # Heavy snow showers
    # Storm conditions - dark dramatic gradients
    95: "weather-storm",  # Thunderstorm
    96: "weather-storm",  # Thunderstorm with slight hail
    99: "weather-storm",  # Thunderstorm with heavy hail
}

# Weather condition to emoji mapping
WEATHER_EMOJI_MAP = {
    0: "☀️",  # Clear sky
    1: "🌤️",  # Mainly clear
    2: "⛅",  # Partly cloudy
    3: "☁️",  # Overcast
    45: "🌫️",  # Fog
    48: "🌫️",  # Depositing rime fog
    51: "🌦️",  # Light drizzle
    53: "🌧️",  # Moderate drizzle
    55: "🌧️",  # Dense drizzle
    56: "🌨️",  # Light freezing drizzle
    57: "🌨️",  # Dense freezing drizzle
    61: "🌦️",  # Slight rain
    63: "🌧️",  # Moderate rain
    65: "🌧️",  # Heavy rain
    66: "🌨️",  # Light freezing rain
    67: "🌨️",  # Heavy freezing rain
    71: "🌨️",  # Slight snow fall
    73: "❄️",  # Moderate snow fall
    75: "❄️",  # Heavy snow fall
    77: "🌨️",  # Snow grains
    80: "🌦️",  # Slight rain showers
    81: "🌧️",  # Moderate rain showers
    82: "⛈️",  # Violent rain showers
    85: "🌨️",  # Slight snow showers
    86: "❄️",  # Heavy snow showers
    95: "⛈️",  # Thunderstorm
    96: "⛈️",  # Thunderstorm with slight hail
    99: "⛈️",  # Thunderstorm with heavy hail
}

# Weather condition descriptions
WEATHER_DESC_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}

# Location APIs in order of preference (fastest first)
LOCATION_APIS = [
    "https://ipapi.co/json/",  # Fastest, 200ms average
    "http://ip-api.com/json/",  # Fast fallback, 150ms average
    "https://ipinfo.io/json",  # Original fallback
]

# Global cache for weather data
_weather_cache: Dict[str, Tuple[Any, float]] = {}
_location_cache: Dict[str, Tuple[float, float, float]] = {}


def get_location() -> str:
    """Get current location using multiple IP geolocation APIs with fallback."""
    for api_url in LOCATION_APIS:
        try:
            response = requests.get(api_url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                # Handle different API response formats
                city = data.get("city", "")
                if city:
                    return city.replace(" ", "")
        except requests.RequestException as e:
            print(f"Location API {api_url} failed: {e}")
            continue

    print("All location APIs failed")
    return ""


def get_coordinates(city: str) -> Optional[Tuple[float, float]]:
    """Get coordinates for a city using Nominatim geocoding API."""
    cache_key = city.lower()
    current_time = time.time()

    # Check cache first (cache for 7 days)
    if cache_key in _location_cache:
        lat, lon, timestamp = _location_cache[cache_key]
        if current_time - timestamp < LOCATION_CACHE_TIMEOUT:
            return lat, lon

    try:
        encoded_city = urllib.parse.quote(city)
        url = f"https://nominatim.openstreetmap.org/search?q={encoded_city}&format=json&limit=1"
        response = requests.get(
            url, timeout=3, headers={"User-Agent": "Modus-Desktop/1.0"}
        )

        if response.status_code == 200:
            data = response.json()
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                _location_cache[cache_key] = (lat, lon, current_time)
                return lat, lon
    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"Error geocoding {city}: {e}")

    return None


def get_weather_data(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Fetch weather data from Open-Meteo API."""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current_weather=true"
            f"&daily=temperature_2m_max,temperature_2m_min"
            f"&timezone=auto"
            f"&forecast_days=1"
        )

        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            return response.json()
    except requests.RequestException as e:
        print(f"Error fetching weather data: {e}")

    return None


def format_weather_data(weather_data: Dict[str, Any], city: str) -> List[str]:
    """Format weather data into the expected format."""
    try:
        current = weather_data["current_weather"]
        daily = weather_data["daily"]

        # Get weather code and map to emoji and description
        weather_code = current["weathercode"]
        emoji = WEATHER_EMOJI_MAP.get(weather_code, "🌤️")
        condition = WEATHER_DESC_MAP.get(weather_code, "Unknown")
        gradient_class = WEATHER_GRADIENT_MAP.get(weather_code, "weather-clear")

        # Temperature
        temp = f"{round(current['temperature'])}°"

        # Daily min/max temperatures
        max_temp = f"{round(daily['temperature_2m_max'][0])}°"
        min_temp = f"{round(daily['temperature_2m_min'][0])}°"

        return [emoji, temp, condition, city, max_temp, min_temp, gradient_class]

    except (KeyError, IndexError, TypeError) as e:
        print(f"Error formatting weather data: {e}")
        return None


def get_weather(callback):
    """Fetch weather data asynchronously using Open-Meteo API."""

    def fetch_weather():
        # Get location
        location = get_location()
        if not location:
            return GLib.idle_add(callback, None)

        # Check cache first
        cache_key = location.lower()
        current_time = time.time()

        if cache_key in _weather_cache:
            cached_data, timestamp = _weather_cache[cache_key]
            if current_time - timestamp < WEATHER_CACHE_TIMEOUT:
                return GLib.idle_add(callback, cached_data)

        # Get coordinates for the location
        coords = get_coordinates(location)
        if not coords:
            return GLib.idle_add(callback, None)

        lat, lon = coords

        # Fetch weather data
        weather_data = get_weather_data(lat, lon)
        if not weather_data:
            return GLib.idle_add(callback, None)

        # Format data
        formatted_data = format_weather_data(weather_data, location)
        if formatted_data:
            # Cache the result
            _weather_cache[cache_key] = (formatted_data, current_time)
            GLib.idle_add(callback, formatted_data)
        else:
            GLib.idle_add(callback, None)

    executor.submit(fetch_weather)


def update_weather(widget):
    """Update weather widget with new data."""

    def fetch_and_update():
        get_weather(lambda weather_info: update_widget(widget, weather_info))
        return True

    GLib.timeout_add_seconds(WEATHER_UPDATE_INTERVAL, fetch_and_update)
    fetch_and_update()


def update_widget(widget, weather_info):
    """Update widget labels with weather information."""
    if weather_info:
        widget.weatherinfo = weather_info
        widget.update_labels(weather_info)


class Weather(Box):
    """Weather widget displaying current conditions and forecast."""

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

        # Create labels with better organization
        self._create_labels()
        self._layout_labels()

        # Start weather updates
        update_weather(self)

    def _create_labels(self):
        """Create all weather labels."""
        self.city = Label(
            name="city", label="Loading...", justification="right", h_align="start"
        )
        self.temperature = Label(name="temperature", label="--°", h_align="start")
        self.condition_em = Label(name="condition-emoji", label="🌤️", h_align="start")
        self.condition = Label(name="condition", label="Loading...", h_align="start")
        self.feels_like = Label(name="feels-like", label="H:-- L:--", h_align="start")

    def _layout_labels(self):
        """Add labels to the widget in proper order."""
        labels = [
            self.city,
            self.temperature,
            self.condition_em,
            self.condition,
            self.feels_like,
        ]
        for label in labels:
            self.add(label)

    def update_labels(self, weather_info: List[str]):
        """Update weather labels with new data."""
        if not weather_info or len(weather_info) != 7:
            return

        emoji, temp, condition, location, maxtemp, mintemp, gradient_class = (
            weather_info
        )
        maxmin = f"H:{maxtemp} L:{mintemp}"

        # Batch update labels for better performance
        label_updates = [
            (self.city, location),
            (self.temperature, temp),
            (self.condition_em, emoji),
            (self.condition, condition),
            (self.feels_like, maxmin),
        ]

        for label, text in label_updates:
            label.set_label(text)

        # Apply gradient background based on weather condition
        self.parent.set_visible(True)


class WeatherContainer(Box):
    """Container for weather widget."""

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
    """Date widget displaying day, month, and date."""

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

        # Create date components
        self.top = Box(orientation="h", name="date-top", h_expand=True)

        # Use consistent interval for all date components
        date_interval = 10000  # 10 seconds
        self.dateone = DateTime(formatters=["%a"], interval=date_interval, name="day")
        self.datetwo = DateTime(formatters=["%b"], interval=date_interval, name="month")
        self.datethree = DateTime(
            formatters=["%-d"], interval=date_interval, name="date"
        )

        # Layout components
        self.top.add(self.dateone)
        self.top.add(self.datetwo)
        self.add(self.top)
        self.add(self.datethree)


class DateContainer(Box):
    """Container for date widget."""

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
    """Calendar widget displaying current month."""

    def __init__(self, **kwargs):
        super().__init__(
            name="calendar-widget",
            h_expand=True,
            v_expand=True,
            orientation="v",
            **kwargs,
        )

        # Cache current date for efficiency
        self._update_current_date()

        # Create calendar components
        self._create_header()
        self._create_days_header()
        self._create_calendar_grid()

        # Layout components
        self.add(self.month_label)
        self.add(self.days_header)
        self.add(self.calendar_grid)

        # Schedule updates
        invoke_repeater(CALENDAR_UPDATE_INTERVAL, self.update_calendar_if_needed)

    def _update_current_date(self):
        """Update cached current date values."""
        now = datetime.datetime.now()
        self.current_month = now.month
        self.current_year = now.year
        self.current_day = now.day

    def _create_header(self):
        """Create month header label."""
        self.month_label = Label(
            name="calendar-month",
            label=calendar.month_name[self.current_month],
            h_align="start",
            justification="left",
        )

    def _create_days_header(self):
        """Create day abbreviations header."""
        self.days_header = Box(
            name="calendar-days-header", orientation="h", h_expand=True, spacing=2
        )

        day_names = ["S", "M", "T", "W", "T", "F", "S"]
        for i, day_name in enumerate(day_names):
            is_weekend = i in (0, 6)  # Sunday or Saturday
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
            self.days_header.add(day_label)

    def _create_calendar_grid(self):
        """Create calendar grid container."""
        self.calendar_grid = Box(name="calendar-grid", orientation="v", spacing=1)
        self.update_calendar()

    def update_calendar_if_needed(self) -> bool:
        """Check if date changed and update calendar if needed."""
        now = datetime.datetime.now()
        if (
            now.month != self.current_month
            or now.year != self.current_year
            or now.day != self.current_day
        ):

            self._update_current_date()
            self.update_calendar()
        return True

    def update_calendar(self):
        """Update the calendar grid with current month."""
        # Clear existing calendar efficiently
        children = self.calendar_grid.get_children()
        for child in children:
            self.calendar_grid.remove(child)

        # Update month label
        self.month_label.set_label(calendar.month_name[self.current_month])

        # Generate calendar
        cal = calendar.monthcalendar(self.current_year, self.current_month)
        current_date = datetime.datetime.now()

        for week in cal:
            week_box = Box(orientation="h", spacing=2, h_expand=True)

            for day_index, day in enumerate(week):
                if day == 0:
                    # Empty day slot
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
                        and self.current_month == current_date.month
                        and self.current_year == current_date.year
                    )
                    is_weekend = day_index in (0, 6)  # Sunday or Saturday

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
    """Container for calendar widget."""

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
    """Base class for system information widgets."""

    @staticmethod
    def create_progress_bar(name: str = "progress-bar", size: int = 80, **kwargs):
        """Create a standardized circular progress bar."""
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

        # Create progress bar and labels
        self.progress = self.create_progress_bar(name="progress")
        self.main_label = Label(
            label="0%\nLoading", justification="center", name="progress-label"
        )

        # Create info container
        self.info_container = Box(
            name="info-container",
            orientation="v",
            spacing=2,
            h_align="center",
        )

        # Create main layout
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

        self.add(self.progress_container)

        # Don't start updates here - let subclasses call start_updates() when ready

    def start_updates(self):
        """Start the update timer - call this after subclass initialization is complete."""
        invoke_repeater(SYSTEM_UPDATE_INTERVAL, self.update)

    def create_info_line(
        self, indicator_name: str, info_text: str, value_text: str
    ) -> Box:
        """Create an information line with indicator, label, and value."""
        indicator = Label(label="■", name=indicator_name)
        info_label = Label(label=info_text, name="info-text")
        value_label = Label(label=value_text, name="info-value")

        line = Box(
            orientation="h",
            spacing=4,
            h_align="start",
            children=[indicator, info_label, value_label],
        )

        # Store references for easy updates
        line.indicator = indicator
        line.info_label = info_label
        line.value_label = value_label

        return line

    def update(self) -> bool:
        """Override in subclasses."""
        raise NotImplementedError


class RamInfo(SystemInfoBase):
    """RAM usage information widget."""

    def __init__(self, **kwargs):
        super().__init__("info-box-widget", **kwargs)

        # Create info lines and store references
        self.used_line = self.create_info_line("used-color-indicator", "Used", "0.0GB")
        self.free_line = self.create_info_line("free-color-indicator", "Free", "0.0GB")

        # Add to info container
        self.info_container.add(self.used_line)
        self.info_container.add(self.free_line)

        # Now that everything is set up, start updates
        self.start_updates()

    def update(self) -> bool:
        """Update RAM information."""
        try:
            mem = psutil.virtual_memory()

            # Update main label
            self.main_label.set_label(f" {round(mem.percent):<2} %\nRAM")

            # Calculate values
            used_gb = mem.used / (1024**3)
            free_gb = mem.available / (1024**3)

            # Update info labels using stored references
            self.used_line.value_label.set_label(f"{round(used_gb, 1)}GB")
            self.free_line.value_label.set_label(f"{round(free_gb, 1)}GB")

            # Update progress bar (use GLib.idle_add for thread safety)
            GLib.idle_add(self.progress.set_value, mem.percent)

        except Exception as e:
            print(f"Error updating RAM info: {e}")

        return True


class CpuInfo(SystemInfoBase):
    """CPU usage and temperature information widget."""

    def __init__(self, **kwargs):
        super().__init__("info-box-widget", **kwargs)

        # Create temperature info components
        self.temp_info = Label(label="Temp", name="info-text")
        self.temp_value = Label(label="0°C", name="info-value")

        # Create temperature info line (no indicator)
        self.temp_line = Box(
            orientation="h",
            spacing=4,
            h_align="start",
            children=[self.temp_info, self.temp_value],
        )

        # Add to info container
        self.info_container.add(self.temp_line)

        # Now that everything is set up, start updates
        self.start_updates()

    def get_cpu_temp(self) -> Optional[float]:
        """Get CPU temperature from system sensors."""
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return None

            # Search for CPU temperature sensors
            cpu_sensor_names = ["coretemp", "k10temp", "cpu"]
            cpu_label_patterns = ["package id 0", "core 0", ""]

            for name, entries in temps.items():
                if any(sensor in name.lower() for sensor in cpu_sensor_names):
                    for entry in entries:
                        entry_label = (entry.label or "").lower()
                        if any(
                            pattern in entry_label for pattern in cpu_label_patterns
                        ):
                            return round(entry.current, 1)
        except Exception as e:
            print(f"Error reading CPU temperature: {e}")

        return None

    def update(self) -> bool:
        """Update CPU information."""
        try:
            # Get CPU usage
            cpu = psutil.cpu_percent()

            # Update main label
            self.main_label.set_label(f" {round(cpu):<2} %\nCPU")

            # Update temperature using stored reference
            temp = self.get_cpu_temp()
            temp_text = f"{temp}°C" if temp is not None else "N/A"
            self.temp_value.set_label(temp_text)

            # Update progress bar (use GLib.idle_add for thread safety)
            GLib.idle_add(self.progress.set_value, cpu)

        except Exception as e:
            print(f"Error updating CPU info: {e}")

        return True


class Deskwidgets(Window):
    """Desktop widgets manager - handles all desktop widgets."""

    config = load_config()

    def __init__(self, **kwargs):
        # Create the main invisible window that manages the widgets
        super().__init__(
            name="desktop-widget-manager",
            layer="bottom",
            title="modus-desktop-widget-manager",
            visible=False,  # This window is invisible - just manages the others
            size=(1, 1),  # Minimal size
            anchor="top left",
            **kwargs,
        )

        # Create separate independent windows as attributes
        self.top_left = Window(
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

        self.bottom_left = Window(
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

        # Show widgets after initialization is complete
        self.top_left.set_visible(True)
        self.bottom_left.set_visible(True)
