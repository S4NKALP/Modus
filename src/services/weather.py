import datetime
import json
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from fabric.core.service import Property, Service, Signal
from fabric.utils import GLib, logger

from shared.data import CACHE_DIR

CACHE_DURATION = 600
STALE_CACHE_MAX = 1800
UPDATE_INTERVAL = 600

IP_LOCATION_API = "http://ip-api.com/json/"
WEATHER_API_BASE = "https://api.open-meteo.com/v1/forecast"

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

WEATHER_EMOJI_MAP = {
    0: "☀️",
    1: "🌤️",
    2: "⛅",
    3: "☁️",
    45: "🌫️",
    48: "🌫️",
    51: "🌦️",
    53: "🌧️",
    55: "🌧️",
    56: "🌨️",
    57: "🌨️",
    61: "🌦️",
    63: "🌧️",
    65: "🌧️",
    66: "🌨️",
    67: "🌨️",
    71: "🌨️",
    73: "❄️",
    75: "❄️",
    77: "🌨️",
    80: "🌦️",
    81: "🌧️",
    82: "⛈️",
    85: "🌨️",
    86: "❄️",
    95: "⛈️",
    96: "⛈️",
    99: "⛈️",
}

WEATHER_ICON_MAP = {
    0: "weather-clear",
    1: "weather-few-clouds",
    2: "weather-clouds",
    3: "weather-overcast",
    45: "weather-fog",
    48: "weather-fog",
    51: "weather-showers-scattered",
    53: "weather-showers",
    55: "weather-showers",
    61: "weather-showers-scattered",
    80: "weather-showers-scattered",
    63: "weather-showers",
    65: "weather-showers",
    81: "weather-showers",
    82: "weather-storm",
    56: "weather-freezing-rain",
    57: "weather-freezing-rain",
    66: "weather-freezing-rain",
    67: "weather-freezing-rain",
    71: "weather-snow",
    73: "weather-snow",
    75: "weather-snow",
    77: "weather-hail",
    85: "weather-snow-scattered",
    86: "weather-snow-scattered",
    95: "weather-storm",
    96: "weather-storm",
    99: "weather-storm",
}

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

WEATHER_GRADIENT_MAP = {
    0: "weather-clear",
    1: "weather-mostly-clear",
    2: "weather-partly-cloudy",
    3: "weather-overcast",
    45: "weather-fog",
    48: "weather-fog",
    51: "weather-light-rain",
    53: "weather-rain",
    55: "weather-rain",
    61: "weather-light-rain",
    80: "weather-light-rain",
    63: "weather-heavy-rain",
    65: "weather-heavy-rain",
    81: "weather-heavy-rain",
    82: "weather-storm",
    56: "weather-snow",
    57: "weather-snow",
    66: "weather-snow",
    67: "weather-snow",
    71: "weather-snow",
    73: "weather-heavy-snow",
    75: "weather-heavy-snow",
    77: "weather-snow",
    85: "weather-snow",
    86: "weather-heavy-snow",
    95: "weather-storm",
    96: "weather-storm",
    99: "weather-storm",
}


class Cache:
    def __init__(self, cache_file: Path, max_age: int):
        self._cache_file = cache_file
        self._max_age = max_age
        self._data = None
        self._time = 0
        self._lock = threading.Lock()
        self._load_cache()

    def _load_cache(self):
        try:
            if self._cache_file.exists():
                with self._lock:
                    self._time = self._cache_file.stat().st_mtime
                    self._data = json.loads(self._cache_file.read_text())
        except Exception:
            pass

    def is_fresh(self) -> bool:
        with self._lock:
            return bool(self._data and time.time() - self._time < CACHE_DURATION)

    def is_usable(self) -> bool:
        with self._lock:
            return bool(self._data and time.time() - self._time < self._max_age)

    def get(self, allow_stale=False) -> Optional[dict]:
        if self.is_fresh() or (allow_stale and self.is_usable()):
            with self._lock:
                return self._data.copy() if self._data else None
        return None

    def set(self, data: dict):
        try:
            tmp = self._cache_file.with_suffix(".tmp")
            persist_data = data.copy() if isinstance(data, dict) else data
            if isinstance(persist_data, dict) and "location" in self._cache_file.name:
                persist_data.pop("lat", None)
                persist_data.pop("lon", None)
            tmp.write_text(json.dumps(persist_data, separators=(",", ":")))
            tmp.rename(self._cache_file)
            with self._lock:
                self._data = data
                self._time = time.time()
        except Exception:
            pass


