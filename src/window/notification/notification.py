import hashlib
import time

from fabric.notifications import (
    Notification,
    NotificationAction,
    NotificationCloseReason,
)
from fabric.utils import Gdk, GdkPixbuf, GLib, Gtk, logger, os
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window

import shared.data as data
from services.config import get_config, on_config_change
from services.modus import notification_service
from shared.widgets.clipping_box import ClippingBox
from shared.widgets.custom_image import CustomImage
from shared.widgets.customrevealer import SlideRevealer
from utils.functions import escape_markup_text, parse_timeout_string
from utils.roam import modus_service
from utils.icon_resolver import IconResolver

# ruff: noqa: I001
from window.notification.unified_cache import (
    UNIFIED_NOTIFICATION_CACHE_DIR as _SHARED_NOTIFICATION_CACHE_DIR,
    cleanup_cache as _unified_cleanup_cache,
    cleanup_old_cache_files as _unified_cleanup_old_cache_files,
    ensure_cache_dir as _ensure_unified_cache_dir,
    get_fallback_icon as _shared_fallback_icon,
    get_from_cache as _unified_get_from_cache,
    get_unified_cache_key,
    save_to_cache as _unified_save_to_cache,
)

_icon_resolver = IconResolver()

NOTIFICATION_WIDTH = 360
NOTIFICATION_IMAGE_SIZE = 48

# Use shared unified cache directory from unified_cache
NOTIFICATION_ICON_CACHE_DIR = _SHARED_NOTIFICATION_CACHE_DIR
NOTIFICATION_IMAGE_CACHE_DIR = _SHARED_NOTIFICATION_CACHE_DIR


def ensure_notification_cache_dirs():
    """Ensure unified notification cache directory exists"""
    _ensure_unified_cache_dir()


def cleanup_old_cache_files():
    """Clean up old notification cache files (older than 7 days)"""
    try:
        _unified_cleanup_old_cache_files()
    except Exception as e:
        logger.warning(f"Failed to cleanup notification cache: {e}")


get_cache_key = get_unified_cache_key


def save_pixbuf_to_cache(pixbuf, cache_key, cache_dir):
    """Save a pixbuf to the specified cache directory"""
    try:
        ensure_notification_cache_dirs()
        # Delegate to unified cache; ignore returned key for compatibility
        result = _unified_save_to_cache(pixbuf, cache_key)
        if result and result[0]:
            return result[0]
        return None
    except Exception as e:
        logger.warning(f"Failed to cache notification icon: {e}")
        return None


def get_cached_pixbuf(cache_key, fallback_size=(48, 48), cache_dir=None):
    """Get a cached pixbuf or return None if not found"""
    if cache_dir is None:
        cache_dir = NOTIFICATION_ICON_CACHE_DIR

    try:
        pixbuf = _unified_get_from_cache(cache_key, fallback_size)
        if pixbuf:
            return pixbuf
    except Exception as e:
        logger.warning(f"Failed to load cached notification icon: {e}")
    return None


def cache_notification_icon(source, size=(48, 48), app_name=None):
    """Optimized notification icon caching with immediate pixbuf generation and caching"""
    try:
        ensure_notification_cache_dirs()

        # Handle different source types with optimized caching
        if isinstance(source, str):
            cache_key = get_unified_cache_key(source, size, app_name)

            # Check cache first for immediate return
            cached_pixbuf = get_cached_pixbuf(
                cache_key, fallback_size=size, cache_dir=NOTIFICATION_ICON_CACHE_DIR
            )
            if cached_pixbuf:
                return cached_pixbuf

            # Load, cache, and return icon in one optimized flow
            if source.startswith("file://"):
                # Local file URL - process and cache immediately
                file_path = source[7:]
                pixbuf = load_and_cache_local_icon(file_path, cache_key, size)
            elif os.path.exists(source):
                # Direct file path - process and cache immediately
                pixbuf = load_and_cache_local_icon(source, cache_key, size)
            else:
                # Icon name - resolve from theme and cache immediately
                pixbuf = load_and_cache_theme_icon(source, cache_key, size)

            return pixbuf

        elif hasattr(source, "scale_simple"):
            # Already a pixbuf - cache it directly with optimized flow
            cache_key = get_unified_cache_key(source, size, app_name)

            # Check cache first
            cached_pixbuf = get_cached_pixbuf(
                cache_key, fallback_size=size, cache_dir=NOTIFICATION_ICON_CACHE_DIR
            )
            if cached_pixbuf:
                return cached_pixbuf

            # Scale once and cache immediately
            scaled_pixbuf = source.scale_simple(
                size[0], size[1], GdkPixbuf.InterpType.BILINEAR
            )
            save_pixbuf_to_cache(scaled_pixbuf, cache_key, NOTIFICATION_ICON_CACHE_DIR)
            return scaled_pixbuf

    except Exception as e:
        logger.warning(f"Failed to cache notification icon: {e}")

    # Return fallback with caching
    return get_fallback_notification_icon(size)


