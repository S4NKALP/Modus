"""
Common notification utilities and shared functionality
"""
import json
import locale
import os
import uuid
from datetime import datetime, timedelta

from fabric.utils.helpers import get_relative_path
from fabric.widgets.box import Box
from gi.repository import GdkPixbuf, GLib, GObject
from loguru import logger

import config.data as data

# Constants
PERSISTENT_DIR = f"/tmp/{data.APP_NAME}/notifications"
PERSISTENT_HISTORY_FILE = os.path.join(PERSISTENT_DIR, "notification_history.json")
CONFIG_FILE = get_relative_path("../config/assets/config.json")
NOTIFICATION_IMAGE_PREFIX = "notification_"
NOTIFICATION_IMAGE_SUFFIX = ".png"
DEFAULT_NOTIFICATION_IMAGE_SIZE = 48
MAX_PERSISTENT_NOTIFICATIONS = 100
LIMITED_APPS = ["Spotify"]

# Global shared notification history instance
_shared_notification_history = None


class HistoricalNotification:
    """Data structure for historical notification data"""

    def __init__(self, id, app_icon, summary, body, app_name, timestamp, cached_image_path=None):
        self.id = id
        self.app_icon = app_icon
        self.summary = summary
        self.body = body
        self.app_name = app_name
        self.timestamp = timestamp
        self.cached_image_path = cached_image_path
        self.image_pixbuf = None
        self.actions = []
        self.cached_scaled_pixbuf = None


# Image handling functions
def cache_notification_pixbuf(notification_box):
    """Cache notification image to disk and return cache file path"""
    notification = notification_box.notification
    if notification.image_pixbuf:
        os.makedirs(PERSISTENT_DIR, exist_ok=True)
        cache_file = os.path.join(
            PERSISTENT_DIR, f"{NOTIFICATION_IMAGE_PREFIX}{notification_box.uuid}{NOTIFICATION_IMAGE_SUFFIX}"
        )

        try:
            scaled = notification.image_pixbuf.scale_simple(
                DEFAULT_NOTIFICATION_IMAGE_SIZE, DEFAULT_NOTIFICATION_IMAGE_SIZE, GdkPixbuf.InterpType.BILINEAR
            )
            scaled.savev(cache_file, "png", [], [])
            return cache_file
        except Exception as e:
            logger.error(f"Error caching image for notification {notification.id}: {e}")
            return None
    else:
        logger.debug(f"Notification {notification.id} has no image_pixbuf to cache.")
        return None


def load_scaled_pixbuf(notification_box, width, height):
    """Load and scale pixbuf from notification box"""
    notification = notification_box.notification
    if not hasattr(notification_box, "notification") or notification is None:
        return None

    pixbuf = None

    # Try to load from cached image first
    if (
        hasattr(notification_box, "cached_image_path")
        and notification_box.cached_image_path
        and os.path.exists(notification_box.cached_image_path)
    ):
        try:
            logger.debug(
                f"Attempting to load cached image from: {notification_box.cached_image_path} "
                f"for notification {notification.id}"
            )
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(notification_box.cached_image_path)
            if pixbuf:
                pixbuf = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
            return pixbuf
        except Exception as e:
            logger.error(
                f"Error loading cached image from {notification_box.cached_image_path} "
                f"for notification {notification.id}: {e}"
            )
            logger.warning(f"Falling back to notification.image_pixbuf for notification {notification.id}")

    # Fall back to notification image_pixbuf
    if notification.image_pixbuf:
        pixbuf = notification.image_pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
        return pixbuf

    # Fall back to app icon
    return get_app_icon_pixbuf(notification.app_icon, width, height)


def get_app_icon_pixbuf(icon_path, width, height):
    """Load and scale app icon pixbuf"""
    if not icon_path:
        return None
    if icon_path.startswith("file://"):
        icon_path = icon_path[7:]
    if not os.path.exists(icon_path):
        logger.warning(f"Icon path does not exist: {icon_path}")
        return None
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_path)
        return pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
    except Exception as e:
        logger.error(f"Failed to load or scale icon: {e}")
        return None


