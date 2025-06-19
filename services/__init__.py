"""
Modus services package.
Contains background services and utilities for the shell.
"""

from .notification import CustomNotifications

notification_service = CustomNotifications()