def load_and_cache_local_icon(file_path, cache_key, size):
    """Load a local icon file and cache it"""
    try:
        if os.path.exists(file_path):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                file_path, size[0], size[1], True
            )
            save_pixbuf_to_cache(pixbuf, cache_key, NOTIFICATION_ICON_CACHE_DIR)
            return pixbuf
    except Exception as e:
        logger.warning(f"Failed to load local notification icon {file_path}: {e}")

    return get_fallback_notification_icon(size)


def load_and_cache_theme_icon(icon_name, cache_key, size):
    """Load an icon from the current theme and cache it"""
    try:
        pixbuf = _icon_resolver.get_icon_pixbuf(icon_name, size[0])
        if pixbuf:
            save_pixbuf_to_cache(pixbuf, cache_key, NOTIFICATION_ICON_CACHE_DIR)
            return pixbuf
    except Exception as e:
        logger.warning(f"Failed to load theme icon {icon_name}: {e}")

    return get_fallback_notification_icon(size)


def get_fallback_notification_icon(size=(48, 48)):
    return _shared_fallback_icon(size)


def get_notification_image_cache_key(notification_id, image_pixbuf):
    """Generate a deterministic cache key based on image content to prevent duplicate caching"""
    try:
        # Use image content hash for deterministic caching
        if image_pixbuf and hasattr(image_pixbuf, "get_pixels"):
            try:
                pixel_data = image_pixbuf.get_pixels()
                image_hash = hashlib.md5(pixel_data).hexdigest()[:8]
                return image_hash
            except Exception:
                # If pixel data fails, use image dimensions + timestamp
                try:
                    width = image_pixbuf.get_width()
                    height = image_pixbuf.get_height()
                    dimension_hash = hashlib.md5(
                        f"{width}x{height}".encode()
                    ).hexdigest()[:8]
                    return dimension_hash
                except Exception as e:
                    logger.error(f"An error occurred: {e}")

        # Fallback to timestamp for invalid pixbufs
        return str(int(time.time()))[:8]
    except Exception:
        # Ultimate fallback
        return str(int(time.time()))[:8]


def cache_notification_image(notification_id, image_pixbuf, size=(64, 64)):
    """Smart notification image caching that avoids duplicate caching"""
    try:
        ensure_notification_cache_dirs()

        # Generate deterministic cache key based on image content
        cache_key = get_notification_image_cache_key(notification_id, image_pixbuf)
        try:
            # Let unified cache handle scaling and saving
            saved_path, _ = _unified_save_to_cache(image_pixbuf, cache_key, size)
            if saved_path:
                return saved_path, cache_key
            return None, None
        except Exception as scale_error:
            logger.debug(
                f"Failed to cache image (temp file likely gone): {scale_error}"
            )
            return None, None

    except Exception as e:
        logger.warning(f"Failed to cache notification image: {e}")
        return None, None


def get_cached_notification_image(cache_key):
    """Get a cached notification image or return None if not found"""
    try:
        return _unified_get_from_cache(cache_key)
    except Exception as e:
        logger.warning(f"Failed to load cached notification image: {e}")
    return None


def cleanup_notification_image_cache(cache_key=None):
    """Clean up notification image cache - specific key or all"""
    try:
        ensure_notification_cache_dirs()
        _unified_cleanup_cache(cache_key)
    except Exception as e:
        logger.warning(f"Failed to cleanup notification image cache: {e}")


def cleanup_notification_specific_caches(
    app_icon_source=None, notification_image_cache_key=None
):
    """Clean up caches specific to a notification (both app icon and notification image) - SINGLE ICON SIZE"""
    try:
        # Clean up notification image cache
        if notification_image_cache_key:
            _unified_cleanup_cache(notification_image_cache_key)

        # Clean up app icon cache for this specific source (only 64x64 version)
        if app_icon_source:
            # Only clean 64x64 version since we only cache this size now
            cache_key_64 = get_unified_cache_key(app_icon_source, (64, 64))
            _unified_cleanup_cache(cache_key_64)

    except Exception as e:
        logger.warning(f"Failed to cleanup notification specific caches: {e}")


def cleanup_all_notification_caches():
    """Clean up ALL notification caches (icons and images)"""
    try:
        _unified_cleanup_cache()
    except Exception as e:
        logger.warning(f"Failed to cleanup all notification caches: {e}")


