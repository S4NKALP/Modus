import config.data as data
from gi.repository import GLib
import json
import os
from typing import List

import gi
from fabric import Signal
from fabric.notifications import Notification, Notifications
from loguru import logger

gi.require_version("GLib", "2.0")


NOTIFICATION_CACHE_FILE = f"{data.CACHE_DIR}/notifications.json"


class CustomNotifications(Notifications):
    """A service to manage the notifications."""

    @Signal
    def clear_all(self, value: bool) -> None:
        """Signal emitted when notifications are emptied."""
        # Implement as needed for your application

    @Signal
    def notification_count(self, value: int) -> None:
        """Signal emitted when a new notification is added."""
        # Implement as needed for your application

    @Signal
    def dnd(self, value: bool) -> None:
        """Signal emitted when dnd is toggled."""
        # Implement as needed for your application

    @property
    def count(self) -> int:
        """Return the count of notifications."""
        return len(self.all_notifications)

    @property
    def dont_disturb(self) -> bool:
        """Return the pause status."""
        return self._dont_disturb

    @dont_disturb.setter
    def dont_disturb(self, value: bool):
        """Set the pause status."""
        self._dont_disturb = value
        self.emit("dnd", value)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.all_notifications = []
        self._count = 0  # Will be updated to highest ID when loading
        self.deserialized_notifications = []
        self._dont_disturb = False
        self._load_notifications()

    def _load_notifications(self):
        """Read notifications from the cache file."""
        if os.path.exists(NOTIFICATION_CACHE_FILE):
            try:
                with open(NOTIFICATION_CACHE_FILE, "r") as file:
                    notifications = json.load(file)

                def validate_with_id(notif):
                    """Helper to validate and return ID if valid."""
                    try:
                        self._deserialize_notification(notif)
                        return (True, notif, notif.get("id", 0))
                    except Exception as e:
                        msg = f"[Notification] Invalid: {str(e)[:50]}"
                        logger.error(msg)
                        return (False, None, 0)

                # Validate all notifications at once
                results = [validate_with_id(n) for n in notifications]

                # Process results and find highest ID
                valid_notifications = []
                highest_id = self._count  # Start with current count
                for is_valid, notif, notif_id in results:
                    if is_valid:
                        valid_notifications.append(notif)
                        highest_id = max(highest_id, notif_id)

                self.all_notifications = valid_notifications
                self._count = highest_id  # Update to highest ID seen
                self._write_notifications(self.all_notifications)

            except (json.JSONDecodeError, KeyError, ValueError, IndexError) as e:
                logger.error(f"[Notification] {e}")
                self.all_notifications = []
                self._count = 0

    def remove_notification(self, id: int):
        """Remove the notification of given id."""
        item = next((p for p in self.all_notifications if p["id"] == id), None)
        if item:
            self.all_notifications.remove(item)
            self._write_notifications(self.all_notifications)
            self.emit("notification_count", len(self.all_notifications))

            # Emit clear_all signal if there are no notifications left
            if len(self.all_notifications) == 0:
                self.emit("clear_all", True)

    def cache_notification(self, data: Notification):
        """Cache the notification without widget_config and max_count."""

        # First clean up any invalid notifications
        self._cleanup_invalid_notifications()

        # Create the new notification
        self._count += 1
        new_id = self._count
        timestamp = GLib.get_real_time() / 1000000  # Convert microseconds to seconds
        serialized_data = data.serialize()
        serialized_data.update(
            {"id": new_id, "app_name": data.app_name, "timestamp": timestamp}
        )

        # Append the new notification
        self.all_notifications.append(serialized_data)

        self._write_notifications(self.all_notifications)
        self.emit("notification_count", len(self.all_notifications))

    def _cleanup_invalid_notifications(self):
        """Remove any invalid notifications."""

        def validate_with_id(notif):
            """Helper to validate and return result with ID."""
            try:
                self._deserialize_notification(notif)
                return (True, notif, None)
            except Exception as e:
                msg = f"[Notification] Removing invalid: {str(e)[:50]}"
                logger.debug(msg)
                return (False, None, notif.get("id", 0))

        # Validate all notifications at once
        results = [validate_with_id(n) for n in self.all_notifications]

        # Process results
        valid_notifications = []
        invalid_count = 0
        for is_valid, notif, invalid_id in results:
            if is_valid:
                valid_notifications.append(notif)
            else:
                invalid_count += 1
                self.emit("notification-closed", invalid_id, "dismissed-by-limit")

        if invalid_count > 0:
            self.all_notifications = valid_notifications
            self._write_notifications(self.all_notifications)
            self.emit("notification_count", len(self.all_notifications))

    def _deserialize_notification(self, notification):
        """Deserialize a notification."""
        try:
            notif = Notification.deserialize(notification)
            # Store the timestamp in the notification object
            notif.timestamp = notification.get(
                "timestamp", GLib.get_real_time() / 1000000
            )
            return notif
        except Exception as e:
            logger.error(
                f"[Notification] Deserialize failed for: {notification}, Error: {e}"
            )
            raise

    def clear_all_notifications(self):
        """Empty the notifications."""
        logger.info("[Notification] Clearing all notifications")
        # Clear notifications but preserve the highest ID we've seen
        highest_id = self._count
        self.all_notifications = []
        self._write_notifications(self.all_notifications)
        self.emit("notification_count", 0)
        self.emit("clear_all", True)
        # Restore the ID counter so new notifications get unique IDs
        self._count = highest_id

    def _write_notifications(self, data):
        """Write the notifications to the cache file."""
        try:
            with open(NOTIFICATION_CACHE_FILE, "w") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info("[Notification] Notifications written successfully.")
        except Exception as e:
            logger.error(f"[Notification] Failed to write notifications: {e}")

    def get_deserialized(self) -> List[Notification]:
        """Return the notifications."""

        def deserialize_with_id(notif):
            """Helper to deserialize and return result with ID."""
            try:
                return (self._deserialize_notification(notif), None)
            except Exception as e:
                msg = f"[Notification] Deserialize failed: {str(e)[:50]}"
                logger.error(msg)
                return (None, notif.get("id"))

        # Process all notifications at once
        results = [
            deserialize_with_id(notification) for notification in self.all_notifications
        ]

        # Split into successful and failed
        deserialized = []
        invalid_ids = []
        for result, error_id in results:
            if result is not None:
                deserialized.append(result)
            elif error_id is not None:
                invalid_ids.append(error_id)

        # Clean up invalid notifications
        for invalid_id in invalid_ids:
            self.remove_notification(invalid_id)

        return deserialized
