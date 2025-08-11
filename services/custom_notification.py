# Standard library imports
import json
import os
from typing import List

# Fabric imports
import gi
from gi.repository import GdkPixbuf

import config.data as data
from fabric.core.service import Property, Service, Signal
from fabric.notifications import (
    Notification,
    NotificationAction,
    NotificationImagePixmap,
    Notifications,
)

gi.require_version("Gtk", "3.0")

NOTIFICATION_CACHE_FILE = f"{data.CACHE_DIR}/notification"


class CachedNotification(Service):
    @classmethod
    def create_from_dict(cls, data, **kwargs):
        data["timeout"] = 0
        self = cls.__new__(cls)
        Service.__init__(self, **kwargs)
        self._notification = Notification.deserialize(data)
        self.cache_id = data["cached-id"]
        return self

    @Signal
    def removed_from_cache(self) -> None: ...

    @Property(int, "read-write")
    def cache_id(self) -> int:
        return self._cache_id

    @cache_id.setter
    def cache_id(self, cache_id: int):
        self._cache_id = cache_id

    @Property(str, "readable")
    def app_name(self) -> str:
        return self._notification.app_name

    @Property(str, "readable")
    def app_icon(self) -> str:
        return self._notification.app_icon

    @Property(str, "readable")
    def summary(self) -> str:
        return self._notification.summary

    @Property(str, "readable")
    def body(self) -> str:
        return self._notification.body

    @Property(int, "readable")
    def id(self) -> int:
        return self._notification.id

    @Property(int, "readable")
    def replaces_id(self) -> int:
        return self._notification.replaces_id

    @Property(int, "readable")
    def urgency(self) -> int:
        return self._notification.urgency

    @Property(list[NotificationAction], "readable")
    def actions(self) -> list[NotificationAction]:
        return self._notification.actions

    @Property(NotificationImagePixmap, "readable")
    def image_pixmap(self) -> NotificationImagePixmap:
        return self._notification.image_pixmap  # type: ignore

    @Property(str, "readable")
    def image_file(self) -> str:
        return self._notification.image_file  # type: ignore

    @Property(GdkPixbuf.Pixbuf, "readable")
    def image_pixbuf(self) -> GdkPixbuf.Pixbuf:
        if self.image_pixmap:
            return self.image_pixmap.as_pixbuf()
        if self.image_file and os.path.exists(self.image_file):
            try:
                return GdkPixbuf.Pixbuf.new_from_file(self.image_file)
            except Exception:
                # If file can't be loaded, return None
                pass
        return None  # type: ignore

    @Property(dict, "readable")
    def serialized(self) -> dict:
        return {
            "cached-id": self.cache_id,
            "id": self.id,
            "replaces-id": self.replaces_id,
            "app-name": self.app_name,
            "app-icon": self.app_icon,
            "summary": self.summary,
            "body": self.body,
            "urgency": self.urgency,
            "actions": [(action.identifier, action.label) for action in self.actions],
            "image-file": self.image_file,
            "image-pixmap": (
                self.image_pixmap.serialize() if self.image_pixmap else None
            ),
        }

    def __init__(self, notification: Notification, cache_id: int, **kwargs):
        super().__init__()
        self._notification: Notification = notification
        self._cache_id = cache_id

    def remove_from_cache(self):
        self.removed_from_cache.emit()