def verify_cache_persistence():
    """Verify that cached icons persist and can be loaded after restart"""
    try:
        icon_cache_files = []
        image_cache_files = []

        if os.path.exists(NOTIFICATION_ICON_CACHE_DIR):
            icon_cache_files = [
                f for f in os.listdir(NOTIFICATION_ICON_CACHE_DIR) if f.endswith(".png")
            ]

        if os.path.exists(NOTIFICATION_IMAGE_CACHE_DIR):
            image_cache_files = [
                f
                for f in os.listdir(NOTIFICATION_IMAGE_CACHE_DIR)
                if f.endswith(".png")
            ]

        # Test loading a few cached items to verify they work
        for cache_file in icon_cache_files[:2]:  # Test first 2 icon files
            try:
                cache_path = os.path.join(NOTIFICATION_ICON_CACHE_DIR, cache_file)
                GdkPixbuf.Pixbuf.new_from_file(cache_path)
            except Exception as e:
                logger.warning(f"Failed to load cached icon {cache_file}: {e}")

        for cache_file in image_cache_files[:2]:  # Test first 2 image files
            try:
                cache_path = os.path.join(NOTIFICATION_IMAGE_CACHE_DIR, cache_file)
                GdkPixbuf.Pixbuf.new_from_file(cache_path)
            except Exception as e:
                logger.warning(f"Failed to load cached image {cache_file}: {e}")

        return len(icon_cache_files) + len(image_cache_files) > 0

    except Exception as e:
        logger.error(f"Failed to verify cache persistence: {e}")
        return False


def migrate_persistent_notifications():
    """Migrate persistent notifications to use cached assets when temp files are gone"""
    try:
        from services.modus import notification_service

        migrated_count = 0
        for cached_notification in notification_service.cached_notifications:
            notification = cached_notification._notification

            # Check if notification has image_pixbuf but temp file might be gone
            if hasattr(notification, "image_pixbuf") and notification.image_pixbuf:
                try:
                    # Try to access pixel data to test if temp file still exists
                    notification.image_pixbuf.get_pixels()
                except Exception:
                    # Temp file is gone, ensure app icon is cached as fallback
                    try:
                        if hasattr(notification, "app_icon") and notification.app_icon:
                            cache_notification_icon(notification.app_icon, (64, 64))
                            migrated_count += 1

                    except Exception as cache_error:
                        logger.debug(
                            f"Failed to cache app icon for {notification.app_name}: {
                                cache_error
                            }"
                        )

    except Exception as e:
        logger.warning(f"Failed to migrate persistent notifications: {e}")


# Initialize cache and verify persistence on module load
ensure_notification_cache_dirs()
cleanup_old_cache_files()
verify_cache_persistence()

# Run migration for persistent notifications on startup
try:
    migrate_persistent_notifications()
except Exception as e:
    logger.debug(f"Migration skipped (service not ready): {e}")


def preload_notification_assets(notification):
    """Preload and cache notification assets with robust error handling for persistent notifications - SINGLE ICON SIZE"""
    try:
        # Cache app icon only at content size (64x64) - scale down for headers at runtime
        if hasattr(notification, "app_icon") and notification.app_icon:
            try:
                # Only cache at 64x64 to reduce disk usage - headers will scale this down
                cache_notification_icon(notification.app_icon, (64, 64))
            except Exception as icon_error:
                logger.debug(
                    f"Failed to preload app icon for {notification.app_name}: {
                        icon_error
                    }"
                )

        # Cache notification image if available
        if hasattr(notification, "image_pixbuf") and notification.image_pixbuf:
            cache_notification_image(
                notification.id, notification.image_pixbuf, (128, 128)
            )

    except Exception as e:
        logger.warning(f"Failed to preload notification assets: {e}")


def smooth_revealer_animation(revealer: SlideRevealer, duration: int = 280):
    """Configure revealer for ultra-smooth animation"""
    revealer.duration = duration


class ActionButton(Button):
    def __init__(
        self, action: NotificationAction, index: int, total: int, notification_box
    ):
        super().__init__(
            name="action-button",
            h_expand=True,
            on_clicked=self.on_clicked,
            child=Label(name="button-label", label=action.label),
        )
        self.action = action
        self.notification_box = notification_box
        style_class = (
            "start-action"
            if index == 0
            else "end-action"
            if index == total - 1
            else "middle-action"
        )
        self.add_style_class(style_class)
        self.connect(
            "enter-notify-event", lambda *_: notification_box.hover_button(self)
        )
        self.connect(
            "leave-notify-event", lambda *_: notification_box.unhover_button(self)
        )

    def on_clicked(self, *_):
        # Mark for cache cleanup when action button is clicked
        self.notification_box._should_cleanup_cache = True
        self.action.invoke()
        self.action.parent.close("dismissed-by-user")


