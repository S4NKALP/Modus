# Standard library imports
import json
import os
import time
from typing import List

# Fabric imports
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

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
gi.require_version("GdkPixbuf", "2.0")

NOTIFICATION_CACHE_FILE = f"{data.CACHE_DIR}/notification_history.json"


class CachedNotification(Service):
    @classmethod
    def create_from_dict(cls, data, **kwargs):
        """Create CachedNotification from enhanced JSON data"""
        data["timeout"] = 0
        self = cls.__new__(cls)
        Service.__init__(self, **kwargs)
        self._notification = Notification.deserialize(data)
        self._cache_id = data["cached-id"]  # Set directly to private var
        
        # Store cache metadata for cleanup
        self.cache_metadata = data.get("cache_metadata", {})
        self.timestamp = data.get("timestamp", int(time.time()))
        
        return self

    @Signal
    def removed_from_cache(self) -> None: ...

    @Property(int, "readable")
    def cache_id(self) -> int:
        return self._cache_id

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

    @Property(object, "readable")
    def image_pixbuf(self) -> GdkPixbuf.Pixbuf | None:
        try:
            if self.image_pixmap:
                return self.image_pixmap.as_pixbuf()
            if self.image_file and os.path.exists(self.image_file):
                try:
                    return GdkPixbuf.Pixbuf.new_from_file(self.image_file)
                except Exception:
                    # If file can't be loaded, return None
                    pass
        except Exception:
            # If any error occurs (including temp file gone), return None safely
            pass
        return None

    @Property(dict, "readable")
    def serialized(self) -> dict:
        """Enhanced serialization with cache metadata - stores only cache keys"""
        from modules.notification.notification import (
            get_cache_key,
            get_notification_image_cache_key,
        )
        
        # Get better cache keys for icons
        app_icon_cache_key = None
        notification_image_cache_key = None
        
        if self.app_icon:
            app_icon_cache_key = get_cache_key(self.app_icon, (35, 35), self.app_name)
        
        # Only try to get notification image cache key if we can safely access image_pixbuf
        if self.id:
            try:
                # First check if we already have the cache key stored
                if hasattr(self, 'cache_metadata') and self.cache_metadata:
                    notification_image_cache_key = self.cache_metadata.get('notification_image_cache_key')
                
                # If not, try to generate it safely
                if not notification_image_cache_key and hasattr(self._notification, 'image_pixbuf'):
                    try:
                        # Check if image_pixbuf exists and can be accessed without loading from file
                        image_pixbuf = getattr(self._notification, 'image_pixbuf', None)
                        if image_pixbuf:
                            notification_image_cache_key = get_notification_image_cache_key(
                                self.id, image_pixbuf
                            )
                    except (AttributeError, OSError, Exception):
                        # If temp file is gone or any other error, just mark as None
                        pass
            except Exception:
                # If any error occurs during cache key generation, skip it
                pass
        
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
            # Only store image-pixmap if no cache key is available (fallback)
            "image-pixmap": None,  # Don't store image data, only cache key
            "timestamp": int(time.time()),
            "group": self.app_name,  # Group notifications by app name
            # Enhanced cache metadata - store only cache keys
            "cache_metadata": {
                "app_icon_cache_key": app_icon_cache_key,
                "notification_image_cache_key": notification_image_cache_key,
                "has_cached_image": notification_image_cache_key is not None,
                "cache_timestamp": int(time.time())
            }
        }

    def __init__(self, notification: Notification, cache_id: int, **kwargs):
        super().__init__()
        self._notification: Notification = notification
        self._cache_id = cache_id
        self.cache_metadata = {}
        self.timestamp = int(time.time())

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
        
    def set_dont_disturb(self, value: bool):
        """Set the pause status."""
        self._dont_disturb = value
        self.notify("dont-disturb")

    def __init__(self, **kwargs):
        super().__init__()
        self._cached_notifications: dict[int, CachedNotification] = {}
        self._signal_handlers = {}  # Store signal handlers by notification_id
        self._dont_disturb = False
        self._count = 0
        self._next_cache_id = 1  # Track next available cache ID
        self._session_start_time = int(time.time())  # Track session start time for deduplication

        self.load_cached_notifications()
        
        # Connect to the notification_added signal to cache new notifications
        # Note: self here refers to the CachedNotifications service, which inherits from Notifications
        # So we connect to our own notification_added signal
        super().notification_added.connect(self.on_notification_added)

    def load_cached_notifications(self) -> dict[int, CachedNotification]:
        """Load cached notifications from a JSON file (deserialization)."""
        try:
            with open(NOTIFICATION_CACHE_FILE, "r") as file:
                data = json.load(file)  # Load list of serialized notifications
        except (FileNotFoundError, json.JSONDecodeError):
            # If file doesn't exist or is corrupted, start with empty list
            data = []

        max_cache_id = 0
        for notification in data:
            cached_notification = CachedNotification.create_from_dict(notification)
            cache_id = cached_notification.cache_id
            max_cache_id = max(max_cache_id, cache_id)
            
            handler_id = cached_notification.connect(
                "removed-from-cache",
                lambda *args: self.remove_cached_notification(
                    notification_id=cache_id
                ),
            )
            self._signal_handlers[cache_id] = handler_id
            self._cached_notifications[cache_id] = cached_notification
            self._count += 1

        # Set next cache ID to be higher than any existing ID
        self._next_cache_id = max_cache_id + 1
        self.notify("count")
        return self._cached_notifications

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
        """Empty the notifications with enhanced cache cleanup"""
        # Clean up all cached files before clearing notifications
        from modules.notification.notification import cleanup_all_notification_caches
        
        for cached_notification in self._cached_notifications.values():
            handler_id = self._signal_handlers.pop(cached_notification.cache_id, None)
            if handler_id:
                cached_notification.disconnect(handler_id)
                
        # Clear all notification caches (icons and images)
        cleanup_all_notification_caches()
        
        self._cached_notifications = {}
        self.cache_notifications()
        self._count = 0
        self._next_cache_id = 1  # Reset cache ID counter
        self.notify("count")
        self.clear_all.emit()

    def on_notification_added(self, service, notification_id: int) -> None:
        """Handle notification added and cache it with enhanced metadata - GUARANTEED STORAGE"""
        # Don't call super() - we're handling this ourselves
        
        # Import logger at the top of the function
        from loguru import logger
        
        notification = self.get_notification_from_id(notification_id)

        if not notification:
            logger.error(f"CRITICAL: Failed to get notification with ID {notification_id}")
            return

        # Import here to avoid circular imports
        from config import data
        from modules.notification.notification import (
            preload_notification_assets,
            cache_notification_icon,
            cache_notification_image,
            get_cache_key,
            get_notification_image_cache_key
        )

        # Check if this app should be ignored for history (don't cache)
        if notification.app_name in data.NOTIFICATION_IGNORED_APPS_HISTORY:
            # Don't cache notifications from ignored apps, but still allow popup display
            logger.debug(f"Ignoring notification from {notification.app_name} (in ignore list)")
            return

        # Check for duplicates using both notification ID and timestamp to avoid session restart issues
        existing_notification = None
        current_time = int(time.time())
        
        for cached_notif in self._cached_notifications.values():
            # Only consider it a duplicate if:
            # 1. Same notification ID AND
            # 2. Notification was cached in the current session (after session start time) AND  
            # 3. Notification was cached recently (within last 5 minutes)
            cached_time = getattr(cached_notif, 'timestamp', 0)
            is_recent = (current_time - cached_time) < 300  # 5 minutes
            is_current_session = cached_time >= self._session_start_time
            
            if (cached_notif._notification.id == notification.id and 
                is_current_session and is_recent):
                existing_notification = cached_notif
                break
        
        if existing_notification:
            logger.debug(f"Notification ID {notification.id} already cached in current session, skipping")
            return

        logger.debug(f"Caching new notification: ID={notification.id}, App={notification.app_name}, Summary={notification.summary[:50]}...")

        # GUARANTEED STORAGE: Always create and store notification to history first
        cache_id = self._next_cache_id
        self._next_cache_id += 1
        self._count += 1

        cached_notification = CachedNotification(
            notification=notification, cache_id=cache_id
        )
        # Set cache_id directly since it's read-only property  
        cached_notification._cache_id = cache_id
        
        # Initialize cache metadata (will be populated below)
        cached_notification.cache_metadata = {
            "app_icon_cache_key": None,
            "notification_image_cache_key": None,
            "has_cached_image": False,
            "cache_timestamp": int(time.time())
        }
        
        # IMMEDIATELY store to history before attempting any caching operations
        handler_id = cached_notification.connect(
            "removed-from-cache",
            lambda *args: self.remove_cached_notification(notification_id=cache_id),
        )
        self._signal_handlers[cache_id] = handler_id
        self._cached_notifications[cache_id] = cached_notification
        
        # Save to JSON file immediately - GUARANTEED STORAGE
        try:
            self.cache_notifications()
            logger.debug(f"GUARANTEED: Notification {cache_id} stored to history")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to save notification {cache_id} to history: {e}")
        
        # Now attempt asset caching (failures here won't affect history storage)
        try:
            # Preload assets and store cache metadata
            preload_notification_assets(notification)
            
            # Store enhanced cache metadata
            app_icon_cache_key = None
            notification_image_cache_key = None
            
            if notification.app_icon:
                try:
                    # Only cache at 35x35 to reduce disk usage - headers will scale this down
                    app_icon_cache_key = get_cache_key(notification.app_icon, (35, 35), notification.app_name)
                    cache_notification_icon(notification.app_icon, (35, 35), notification.app_name)
                    cached_notification.cache_metadata["app_icon_cache_key"] = app_icon_cache_key
                    logger.debug(f"Cached app icon (35x35) for notification {cache_id}")
                except Exception as e:
                    logger.warning(f"Failed to cache app icon for notification {cache_id}: {e}")
            
            if hasattr(notification, 'image_pixbuf'):
                try:
                    # Safely try to access image_pixbuf
                    image_pixbuf = getattr(notification, 'image_pixbuf', None)
                    if image_pixbuf:
                        notification_image_cache_key = get_notification_image_cache_key(
                            notification.id, image_pixbuf
                        )
                        cache_notification_image(notification.id, image_pixbuf, (35, 35))
                        cached_notification.cache_metadata["notification_image_cache_key"] = notification_image_cache_key
                        cached_notification.cache_metadata["has_cached_image"] = True
                        logger.debug(f"Cached notification image for notification {cache_id}")
                except (AttributeError, OSError, Exception) as e:
                    logger.warning(f"Failed to cache notification image for notification {cache_id}: {e}")
            
            # Update cached notification with final metadata
            self._cached_notifications[cache_id] = cached_notification
            
            # Save updated metadata to JSON
            self.cache_notifications()
            
        except Exception as e:
            logger.error(f"Asset caching failed for notification {cache_id}, but notification is still stored: {e}")

        # Always emit signals regardless of caching success
        self.notify("count")
        self.emit("cached-notification-added", cached_notification)
        
        logger.debug(f"Successfully processed notification: Cache ID={cache_id}, Total cached={len(self._cached_notifications)}")

    def remove_cached_notification(self, notification_id: int):
        """Remove the notification of given id with enhanced cache cleanup"""
        if notification_id in self._cached_notifications:
            cached_notification = self._cached_notifications.pop(notification_id)
            
            # Enhanced cache cleanup using stored metadata
            if hasattr(cached_notification, 'cache_metadata'):
                cache_metadata = cached_notification.cache_metadata
                
                # Clean up specific cached files using stored keys
                from modules.notification.notification import cleanup_notification_specific_caches
                cleanup_notification_specific_caches(
                    app_icon_source=cached_notification.app_icon,
                    notification_image_cache_key=cache_metadata.get('notification_image_cache_key')
                )
            
            self.cache_notifications()  # Update JSON
            self._count -= 1
            self.notify("count")
            
            # Get the stored signal handler ID and disconnect it
            handler_id = self._signal_handlers.pop(notification_id, None)
            if handler_id:
                cached_notification.disconnect(handler_id)

            # Emit signal to notify UI that notification was removed
            self.emit("cached-notification-removed", cached_notification)

    def toggle_dnd(self):
        self.set_dont_disturb(not self.dont_disturb)