class CachedNotifications(Notifications):
    """A service to manage the cached notifications."""

    @Signal
    def clear_all(self) -> None:
        """Signal emitted when notifications are emptied."""
        pass

    @Signal
    def cached_notification_added(self, notification: CachedNotification) -> None:
        """Signal emitted when a notification is cached."""
        pass

    @Signal
    def cached_notification_removed(self, notification: CachedNotification) -> None:
        """Signal emitted when a notification is removed from cache."""
        pass

    @Property(List[CachedNotification], "readable")
    def cached_notifications(self) -> List[CachedNotification]:
        """Return the cached notifications."""
        return list(self._cached_notifications.values())

    @Property(int, "readable")
    def count(self) -> int:
        """Return the count of notifications."""
        return self._count

    @Property(bool, "read-write", default_value=False)
    def dont_disturb(self) -> bool:
        """Return the pause status."""
        return self._dont_disturb

    @dont_disturb.setter
    def dont_disturb(self, value: bool):
        """Set the pause status."""
        self._dont_disturb = value
        self.notify("dont-disturb")

    def __init__(self, **kwargs):
        super().__init__()
        self._cached_notifications: dict[int, CachedNotification] = {}
        self._signal_handlers = {}  # Store signal handlers by notification_id
        self._dont_disturb = False
        self._count = 0

        self.load_cached_notifications()

    def load_cached_notifications(self) -> dict[int, CachedNotification]:
        """Load cached notifications from a JSON file (deserialization)."""
        try:
            with open(NOTIFICATION_CACHE_FILE, "r") as file:
                data = json.load(file)  # Load list of serialized notifications
        except (FileNotFoundError, json.JSONDecodeError):
            # If file doesn't exist or is corrupted, start with empty list
            data = []

        for notification in data:
            cached_notification = CachedNotification.create_from_dict(notification)
            handler_id = cached_notification.connect(
                "removed-from-cache",
                lambda *args: self.remove_cached_notification(
                    notification_id=cached_notification.cache_id
                ),
            )
            self._signal_handlers[cached_notification.cache_id] = handler_id
            self._cached_notifications[cached_notification.cache_id] = (
                cached_notification
            )
            self._count += 1

        self.notify("count")

    def cache_notifications(self) -> None:
        """Save cached notifications to a JSON file."""
        # Ensure cache directory exists
        os.makedirs(os.path.dirname(NOTIFICATION_CACHE_FILE), exist_ok=True)

        serialized_data = [
            notif.serialized for notif in self._cached_notifications.values()
        ]  # Convert to serializable format
        with open(NOTIFICATION_CACHE_FILE, "w") as file:
            json.dump(serialized_data, file, indent=4)

    def clear_all_cached_notifications(self):
        """Empty the notifications."""
        for cached_notification in self._cached_notifications.values():
            handler_id = self._signal_handlers.pop(cached_notification.cache_id, None)
            if handler_id:
                cached_notification.disconnect(handler_id)
        self._cached_notifications = {}
        self.cache_notifications()
        self._count = 0
        self.notify("count")
        self.clear_all.emit()

    def notification_added(self, notification_id: int) -> None:
        """Handle notification added and cache it."""
        super().notification_added(notification_id)

        notification = self.get_notification_from_id(notification_id)

        if notification:
            # Import here to avoid circular imports
            from config import data

            # Check if this app should be ignored for history (don't cache)
            if notification.app_name in data.NOTIFICATION_IGNORED_APPS_HISTORY:
                # Don't cache notifications from ignored apps, but still allow popup display
                return

            # Cache notifications (except for ignored apps)
            # DND only affects popup display, not caching
            self._count += 1
            cache_id = self._count

            cached_notification = CachedNotification(
                notification=notification, cache_id=cache_id
            )
            handler_id = cached_notification.connect(
                "removed-from-cache",
                lambda *args: self.remove_cached_notification(notification_id=cache_id),
            )

            self._signal_handlers[cache_id] = handler_id
            self._cached_notifications[cache_id] = cached_notification
            self.cache_notifications()

            self.notify("count")
            self.emit("cached-notification-added", cached_notification)

    def remove_cached_notification(self, notification_id: int):
        """Remove the notification of given id."""
        if notification_id in self._cached_notifications:
            cached_notification = self._cached_notifications.pop(
                notification_id
            )  # Remove from cache
            self.cache_notifications()  # Update JSON
            self._count -= 1
            self.notify("count")
            # Get the stored signal handler ID and disconnect it
            handler_id = self._signal_handlers.pop(notification_id, None)
            if handler_id:
                # Disconnect the signal handler
                cached_notification.disconnect(handler_id)

            # Emit signal to notify UI that notification was removed
            self.emit("cached-notification-removed", cached_notification)

    def toggle_dnd(self):
        self.dont_disturb = not self.dont_disturb