class NotificationWidget(Box):
    def __init__(
        self,
        notification: Notification,
        timeout_ms=None,
        show_close_button=True,
        name="notification",
        **kwargs,
    ):
        # Get current timeout from config manager if not provided
        if timeout_ms is None:
            timeout_ms = self._get_current_notification_timeout()

        self.show_close_button = show_close_button
        self.close_button = None
        self._is_hovered = False
        self.notification_image_cache_key = None  # Track cached image for cleanup
        self.app_icon_source = (
            notification.app_icon
        )  # Track app icon source for cleanup
        self._should_cleanup_cache = False  # Only cleanup cache on manual dismissal

        super().__init__(
            size=(NOTIFICATION_WIDTH, -1),
            name=name,
            orientation="v",
            h_align="fill",
            h_expand=True,
            children=[
                self.create_content(notification),
                self.create_action_buttons(notification),
            ],
        )

        self.notification = notification
        self.timeout_ms = timeout_ms
        self._timeout_id = None

        # Add hover events to the main notification widget
        self.connect("enter-notify-event", self._on_enter_notify)
        self.connect("leave-notify-event", self._on_leave_notify)

        self.start_timeout()

    def create_header(self, notification):
        """Create notification header with optimized cached app icon - SINGLE CACHE SIZE"""
        try:
            # Get 64x64 cached icon and scale down to 24x24 for header
            cached_app_icon_pixbuf = cache_notification_icon(
                notification.app_icon or notification.app_name, (64, 64)
            )

            if cached_app_icon_pixbuf:
                # Scale down the 64x64 cached icon to 24x24 for header display
                header_icon_pixbuf = cached_app_icon_pixbuf.scale_simple(
                    24, 24, GdkPixbuf.InterpType.BILINEAR
                )
                app_icon = ClippingBox(
                    name="notification-icon",
                    children=Image(pixbuf=header_icon_pixbuf),
                )
            else:
                # Fallback to theme icon if caching fails completely
                app_icon = ClippingBox(
                    name="notification-icon",
                    children=Image(
                        icon_name="notifications",
                        icon_size=24,
                    ),
                )
        except Exception as e:
            logger.warning(f"Failed to load cached header icon: {e}")
            # Ultimate fallback
            app_icon = ClippingBox(
                name="notification-icon",
                children=Image(
                    icon_name="notifications",
                    icon_size=24,
                ),
            )

        return CenterBox(
            name="notification-title",
            start_children=[
                Box(
                    spacing=4,
                    children=[
                        app_icon,
                        Label(
                            notification.app_name,
                            name="notification-app-name",
                            h_align="start",
                        ),
                    ],
                )
            ],
            end_children=[
                self.create_close_button() if self.show_close_button else Box()
            ],
        )

    def create_content(self, notification):
        return Box(
            name="notification-content",
            spacing=8,
            children=[
                ClippingBox(
                    name="notification-image",
                    children=Image(pixbuf=self._get_notification_pixbuf(notification)),
                ),
                Box(
                    name="notification-text",
                    orientation="v",
                    v_align="center",
                    children=[
                        Box(
                            name="notification-summary-box",
                            orientation="h",
                            children=[
                                Label(
                                    name="notification-summary",
                                    markup=escape_markup_text(
                                        notification.summary.replace("\n", " ")
                                    ),
                                    h_align="start",
                                    max_chars_width=40,
                                    ellipsization="end",
                                ),
                                # Label(
                                #     name="notification-app-name",
                                #     markup=" | " + notification.app_name,
                                #     h_align="start",
                                #     ellipsization="end",
                                # ),
                            ],
                        ),
                        (
                            Label(
                                markup=escape_markup_text(
                                    notification.body.replace("\n", " ")
                                ),
                                h_align="start",
                                max_chars_width=45,
                                ellipsization="end",
                            )
                            if notification.body
                            else Label(
                                markup="",
                                h_align="start",
                                ellipsization="end",
                            )
                        ),
                    ],
                ),
                Box(h_expand=True),
                Box(
                    orientation="v",
                    children=[
                        Button(
                            name="notification-close-button",
                            image=CustomImage(icon_name="close-symbolic", icon_size=18),
                            visible=True,  # Initially hidden
                            on_clicked=lambda *_: self._manual_close(),
                        ),
                        Box(v_expand=True),
                    ],
                ),
            ],
        )

    def _on_enter_notify(self, widget, event):
        self._is_hovered = True
        if self.close_button:
            self.close_button.set_visible(True)
        self.pause_timeout()
        return False

    def _on_leave_notify(self, widget, event):
        self._is_hovered = False
        if self.close_button:
            self.close_button.set_visible(False)
        self.resume_timeout()
        return False

    def get_pixbuf(self, icon_path, width, height):
        """Get pixbuf with caching support"""
        try:
            # Use the icon caching system
            cached_pixbuf = cache_notification_icon(icon_path, (width, height))
            if cached_pixbuf:
                return cached_pixbuf
        except Exception as e:
            logger.warning(f"Failed to get cached pixbuf for {icon_path}: {e}")

        # Fallback to original method if caching fails
        if icon_path.startswith("file://"):
            icon_path = icon_path[7:]

        if not os.path.exists(icon_path):
            return get_fallback_notification_icon((width, height))

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_path)
            if pixbuf:
                return pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
            else:
                return get_fallback_notification_icon((width, height))
        except Exception as e:
            logger.error(f"Failed to load or scale icon: {e}")
            return get_fallback_notification_icon((width, height))

    def _get_notification_pixbuf(self, notification):
        """Notification pixbuf — loads notification image or app icon, scaled consistently."""
        pixbuf = None

        # 1. Try cache_metadata keys first (cheap — no disk/pixbuf load)
        cache_meta = getattr(notification, "cache_metadata", {}) or {}
        notif_key = cache_meta.get("notification_image_cache_key")
        if notif_key:
            try:
                pixbuf = get_cached_notification_image(notif_key)
            except Exception:
                pass

        # 2. Try notification image via image_pixbuf (only if no cached)
        if not pixbuf:
            try:
                img = getattr(notification, "image_pixbuf", None)
                if img is not None:
                    nid = getattr(notification, "id", 0)
                    ck = get_notification_image_cache_key(nid, img)
                    cached = get_cached_notification_image(ck)
                    if cached:
                        pixbuf = cached
                    else:
                        pixbuf = img
            except Exception:
                pass

        # 3. App icon via cache_metadata
        if not pixbuf:
            app_key = cache_meta.get("app_icon_cache_key")
            if app_key:
                try:
                    from window.notification.unified_cache import get_from_cache

                    pixbuf = get_from_cache(app_key, (64, 64))
                except Exception:
                    pass

        # 4. Direct app icon caching
        if not pixbuf:
            app_icon = getattr(notification, "app_icon", None) or getattr(
                notification, "app_name", None
            )
            if app_icon:
                try:
                    pixbuf = cache_notification_icon(app_icon, (64, 64))
                except Exception:
                    pass

        # 5. Fallback
        if not pixbuf:
            pixbuf = get_fallback_notification_icon((64, 64))

        try:
            return pixbuf.scale_simple(
                NOTIFICATION_IMAGE_SIZE,
                NOTIFICATION_IMAGE_SIZE,
                GdkPixbuf.InterpType.BILINEAR,
            )
        except Exception:
            return pixbuf

    def create_action_buttons(self, notification):
        return Box(
            name="notification-action-buttons",
            spacing=4,
            h_expand=True,
            children=[
                ActionButton(action, i, len(notification.actions), self)
                for i, action in enumerate(notification.actions)
            ],
        )

    def start_timeout(self):
        self.stop_timeout()
        self._timeout_id = GLib.timeout_add(self.timeout_ms, self.close_notification)

    def stop_timeout(self):
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

    def close_notification(self):
        self.notification.close("expired")
        self.stop_timeout()
        return False

    def pause_timeout(self):
        self.stop_timeout()

    def resume_timeout(self):
        if not self._is_hovered:  # Only resume if not hovered
            self.start_timeout()

    def _manual_close(self):
        """Handle manual close button click - just close notification"""
        self.notification.close("dismissed-by-user")

    def destroy(self):
        self.stop_timeout()
        # Only clean up caches if this was a manual dismissal
        if self._should_cleanup_cache:
            cleanup_notification_specific_caches(
                app_icon_source=getattr(self, "app_icon_source", None),
                notification_image_cache_key=getattr(
                    self, "notification_image_cache_key", None
                ),
            )
        else:
            logger.debug("Preserved caches for timeout/auto-dismissed notification")
        super().destroy()

    # @staticmethod
    def set_pointer_cursor(self, widget, cursor_name):
        window = widget.get_window()
        if window:
            cursor = Gdk.Cursor.new_from_name(widget.get_display(), cursor_name)
            window.set_cursor(cursor)

    def hover_button(self, button):
        self.pause_timeout()
        self.set_pointer_cursor(button, "hand2")

    def unhover_button(self, button):
        # Don't resume timeout here since the notification itself might still be hovered
        self.set_pointer_cursor(button, "arrow")

    @staticmethod
    def _get_current_notification_timeout():
        """Get the current notification timeout from config manager."""
        try:
            timeout_str = get_config(
                "notification_timeout", data.NOTIFICATION_TIMEOUT_STR
            )
            from shared.data import parse_timeout_string

            return parse_timeout_string(timeout_str)
        except Exception as e:
            logger.warning(f"Failed to get notification timeout from config: {e}")
            return data.NOTIFICATION_TIMEOUT


