import calendar
import datetime
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import httpx
import psutil
from fabric.core.service import Service, Signal
from fabric.utils import GLib, invoke_repeater, logger, time
from fabric.widgets.box import Box
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.datetime import DateTime
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.wayland import WaylandWindow as Window

from services.config import on_config_change
from shared.data import load_config
from utils.gtk_utils import svg_file
from window.desktop.constants import (
    CALENDAR_UPDATE_INTERVAL,
    LOCATION_APIS,
    SYSTEM_UPDATE_INTERVAL,
    WEATHER_CACHE_TIMEOUT,
    WEATHER_DESC_MAP,
    WEATHER_GRADIENT_MAP,
    WEATHER_ICON_MAP,
    WEATHER_UPDATE_INTERVAL,
)

# Icons that have a dedicated -night SVG variant.
_NIGHT_VARIANT_ICONS = frozenset(
    (
        "weather-clear",
        "weather-clouds",
        "weather-few-clouds",
        "weather-overcast",
        "weather-showers",
        "weather-showers-scattered",
        "weather-snow",
        "weather-snow-scattered",
        "weather-storm",
    )
)

_HTTP_HEADERS = {"User-Agent": "Modus-Desktop/1.0"}


class WeatherService(Service):
    """Owns HTTP, caching, coordinate lookup and update scheduling for the
    weather widget. Networking runs on a single background worker; results are
    delivered back to the GLib main loop through the ``updated`` signal.

    This is an app-lifetime singleton: its executor, client and timer are never
    torn down. Widgets observe it by connecting to ``updated`` and disconnect on
    destroy, so the service survives widget rebuilds (config reloads, etc.)."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def get_initial():
        if WeatherService._instance is None:
            WeatherService._instance = WeatherService()
        return WeatherService._instance

    @Signal
    def updated(self, weather_info: object) -> None:
        """Emitted on the main loop with fresh weather data (or None on failure)."""

    def __init__(self, **kwargs):
        if getattr(self, "_initialized", False):
            return
        super().__init__(**kwargs)
        self._initialized = True
        self._http = httpx.Client(
            timeout=3.0, follow_redirects=True, headers=_HTTP_HEADERS
        )
        self._executor = ThreadPoolExecutor(max_workers=1)

        # This shell shows one location at a time, so caches hold single values.
        self._weather: Optional[List[str]] = None
        self._weather_ts: float = 0.0
        self._location: Optional[str] = None
        self._coords: Optional[Tuple[float, float]] = None
        self._coords_location: Optional[str] = None

        # Periodic refresh only; widgets request the first fetch after
        # connecting (see Weather.__init__) to avoid a race with subscription.
        GLib.timeout_add_seconds(WEATHER_UPDATE_INTERVAL, self._refresh)

        on_config_change(self._on_config_change)

    def _on_config_change(self, new_config, old_config):
        if new_config.get("weather_location") != old_config.get("weather_location"):
            self._weather = None
            self._location = None
            self._coords = None
            self._coords_location = None
            self._executor.submit(self._fetch)

    # -- scheduling -------------------------------------------------------

    def refresh(self) -> None:
        """Trigger an immediate fetch (e.g. when a widget subscribes)."""
        self._executor.submit(self._fetch)

    def _refresh(self) -> bool:
        self._executor.submit(self._fetch)
        return True

    # -- networking -------------------------------------------------------

    def _get_json(self, url: str, timeout: float) -> Optional[Dict[str, Any]]:
        try:
            resp = self._http.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.error(f"HTTP request to {url} failed: {e}")
        return None

    def _get_location(self) -> str:
        try:
            manual_location = load_config().get("weather_location")
            if manual_location:
                return manual_location
        except Exception as e:
            logger.error(f"An error occurred: {e}")

        for api_url in LOCATION_APIS:
            data = self._get_json(api_url, 2.0)
            if data:
                city = data.get("city", "")
                if city:
                    return city

        logger.warning("All location APIs failed")
        return ""

    def _get_coordinates(self, city: str) -> Optional[Tuple[float, float]]:
        # Only query Nominatim when the location is new or unknown.
        if self._coords is not None and self._coords_location == city:
            return self._coords

        encoded_city = urllib.parse.quote(city)
        url = (
            "https://nominatim.openstreetmap.org/search?"
            f"q={encoded_city}&format=json&limit=1"
        )
        data = self._get_json(url, 3.0)
        if isinstance(data, list) and data:
            try:
                coords = (float(data[0]["lat"]), float(data[0]["lon"]))
            except (ValueError, KeyError) as e:
                logger.warning(
                    f"[widget] coords = (float(data[0]['lat']), float(data[0]['lon'])) failed: {e}"
                )
                return None
            self._coords = coords
            self._coords_location = city
            return coords
        return None

    def _get_weather_data(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            "&current_weather=true"
            "&daily=temperature_2m_max,temperature_2m_min"
            "&timezone=auto"
            "&forecast_days=1"
        )
        return self._get_json(url, 3.0)

    # -- background fetch (runs on the worker thread) ---------------------

    def _fetch(self) -> None:
        location = self._get_location()
        if not location:
            return GLib.idle_add(self._deliver, None)

        cache_key = location.lower()
        now = time.time()
        if (
            self._weather is not None
            and self._location == cache_key
            and now - self._weather_ts < WEATHER_CACHE_TIMEOUT
        ):
            return GLib.idle_add(self._deliver, self._weather)

        coords = self._get_coordinates(location)
        if not coords:
            return GLib.idle_add(self._deliver, None)

        weather_data = self._get_weather_data(*coords)
        if not weather_data:
            return GLib.idle_add(self._deliver, None)

        formatted = _format_weather_data(weather_data, location)
        if formatted:
            self._weather = formatted
            self._location = cache_key
            self._weather_ts = now
            GLib.idle_add(self._deliver, formatted)
        else:
            GLib.idle_add(self._deliver, None)
        return None

    def _deliver(self, weather_info: Optional[List[str]]) -> None:
        self.emit("updated", weather_info)


def _format_weather_data(
    weather_data: Dict[str, Any], city: str
) -> Optional[List[str]]:
    """Format weather data into the list consumed by the widget."""
    try:
        current = weather_data["current_weather"]
        daily = weather_data["daily"]

        weather_code = current["weathercode"]
        is_day = current.get("is_day", 1)  # Default to day if missing

        base_icon = WEATHER_ICON_MAP.get(weather_code, "weather-none-available")
        icon_name = base_icon
        if not is_day and base_icon in _NIGHT_VARIANT_ICONS:
            icon_name = f"{base_icon}-night"

        condition = WEATHER_DESC_MAP.get(weather_code, "Unknown")
        gradient_class = WEATHER_GRADIENT_MAP.get(weather_code, "weather-clear")

        temp = f"{round(current['temperature'])}°"
        max_temp = f"{round(daily['temperature_2m_max'][0])}°"
        min_temp = f"{round(daily['temperature_2m_min'][0])}°"

        return [icon_name, temp, condition, city, max_temp, min_temp, gradient_class]
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Error formatting weather data: {e}")
        return None


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
        self._create_labels()
        self._layout_labels()
        self._service = WeatherService.get_initial()
        self._service.connect("updated", self._on_service_update)
        self._service.refresh()

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

    def _on_service_update(self, _service, weather_info):
        if weather_info:
            self.weatherinfo = weather_info
            self.update_labels(weather_info)

    def destroy(self):
        """Disconnect from the weather service (the service is app-lifetime)."""
        try:
            self._service.disconnect_by_func(self._on_service_update)
        except ValueError as e:
            logger.warning(
                f"[widget] self._service.disconnect_by_func(self._on_service_update) failed: {e}"
            )
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
        from utils.functions import clear_children

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
            logger.error(f"Error: {e}")
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
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        return None

    def update(self) -> bool:
        try:
            cpu = psutil.cpu_percent()
            self.main_label.set_label(f" {round(cpu):<2} %\nCPU")
            temp = self.get_cpu_temp()
            self.temp_value.set_label(f"{temp}°C" if temp else "N/A")
            GLib.idle_add(self.progress.set_value, cpu)
        except Exception as e:
            logger.error(f"Error: {e}")
        return True


class Deskwidgets:
    """Desktop widgets manager - handles all desktop widgets."""

    config = load_config()

    def __init__(self):
        # This class now just manages other windows instead of being one itself

        # Create separate independent windows as attributes
        self.top_left = Window(
            anchor="top left",
            title="modus-widgets",
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
            title="modus-widgets",
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