def fetch_api(url: str, timeout: int = 10) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return (
                json.loads(response.read().decode()) if response.status == 200 else None
            )
    except Exception:
        return None


def get_weather_info(code: int, is_day: int = 1) -> Tuple[str, str, str, str]:
    emoji = WEATHER_EMOJI_MAP.get(code, "🌡️")
    icon = WEATHER_ICON_MAP.get(code, "weather-none-available")
    if not is_day and icon in _NIGHT_VARIANT_ICONS:
        icon = f"{icon}-night"
    description = WEATHER_DESC_MAP.get(code, "Unknown")
    gradient = WEATHER_GRADIENT_MAP.get(code, "weather-clear")
    return emoji, icon, description, gradient


def get_wind_direction(degrees: float) -> str:
    dirs = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    return dirs[round(degrees / 22.5) % 16]


class Weather(Service):
    _instance = None

    @classmethod
    def get_default(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @Signal
    def ready(self): ...

    @Property(float, "readable", default_value=0.0)
    def temperature(self) -> float:
        return self._property_helper_temperature

    @Property(float, "readable", default_value=0.0)
    def feels_like(self) -> float:
        return self._property_helper_feels_like

    @Property(int, "readable", default_value=0)
    def humidity(self) -> int:
        return self._property_helper_humidity

    @Property(int, "readable", default_value=0)
    def pressure(self) -> int:
        return self._property_helper_pressure

    @Property(float, "readable", default_value=0.0)
    def wind_speed(self) -> float:
        return self._property_helper_wind_speed

    @Property(str, "readable", default_value="")
    def wind_direction(self) -> str:
        return self._property_helper_wind_direction

    @Property(float, "readable", default_value=0.0)
    def precipitation(self) -> float:
        return self._property_helper_precipitation

    @Property(int, "readable", default_value=0)
    def weather_code(self) -> int:
        return self._property_helper_weather_code

    @Property(str, "readable", default_value="🌡️")
    def weather_emoji(self) -> str:
        return self._property_helper_weather_emoji

    @Property(str, "readable", default_value="cloud-sun-duotone")
    def weather_icon(self) -> str:
        return self._property_helper_weather_icon

    @Property(str, "readable", default_value="weather-clear")
    def weather_gradient(self) -> str:
        return self._property_helper_weather_gradient

    @Property(str, "readable", default_value="Unknown")
    def weather_description(self) -> str:
        return self._property_helper_weather_description

    @Property(str, "readable", default_value="Loading...")
    def location(self) -> str:
        return self._property_helper_location

    @Property(bool, "readable", default_value=True)
    def is_loading(self) -> bool:
        return self._property_helper_is_loading

    @Property(bool, "readable", default_value=False)
    def has_error(self) -> bool:
        return self._property_helper_has_error

    @Property(str, "readable", default_value="")
    def error_message(self) -> str:
        return self._property_helper_error_message

    @Property(object, "readable", default_value=None)
    def hourly_forecast(self) -> list:
        return self._property_helper_hourly_forecast

    @Property(object, "readable", default_value=None)
    def daily_forecast(self) -> list:
        return self._property_helper_daily_forecast

    def __init__(self, **kwargs):

        self._property_helper_temperature = 0.0
        self._property_helper_feels_like = 0.0
        self._property_helper_humidity = 0
        self._property_helper_pressure = 0
        self._property_helper_wind_speed = 0.0
        self._property_helper_wind_direction = ""
        self._property_helper_precipitation = 0.0
        self._property_helper_weather_code = 0
        self._property_helper_weather_emoji = "🌡️"
        self._property_helper_weather_icon = "cloud-sun-duotone"
        self._property_helper_weather_description = "Unknown"
        self._property_helper_weather_gradient = "weather-clear"
        self._property_helper_location = "Loading..."
        self._property_helper_is_loading = True
        self._property_helper_has_error = False
        self._property_helper_error_message = ""
        self._property_helper_hourly_forecast = []
        self._property_helper_daily_forecast = []

        self._weather_cache = Cache(
            Path(CACHE_DIR) / "weather_cache.json", STALE_CACHE_MAX
        )
        self._location_cache = Cache(Path(CACHE_DIR) / "location_cache.json", 24 * 3600)

        super().__init__(**kwargs)

        cached_weather = self._weather_cache.get(allow_stale=True)
        cached_location = self._location_cache.get(allow_stale=True)
        if cached_weather and cached_location:
            self._update_properties(cached_weather, cached_location)

        self._start_fetch_thread()

        GLib.timeout_add_seconds(UPDATE_INTERVAL, self._on_periodic_update)

        from services.config import on_config_change

        on_config_change(self._on_config_changed)

        self.emit("ready")

    def _on_config_changed(self, new_config: dict, old_config: dict) -> None:
        new_general = new_config.get("general", {})
        old_general = old_config.get("general", {})
        if new_general.get("weather_location") != old_general.get("weather_location"):
            self.refresh()

    def _start_fetch_thread(self) -> None:
        thread = threading.Thread(target=self._fetch_weather_data, daemon=True)
        thread.start()

    def _fetch_weather_data(self) -> None:
        try:
            GLib.idle_add(self._set_loading, True)

            location_data = self._location_cache.get()

            from services.config import config

            target_loc = config().get("general.weather_location", "").strip()

            # Invalidate location cache if the config target changed
            if location_data and location_data.get("config_location", "") != target_loc:
                location_data = None
                with self._weather_cache._lock:
                    self._weather_cache._data = None  # Invalidate weather cache

            if not location_data:
                if target_loc:
                    import urllib.parse

                    encoded_loc = urllib.parse.quote(target_loc)
                    geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_loc}&count=1"
                    raw = fetch_api(geocode_url, 10)
                    if not raw or not raw.get("results"):
                        GLib.idle_add(self._set_error, "Location not found")
                        return
                    result = raw["results"][0]
                    location_data = {
                        "lat": round(result["latitude"], 1),
                        "lon": round(result["longitude"], 1),
                        "city": result.get("name", "Unknown"),
                        "country": result.get("country", ""),
                        "config_location": target_loc,
                    }
                else:
                    raw = fetch_api(IP_LOCATION_API, 10)
                    if not raw or raw.get("status") != "success":
                        GLib.idle_add(self._set_error, "Location unavailable")
                        return
                    location_data = {
                        "lat": round(raw["lat"], 1),
                        "lon": round(raw["lon"], 1),
                        "city": raw.get("city", "Unknown"),
                        "country": raw.get("country", ""),
                        "config_location": "",
                    }
                self._location_cache.set(location_data)

            weather_data = self._weather_cache.get()
            if not weather_data:
                lat, lon = location_data["lat"], location_data["lon"]
                params = "&".join(
                    [
                        f"latitude={lat}",
                        f"longitude={lon}",
                        "current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,surface_pressure,wind_speed_10m,wind_direction_10m,is_day",
                        "hourly=temperature_2m,weather_code,precipitation_probability",
                        "daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                        "timezone=auto",
                        "forecast_days=7",
                    ]
                )
                weather_data = fetch_api(f"{WEATHER_API_BASE}?{params}", 15)
                if not weather_data:
                    weather_data = self._weather_cache.get(allow_stale=True)
                    if not weather_data:
                        GLib.idle_add(self._set_error, "Weather unavailable")
                        return
                else:
                    weather_data = {
                        k: v
                        for k, v in weather_data.items()
                        if k not in ("latitude", "longitude")
                    }
                    self._weather_cache.set(weather_data)

            GLib.idle_add(self._update_properties, weather_data, location_data)

        except Exception as e:
            logger.error(f"[WeatherService] Fetch error: {e}")
            GLib.idle_add(self._set_error, str(e))

    def _update_properties(self, weather_data: dict, location_data: dict) -> None:
        try:
            current = weather_data["current"]

            self._property_helper_temperature = current["temperature_2m"]
            self._property_helper_feels_like = current.get(
                "apparent_temperature", current["temperature_2m"]
            )
            self._property_helper_humidity = round(current["relative_humidity_2m"])
            self._property_helper_pressure = round(
                current.get("surface_pressure", 1013)
            )
            self._property_helper_wind_speed = current.get("wind_speed_10m", 0)
            self._property_helper_wind_direction = get_wind_direction(
                current.get("wind_direction_10m", 0)
            )
            self._property_helper_precipitation = current.get("precipitation", 0)
            self._property_helper_weather_code = current["weather_code"]
            is_day = current.get("is_day", 1)

            emoji, icon, description, gradient = get_weather_info(
                self._property_helper_weather_code, is_day
            )
            self._property_helper_weather_emoji = emoji
            self._property_helper_weather_icon = icon
            self._property_helper_weather_description = description
            self._property_helper_weather_gradient = gradient

            city = location_data.get("city", "Unknown")
            country = location_data.get("country", "")
            self._property_helper_location = f"{city}, {country}" if country else city

            self._property_helper_hourly_forecast = self._process_hourly_forecast(
                weather_data.get("hourly", {})
            )
            self._property_helper_daily_forecast = self._process_daily_forecast(
                weather_data.get("daily", {})
            )

            self._property_helper_has_error = False
            self._property_helper_error_message = ""
            self._property_helper_is_loading = False

            for prop in [
                "temperature",
                "feels-like",
                "humidity",
                "pressure",
                "wind-speed",
                "wind-direction",
                "precipitation",
                "weather-code",
                "weather-emoji",
                "weather-icon",
                "weather-description",
                "weather-gradient",
                "location",
                "is-loading",
                "has-error",
                "error-message",
                "hourly-forecast",
                "daily-forecast",
            ]:
                self.notify(prop)

        except Exception as e:
            logger.error(f"[WeatherService] Update error: {e}")
            self._set_error(str(e))

    def _process_hourly_forecast(self, hourly: dict) -> list:
        if not hourly or not hourly.get("time"):
            return []
        forecast = []
        current_hour = datetime.datetime.now().hour
        for i in range(current_hour, min(current_hour + 24, len(hourly["time"]))):
            try:
                forecast.append(
                    {
                        "time": hourly["time"][i],
                        "temperature": hourly["temperature_2m"][i],
                        "weather_code": hourly["weather_code"][i],
                        "precipitation_probability": hourly.get(
                            "precipitation_probability", [0] * len(hourly["time"])
                        )[i],
                    }
                )
            except (IndexError, KeyError):
                continue
        return forecast

    def _process_daily_forecast(self, daily: dict) -> list:
        if not daily or not daily.get("time"):
            return []
        forecast = []
        for i in range(min(7, len(daily["time"]))):
            try:
                forecast.append(
                    {
                        "date": daily["time"][i],
                        "temperature_max": daily["temperature_2m_max"][i],
                        "temperature_min": daily["temperature_2m_min"][i],
                        "weather_code": daily["weather_code"][i],
                        "precipitation": daily.get(
                            "precipitation_sum", [0] * len(daily["time"])
                        )[i],
                    }
                )
            except (IndexError, KeyError):
                continue
        return forecast

    def _set_loading(self, value: bool) -> None:
        self._property_helper_is_loading = value
        self.notify("is-loading")

    def _set_error(self, message: str) -> None:
        self._property_helper_has_error = True
        self._property_helper_error_message = message
        self._property_helper_is_loading = False
        self.notify("has-error")
        self.notify("error-message")
        self.notify("is-loading")

    def _on_periodic_update(self) -> bool:
        self._start_fetch_thread()
        return True

    def refresh(self) -> None:
        self._start_fetch_thread()

    def get_weather_info_for_code(
        self, code: int, is_day: int = 1
    ) -> Tuple[str, str, str, str]:
        return get_weather_info(code, is_day)