class NotificationRevealer(SlideRevealer):
    def __init__(
        self,
        notification: Notification,
        on_transition_end=None,
        parent_window=None,
        **kwargs,
    ):
        self.notif_box = NotificationWidget(notification, show_close_button=False)
        self.notification = notification
        self.on_transition_end = on_transition_end
        # Reference to NotificationCenter window for queue clearing
        self.parent_window = parent_window
        self._is_closing = False

        # Enhanced swipe detection variables for Android-style animation
        self._drag_start_y = 0
        self._drag_start_x = 0
        self._is_dragging = False
        self._swipe_threshold = 80  # Distance to trigger auto-dismiss
        self._swipe_velocity_threshold = (
            150  # Velocity to trigger dismiss even on shorter swipes
        )
        self._swipe_in_progress = False
        self._current_offset = 0
        self._last_drag_time = 0
        self._drag_velocity = 0
        self._spring_back_duration = 200  # Duration for spring-back animation
        self._dismiss_threshold = 0.3  # Dismiss if swiped 30% of width

        # Animation state
        self._animation_in_progress = False
        self._spring_timer_id = None
        self._anim_timeout_id = None
        self._css_provider = None

        # Wrap notification in EventBox for swipe detection
        self.event_box = EventBox(
            events=[
                "button-press-event",
                "button-release-event",
                "motion-notify-event",
            ],
            child=self.notif_box,
        )

        super().__init__(
            child=self.event_box,
            direction="right",
            duration=280,  # Faster, smoother duration
        )

        smooth_revealer_animation(self)

        # Connect our own handler that manages the slide animation - track ID for cleanup
        self._closed_handler_id = self.notification.connect("closed", self.on_resolved)

        self._animation_in_progress = True

    def _ease_out_cubic(self, t):
        """Smoother easing function for better animation quality"""
        return 1 - pow(1 - t, 3)

    def _ease_out_quart(self, t):
        """Even smoother easing for ultra-smooth animations"""
        return 1 - pow(1 - t, 4)

    def _apply_transform(self, offset_x, opacity, scale):
        """Apply smooth CSS transforms for animation"""
        try:
            # Create CSS transformation
            transform_css = f"""
                opacity: {opacity};
                transform: translateX({offset_x}px) scale({scale});
                transition: none;
            """

            # Apply to the notification box
            if hasattr(self.notif_box, "get_style_context"):
                style_context = self.notif_box.get_style_context()
                if style_context:
                    # Use CSS provider for smooth transforms
                    if not hasattr(self, "_css_provider") or not self._css_provider:
                        self._css_provider = Gtk.CssProvider()
                        style_context.add_provider(
                            self._css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                        )

                    css_data = f"* {{ {transform_css} }}"
                    self._css_provider.load_from_data(css_data.encode())

        except Exception as e:
            logger.debug(f"Transform apply failed (non-critical): {e}")

    def _animate_dismiss(self, start_offset):
        """Animate the notification sliding out with smooth 60fps animation"""
        target_offset = NOTIFICATION_WIDTH + 50
        duration = 200  # Slightly longer for smoother feel

        if self._spring_timer_id:
            GLib.source_remove(self._spring_timer_id)

        start_time = GLib.get_monotonic_time() / 1000
        offset_diff = target_offset - start_offset

        def animate_step():
            current_time = GLib.get_monotonic_time() / 1000
            elapsed = current_time - start_time
            progress = min(1.0, elapsed / duration)

            # Use smoother easing for premium feel
            eased_progress = self._ease_out_quart(progress)
            current_offset = start_offset + (offset_diff * eased_progress)

            # Smoother fade and scale transitions
            opacity = max(0.0, 1.0 - (progress * 0.9))  # Gentler fade
            scale = max(0.9, 1.0 - (progress * 0.1))  # Subtle scale

            self._apply_transform(current_offset, opacity, scale)

            if progress >= 1.0:
                # Mark notification for cache cleanup on swipe dismissal
                self.notif_box._should_cleanup_cache = True
                try:
                    self.notification.close("dismissed-by-user")
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                return False

            return True

        # Use consistent 60fps timing
        self._animation_in_progress = True
        self._spring_timer_id = GLib.timeout_add(16, animate_step)  # ~60 FPS

    def _calculate_drag_velocity(self, current_x):
        """Calculate the velocity of the drag gesture"""
        current_time = GLib.get_monotonic_time() / 1000

        if self._last_drag_time > 0:
            time_diff = current_time - self._last_drag_time
            if time_diff > 0:
                distance_diff = current_x - self._drag_start_x - self._current_offset
                self._drag_velocity = abs(distance_diff / time_diff)

        self._last_drag_time = current_time

    def _on_animation_complete(self, is_hiding=False):
        if is_hiding:
            # Manually destroy the notification widget since we disconnected its handler
            self.notif_box.destroy()

            if self.on_transition_end:
                self.on_transition_end()
            self.destroy()

    def on_resolved(
        self,
        _notification: Notification,
        reason: NotificationCloseReason,
    ):
        if self._is_closing:
            return

        self._is_closing = True

        # Clean up any ongoing animations
        if self._spring_timer_id:
            GLib.source_remove(self._spring_timer_id)

        # Use different slide directions based on dismiss reason
        if reason == "expired":
            # Gentle fade-out for auto-dismiss
            self.set_slide_direction("left")
            self.duration = 250  # Slightly slower for natural feel
        elif self._swipe_in_progress:
            # Quick slide for swipe dismissals
            self.duration = 150
            self.set_slide_direction("right")
        else:
            # Smooth slide for manual close
            self.set_slide_direction("right")
            self.duration = 200

        self.hide()
        # Consistent timing for smooth transitions
        timeout_duration = self.duration + 50
        self._anim_timeout_id = GLib.timeout_add(
            timeout_duration, lambda: self._on_animation_complete(True)
        )

    def destroy(self):
        # Clean up CSS provider and timers
        if self._spring_timer_id:
            GLib.source_remove(self._spring_timer_id)
            self._spring_timer_id = None
        if self._anim_timeout_id:
            GLib.source_remove(self._anim_timeout_id)
            self._anim_timeout_id = None

        # Disconnect notification signal
        if hasattr(self, "_closed_handler_id") and self._closed_handler_id:
            try:
                self.notification.disconnect(self._closed_handler_id)
            except Exception as e:
                logger.error(f"An error occurred: {e}")
            self._closed_handler_id = 0

        # Clean up CSS provider from style context
        if self._css_provider:
            try:
                style_context = self.notif_box.get_style_context()
                if style_context:
                    style_context.remove_provider(self._css_provider)
            except Exception as e:
                logger.error(f"An error occurred: {e}")
            self._css_provider = None

        super().destroy()


