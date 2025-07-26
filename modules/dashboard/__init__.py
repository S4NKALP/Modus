"""
Dashboard module for Modus.
Provides a dashboard interface with tiles and notifications.
"""

from .main import DashboardWindow
from .notifications import DashboardNotifications, DashboardNotificationItem

__all__ = ["DashboardWindow", "DashboardNotifications", "DashboardNotificationItem"]