def cleanup_orphan_cached_images(persistent_notifications):
    """Clean up cached images that no longer have corresponding notifications"""
    if not os.path.exists(PERSISTENT_DIR):
        return

    cached_files = [
        f for f in os.listdir(PERSISTENT_DIR)
        if f.startswith(NOTIFICATION_IMAGE_PREFIX) and f.endswith(NOTIFICATION_IMAGE_SUFFIX)
    ]
    if not cached_files:
        return

    history_uuids = {
        note.get("id") for note in persistent_notifications if note.get("id")
    }
    for cached_file in cached_files:
        try:
            uuid_from_filename = cached_file[len(NOTIFICATION_IMAGE_PREFIX):-len(NOTIFICATION_IMAGE_SUFFIX)]
            if uuid_from_filename not in history_uuids:
                cache_file_path = os.path.join(PERSISTENT_DIR, cached_file)
                os.remove(cache_file_path)
        except Exception as e:
            print(f"Error processing cached file {cached_file} during cleanup: {e}")


def delete_cached_image(cached_image_path):
    """Delete a specific cached image file"""
    if cached_image_path and os.path.exists(cached_image_path):
        try:
            os.remove(cached_image_path)
            logger.info(f"Deleted cached image: {cached_image_path}")
        except Exception as e:
            logger.error(f"Error deleting cached image {cached_image_path}: {e}")


# Time and date utilities
def get_ordinal(n):
    """Get ordinal suffix for a number (1st, 2nd, 3rd, etc.)"""
    if 11 <= (n % 100) <= 13:
        return "th"
    else:
        return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def get_date_header(dt):
    """Get human-readable date header for a datetime"""
    now = datetime.now()
    today = now.date()
    date = dt.date()

    if date == today:
        return "Today"
    elif date == today - timedelta(days=1):
        return "Yesterday"
    else:
        original_locale = locale.getlocale(locale.LC_TIME)
        try:
            locale.setlocale(locale.LC_TIME, ("en_US", "UTF-8"))
        except locale.Error:
            locale.setlocale(locale.LC_TIME, "C")
        try:
            day = dt.day
            ordinal = get_ordinal(day)
            month = dt.strftime("%B")
            if dt.year == now.year:
                result = f"{month} {day}{ordinal}"
            else:
                result = f"{month} {day}{ordinal}, {dt.year}"
        finally:
            locale.setlocale(locale.LC_TIME, original_locale)
        return result


def schedule_midnight_update(callback):
    """Schedule a callback to run at midnight"""
    now = datetime.now()
    next_midnight = datetime.combine(
        now.date() + timedelta(days=1), datetime.min.time()
    )
    delta_seconds = (next_midnight - now).total_seconds()
    return GLib.timeout_add_seconds(int(delta_seconds), callback)


def compute_time_label(arrival_time):
    """Compute time label for notification timestamp"""
    return arrival_time.strftime("%H:%M")


# Data creation utilities
def create_notification_data(notification_box):
    """Create notification data dictionary from notification box"""
    notification = notification_box.notification

    return {
        "id": notification_box.uuid,
        "app_icon": getattr(notification, "app_icon", "dialog-information-symbolic"),
        "summary": getattr(notification, "summary", "No summary"),
        "body": getattr(notification, "body", ""),
        "app_name": getattr(notification, "app_name", "Unknown"),
        "timestamp": datetime.now().isoformat(),
        "cached_image_path": getattr(notification_box, "cached_image_path", None),
    }


def create_historical_notification_from_data(note_data):
    """Create HistoricalNotification object from data dictionary"""
    return HistoricalNotification(
        id=note_data.get("id"),
        app_icon=note_data.get("app_icon"),
        summary=note_data.get("summary"),
        body=note_data.get("body"),
        app_name=note_data.get("app_name"),
        timestamp=note_data.get("timestamp"),
        cached_image_path=note_data.get("cached_image_path"),
    )


