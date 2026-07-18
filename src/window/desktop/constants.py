import datetime

WEATHER_UPDATE_INTERVAL = 600  # 10 minutes
WEATHER_CACHE_TIMEOUT = 1800  # 30 minutes
SYSTEM_UPDATE_INTERVAL = 60000  # 1 minute instead of 1 second
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

# Weather condition to SVG icon mapping
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
