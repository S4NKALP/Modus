"""Example: package plugin with third-party dependencies.

Demonstrates:
  - Package plugin structure
  - Third-party deps via requirements.txt (uv venv auto-install)
  - Keyword activation + global search
  - Deep reload during development
  - Cancellation checks for I/O
  - External command support

Usage:
  cp -r examples/plugins/weather config/plugins/weather

  Set your API key:
    env = OPENWEATHER_API_KEY, your_key_here

  Open spotlight and type "wth london" or just "london".
  After editing, deep-reload:
    fabric-cli exec modus1 'deep_reload weather'
"""

import os
from typing import Any

from window.spotlight.api import SearchResult, SpotlightPlugin

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


class WeatherPlugin(SpotlightPlugin):
    id = "weather"
    name = "Weather"
    icon = "weather-clear-symbolic"
    keywords = ["wth", "weather"]
    searchable = True
    priority = 75

    def __init__(self, context):
        super().__init__(context)
        self._cache: dict | None = None

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        self._cache = None

    def release_memory(self) -> None:
        self._cache = None

    def search(self, query: str, token: Any) -> list[SearchResult]:
        q = query.strip().lower()

        for prefix in ("wth ", "weather "):
            if q.startswith(prefix):
                q = q[len(prefix) :].strip()
                break
        if q in ("wth", "weather"):
            q = ""

        if not q:
            return [
                SearchResult(
                    id="weather_hint",
                    title="Weather",
                    subtitle="Type 'wth <city>' to get current weather",
                    icon_name="weather-clear-symbolic",
                    score=100.0,
                    render_type="default",
                )
            ]

        data = self._fetch_weather(q, token)
        if token.is_cancelled or not data:
            return []

        temp = data.get("main", {}).get("temp", "?")
        desc = data.get("weather", [{}])[0].get("description", "?")
        city = data.get("name", q)

        return [
            SearchResult(
                id=f"weather_{q}",
                title=f"{city}: {temp}°C",
                subtitle=desc.capitalize(),
                icon_name="weather-clear-symbolic",
                score=100.0,
                render_type="default",
            )
        ]

    def _fetch_weather(self, city: str, token: Any) -> dict | None:
        if self._cache:
            return self._cache

        api_key = os.environ.get("OPENWEATHER_API_KEY")
        if not api_key or requests is None:
            return None

        try:
            resp = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": api_key, "units": "metric"},
                timeout=10,
            )
            if token.is_cancelled:
                return None
            if resp.status_code == 200:
                self._cache = resp.json()
                return self._cache
        except Exception:
            pass
        return None

    def handle_external(self, command: str, args: str) -> None:
        print(f"[Weather] External: {command} {args}")

    def on_activate(self, update_fn=None) -> None:
        print("[Weather] Keyword mode activated")

    def on_deactivate(self) -> None:
        print("[Weather] Keyword mode deactivated")


PLUGIN = WeatherPlugin
