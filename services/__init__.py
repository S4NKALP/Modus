"""
Modus services package.
Contains background services and utilities for the shell.
"""

from .notification import CustomNotifications
from .weather import WeatherService

notification_service = CustomNotifications()
weather_service = WeatherService()