# Storage utilities
def ensure_persistent_dir():
    """Ensure the persistent directory exists"""
    if not os.path.exists(PERSISTENT_DIR):
        os.makedirs(PERSISTENT_DIR, exist_ok=True)


def load_persistent_history():
    """Load notification history from persistent storage"""
    ensure_persistent_dir()

    if os.path.exists(PERSISTENT_HISTORY_FILE):
        try:
            with open(PERSISTENT_HISTORY_FILE, "r") as f:
                notifications = json.load(f)
            logger.info(f"Loaded {len(notifications)} notifications from persistent history")
            return notifications
        except Exception as e:
            logger.error(f"Error loading persistent history: {e}")
            return []
    else:
        return []


def save_persistent_history(notifications):
    """Save notification history to persistent storage"""
    try:
        ensure_persistent_dir()
        with open(PERSISTENT_HISTORY_FILE, "w") as f:
            json.dump(notifications, f, indent=2)
        logger.info(f"Saved {len(notifications)} notifications to persistent history")
    except Exception as e:
        logger.error(f"Error saving persistent history: {e}")


def load_dnd_state():
    """Load Do Not Disturb state from config"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)
                dnd_enabled = config_data.get("dnd_enabled", False)
                logger.info(f"Loaded DND state: {dnd_enabled}")
                return dnd_enabled
    except Exception as e:
        logger.error(f"Error loading DND state: {e}")

    return False


def save_dnd_state(dnd_enabled):
    """Save Do Not Disturb state to config"""
    try:
        config_data = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)

        config_data["dnd_enabled"] = dnd_enabled

        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=4)
        logger.debug(f"Saved DND state: {dnd_enabled}")
    except Exception as e:
        logger.error(f"Error saving DND state: {e}")


# Shared notification history class
class NotificationHistory(Box):
    """Shared notification history with DND state management"""

    __gsignals__ = {
        "dnd-state-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "notification-added": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, **kwargs):
        super().__init__(name="notification-history", orientation="v", **kwargs)
        self.do_not_disturb_enabled = False
        self.persistent_notifications = []
        self._load_persistent_history()
        self._load_dnd_state()

    def set_do_not_disturb_enabled(self, enabled):
        """Set DND state and emit signal if changed"""
        if self.do_not_disturb_enabled != enabled:
            self.do_not_disturb_enabled = enabled
            save_dnd_state(enabled)
            self.emit("dnd-state-changed", enabled)

    def _load_persistent_history(self):
        """Load persistent notification history"""
        self.persistent_notifications = load_persistent_history()

    def _load_dnd_state(self):
        """Load DND state from config"""
        self.do_not_disturb_enabled = load_dnd_state()

    def _save_persistent_history(self):
        """Save persistent notification history"""
        save_persistent_history(self.persistent_notifications)

    def add_notification(self, notification_box):
        """Add notification to history"""
        try:
            hist_data = create_notification_data(notification_box)
            self.persistent_notifications.append(hist_data)

            # Remove old notifications if we exceed the limit
            if len(self.persistent_notifications) > MAX_PERSISTENT_NOTIFICATIONS:
                self.persistent_notifications.pop(0)

            self._save_persistent_history()
            self.emit("notification-added")
        except Exception as e:
            print(f"Error adding notification to history: {e}")

    def clear_history_for_app(self, app_name):
        """Clear history for specific app"""
        try:
            original_count = len(self.persistent_notifications)
            self.persistent_notifications = [
                notif for notif in self.persistent_notifications
                if notif.get("app_name") != app_name
            ]
            removed_count = original_count - len(self.persistent_notifications)
            if removed_count > 0:
                self._save_persistent_history()
                logger.info(f"Cleared {removed_count} notifications for app: {app_name}")
        except Exception as e:
            print(f"Error clearing history for app {app_name}: {e}")


def get_shared_notification_history():
    """Get or create the shared notification history instance"""
    global _shared_notification_history
    if _shared_notification_history is None:
        _shared_notification_history = NotificationHistory()
    return _shared_notification_history