class NotificationState:
    IDLE = 0
    SHOWING = 1
    HIDING = 2
    TRANSITIONING = 3  # New state for smooth transitions


class ModusNoti(Window):
    def __init__(self):
        # Local config state mirroring services.config usage
        self._current_config = {
            "notification_timeout": data.NOTIFICATION_TIMEOUT_STR,
            "notification_ignored_apps": data.NOTIFICATION_IGNORED_APPS_HISTORY,
            "notification_limited_apps_history": data.NOTIFICATION_LIMITED_APPS_HISTORY,
        }

        # Subscribe to config changes and apply initial config
        on_config_change(self._on_config_changed)
        self._apply_initial_config()

        self._server = notification_service

        self.notifications = Box(
            v_expand=True,
            h_expand=True,
            style="margin: 1px 0px 1px 1px;",
            orientation="v",
            spacing=5,
        )

        # Enhanced queue system for ultra-smooth transitions
        self.notification_queue = []
        self.current_notification = None
        self.notification_state = NotificationState.IDLE
        self._transition_timer_id = None
        self._debounce_timer_id = None
        self._last_notification_time = 0

        # Queue management settings for smooth behavior
        self.MAX_QUEUE_SIZE = 3  # Limit queue to prevent overwhelming
        self.TRANSITION_DELAY = 100  # Smoother transition timing
        self.DEBOUNCE_DELAY = 50  # Prevent rapid fire notifications

        self._server.connect("notification-added", self.on_new_notification)
        Window.__init__(
            self,
            anchor="top right",
            child=self.notifications,
            layer="overlay",
            title="modus-notifications",  # More specific title for debugging
            all_visible=True,
            visible=False,  # Start hidden, show only when we have content
            exclusive=False,
        )

    def on_new_notification(self, fabric_notif, id):
        notification: Notification = fabric_notif.get_notification_from_id(id)

        # Check if notification still exists (might have been removed already)
        if not notification:
            return

        if self._server.dont_disturb or modus_service.dont_disturb:
            # Notification is already cached by the service, just don't show popup
            return

        # Check if notification should be ignored based on current config
        if self._should_ignore_notification(notification):
            return

        # Preload assets immediately for optimal caching and display performance
        preload_notification_assets(notification)

        # Implement smart queue management for smooth transitions
        GLib.get_monotonic_time() / 1000

        # If queue is getting full, remove oldest notifications smoothly
        if len(self.notification_queue) >= self.MAX_QUEUE_SIZE:
            # Remove oldest notification from queue (not current showing one)
            if self.notification_queue:
                oldest = self.notification_queue.pop(0)
                try:
                    oldest.close("dismissed-by-user")
                except Exception as e:
                    logger.error(f"An error occurred: {e}")

        # Add new notification to queue
        self.notification_queue.append(notification)

        # Debounce rapid notifications for smoother experience
        if self._debounce_timer_id:
            GLib.source_remove(self._debounce_timer_id)

        self._debounce_timer_id = GLib.timeout_add(
            self.DEBOUNCE_DELAY,
            lambda: self._process_notification_queue_debounced() or False,
        )

    def _process_notification_queue_debounced(self):
        """Process queue after debounce delay for smooth transitions"""
        self._debounce_timer_id = None
        self._process_notification_queue()
        return False

    def _process_notification_queue(self):
        # If we're currently showing a notification and there's a new one in queue
        if (
            self.notification_state == NotificationState.SHOWING
            and self.current_notification
            and self.notification_queue
        ):
            # Smooth transition: start hiding current notification
            self.notification_state = NotificationState.TRANSITIONING
            self._start_smooth_transition()

        elif (
            self.notification_state == NotificationState.IDLE
            and self.notification_queue
        ):
            # If we're idle and have notifications in queue, show the next one
            self._show_next_notification()

    def _start_smooth_transition(self):
        """Start smooth transition between notifications"""
        if self.current_notification and not self.current_notification._is_closing:
            # Don't mark for cache cleanup during smooth transitions
            # to maintain performance

            # Use shorter timeout for smooth transitions
            self.current_notification.notif_box.timeout_ms = 100

            # Force close current notification with smooth animation
            try:
                self.current_notification.notification.close("expired")
            except Exception as e:
                logger.error(f"An error occurred: {e}")

    def _show_next_notification(self):
        if (
            not self.notification_queue
            or self.notification_state != NotificationState.IDLE
        ):
            return

        notification = self.notification_queue.pop(0)

        # Check if notification is still valid (might have been removed)
        if not notification or not hasattr(notification, "app_icon"):
            # Skip invalid notifications and try next one
            if self.notification_queue:
                self._show_next_notification()
            return

        self.notification_state = NotificationState.SHOWING

        new_box = NotificationRevealer(
            notification,
            on_transition_end=lambda: self._on_notification_finished(new_box),
            parent_window=self,
        )

        self.current_notification = new_box

        # Clear and destroy any existing children
        for child in list(self.notifications.children):
            try:
                self.notifications.remove(child)
                child.destroy()
            except Exception as e:
                logger.error(f"An error occurred: {e}")

        self.notifications.children = [new_box]

        # Show the window now that we have content to display
        self.set_visible(True)

        new_box.show()
        self.notifications.queue_resize()

        def start_animation():
            if new_box.get_parent() and new_box.get_realized():
                new_box.reveal()
                return False
            return True

        GLib.idle_add(start_animation)

    def _on_notification_finished(self, notification_box):
        if notification_box != self.current_notification:
            return

        # Cancel any pending transition timer
        if self._transition_timer_id:
            GLib.source_remove(self._transition_timer_id)
            self._transition_timer_id = None

        # Safely remove and destroy notification box
        try:
            if notification_box in self.notifications.children:
                self.notifications.remove(notification_box)
            notification_box.destroy()
        except Exception as e:
            logger.error(f"An error occurred: {e}")

        # Reset state
        self.current_notification = None
        self.notification_state = NotificationState.IDLE

        # Process next notification with optimized delay for ultra-smooth transitions
        if self.notification_queue:
            self._transition_timer_id = GLib.timeout_add(
                self.TRANSITION_DELAY,  # Consistent smooth timing
                lambda: self._show_next_notification() or False,
            )
        else:
            # Hide window when no more notifications to show
            self.set_visible(False)

    def show_next_notification(self):
        # Legacy method for compatibility - redirect to new implementation
        self._show_next_notification()

    def on_notification_finished(self, notification_box):
        # Legacy method for compatibility - redirect to new implementation
        self._on_notification_finished(notification_box)

    def clear_notification_queue(self):
        """Clear queue with smooth cleanup"""
        queue_length = len(self.notification_queue)
        if queue_length > 0:
            # Smooth dismissal of queued notifications
            for notification in list(self.notification_queue):
                try:
                    notification.close("dismissed-by-user")
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
            self.notification_queue.clear()

        # Also clean current notification if showing
        if self.current_notification:
            self.current_notification.notif_box._should_cleanup_cache = True
            try:
                self.current_notification.notification.close("dismissed-by-user")
            except Exception as e:
                logger.error(f"An error occurred: {e}")

        # Clear animation timers
        if self._transition_timer_id:
            GLib.source_remove(self._transition_timer_id)
            self._transition_timer_id = None

        if self._debounce_timer_id:
            GLib.source_remove(self._debounce_timer_id)
            self._debounce_timer_id = None

    def get_queue_length(self):
        return len(self.notification_queue)

    def _should_ignore_notification(self, notification):
        """Check if notification should be ignored based on current config."""
        try:
            ignored_apps = self._current_config.get("notification_ignored_apps", [])
            app_name = getattr(notification, "app_name", "")

            # Check if app name is in ignored list
            return app_name in ignored_apps
        except Exception as e:
            logger.warning(f"Failed to check if notification should be ignored: {e}")
            return False

    def update_config(self, new_config):
        """Update notification configuration dynamically."""
        try:
            # Handle notification timeout changes
            if "notification_timeout" in new_config:
                timeout_str = new_config["notification_timeout"]
                # Parse the timeout string to milliseconds

                parse_timeout_string(timeout_str)

            # Handle ignored apps changes
            if "notification_ignored_apps" in new_config:
                new_config["notification_ignored_apps"]

            # Handle limited apps history changes
            if "notification_limited_apps_history" in new_config:
                new_config["notification_limited_apps_history"]

            # Update the current config
            self._current_config.update(new_config)

        except Exception as e:
            logger.error(f"[ModusNoti] Failed to update config: {e}")

    def _apply_initial_config(self):
        try:
            timeout_val = get_config(
                "notification_timeout", data.NOTIFICATION_TIMEOUT_STR
            )
            ignored_apps = get_config(
                "notification_ignored_apps", data.NOTIFICATION_IGNORED_APPS_HISTORY
            )
            limited_apps = get_config(
                "notification_limited_apps_history",
                data.NOTIFICATION_LIMITED_APPS_HISTORY,
            )
            initial = {
                "notification_timeout": timeout_val,
                "notification_ignored_apps": ignored_apps,
                "notification_limited_apps_history": limited_apps,
            }
            # Only apply if different
            self.update_config(initial)
        except Exception as e:
            logger.error(f"[ModusNoti] Failed to apply initial config: {e}")

    def _on_config_changed(self, new_config: dict, old_config: dict):
        try:
            changes = {}
            for key in (
                "notification_timeout",
                "notification_ignored_apps",
                "notification_limited_apps_history",
            ):
                if key in new_config and new_config.get(key) != old_config.get(key):
                    changes[key] = new_config.get(key)

            if changes:
                self.update_config(changes)
        except Exception as e:
            logger.error(f"[ModusNoti] Error handling config change: {e}")
