import os
import hashlib
import time

from fabric.utils import get_relative_path
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # type: ignore
from loguru import logger

import config.data as data
from fabric.notifications import (
    Notification,
    NotificationAction,
    NotificationCloseReason,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from utils.roam import modus_service
from widgets.custom_image import CustomImage
from widgets.customrevealer import SlideRevealer
from widgets.wayland import WaylandWindow as Window
from services.modus import notification_service

NOTIFICATION_WIDTH = 360
NOTIFICATION_IMAGE_SIZE = 48

NOTIFICATION_WIDTH = 360
NOTIFICATION_IMAGE_SIZE = 48

# Notification icon cache directory (for small notification and app icons)
NOTIFICATION_ICON_CACHE_DIR = os.path.join(data.CACHE_DIR, "notification_icons")
# Notification image cache directory (for large notification images)
NOTIFICATION_IMAGE_CACHE_DIR = os.path.join(data.CACHE_DIR, "notification_images")

def ensure_notification_cache_dirs():
    """Ensure notification cache directories exist"""
    os.makedirs(NOTIFICATION_ICON_CACHE_DIR, exist_ok=True)
    os.makedirs(NOTIFICATION_IMAGE_CACHE_DIR, exist_ok=True)

def cleanup_old_cache_files():
    """Clean up old notification cache files (older than 7 days) from icon cache only"""
    try:
        if not os.path.exists(NOTIFICATION_ICON_CACHE_DIR):
            return

        current_time = time.time()
        week_ago = current_time - (7 * 24 * 60 * 60)  # 7 days

        for filename in os.listdir(NOTIFICATION_ICON_CACHE_DIR):
            filepath = os.path.join(NOTIFICATION_ICON_CACHE_DIR, filename)
            try:
                if os.path.isfile(filepath):
                    file_mtime = os.path.getmtime(filepath)
                    if file_mtime < week_ago:
                        os.unlink(filepath)
                        logger.debug(f"Cleaned up old notification icon cache: {filename}")
            except Exception as e:
                logger.warning(f"Failed to cleanup cache file {filename}: {e}")
    except Exception as e:
        logger.warning(f"Failed to cleanup notification cache: {e}")

def get_cache_key(source_data, size=None):
    """Generate a cache key from source data and optional size"""
    if isinstance(source_data, str):
        # For file paths
        cache_input = source_data
        if size:
            cache_input += f"_{size[0]}x{size[1]}"
    else:
        # For pixbuf data - use hash of pixel data
        try:
            pixel_data = source_data.get_pixels()
            cache_input = hashlib.md5(pixel_data).hexdigest()
            if size:
                cache_input += f"_{size[0]}x{size[1]}"
        except Exception:
            # Fallback to timestamp if pixel data fails
            cache_input = f"pixbuf_{int(time.time())}"
    
    return hashlib.md5(cache_input.encode()).hexdigest()

def save_pixbuf_to_cache(pixbuf, cache_key, cache_dir):
    """Save a pixbuf to the specified cache directory"""
    try:
        ensure_notification_cache_dirs()
        cache_path = os.path.join(cache_dir, f"{cache_key}.png")
        
        # Don't overwrite existing cache
        if os.path.exists(cache_path):
            return cache_path
            
        pixbuf.savev(cache_path, "png", [], [])
        logger.debug(f"Cached notification icon: {cache_key}")
        return cache_path
    except Exception as e:
        logger.warning(f"Failed to cache notification icon: {e}")
        return None

def get_cached_pixbuf(cache_key, fallback_size=(48, 48), cache_dir=None):
    """Get a cached pixbuf or return None if not found"""
    if cache_dir is None:
        cache_dir = NOTIFICATION_ICON_CACHE_DIR
        
    try:
        cache_path = os.path.join(cache_dir, f"{cache_key}.png")
        if os.path.exists(cache_path):
            logger.debug(f"Using cached notification icon: {cache_key}")
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                cache_path, fallback_size[0], fallback_size[1], True
            )
    except Exception as e:
        logger.warning(f"Failed to load cached notification icon: {e}")
    return None

def cache_notification_icon(source, size=(48, 48)):
    """Cache a notification icon from local sources (file, pixbuf) - PERMANENT cache"""
    try:
        ensure_notification_cache_dirs()
        
        # Handle different source types
        if isinstance(source, str):
            cache_key = get_cache_key(source, size)
            
            # Check if already cached
            cached_pixbuf = get_cached_pixbuf(cache_key, size, NOTIFICATION_ICON_CACHE_DIR)
            if cached_pixbuf:
                return cached_pixbuf
            
            # Load and cache the icon (local only)
            if source.startswith('file://'):
                # Local file URL
                file_path = source[7:]
                pixbuf = load_and_cache_local_icon(file_path, cache_key, size)
            elif os.path.exists(source):
                # Direct file path
                pixbuf = load_and_cache_local_icon(source, cache_key, size)
            else:
                # Icon name - try to resolve from theme
                pixbuf = load_and_cache_theme_icon(source, cache_key, size)
                
            return pixbuf
            
        elif hasattr(source, 'scale_simple'):
            # Already a pixbuf
            cache_key = get_cache_key(source, size)
            
            # Check if already cached
            cached_pixbuf = get_cached_pixbuf(cache_key, size, NOTIFICATION_ICON_CACHE_DIR)
            if cached_pixbuf:
                return cached_pixbuf
            
            # Scale and cache
            scaled_pixbuf = source.scale_simple(size[0], size[1], GdkPixbuf.InterpType.BILINEAR)
            save_pixbuf_to_cache(scaled_pixbuf, cache_key, NOTIFICATION_ICON_CACHE_DIR)
            return scaled_pixbuf
            
    except Exception as e:
        logger.warning(f"Failed to cache notification icon: {e}")
    
    # Return fallback
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
        icon_theme = Gtk.IconTheme.get_default()
        icon_info = icon_theme.lookup_icon(icon_name, min(size), 0)
        
        if icon_info:
            pixbuf = icon_info.load_icon()
            if pixbuf:
                scaled_pixbuf = pixbuf.scale_simple(size[0], size[1], GdkPixbuf.InterpType.BILINEAR)
                save_pixbuf_to_cache(scaled_pixbuf, cache_key, NOTIFICATION_ICON_CACHE_DIR)
                return scaled_pixbuf
    except Exception as e:
        logger.warning(f"Failed to load theme notification icon {icon_name}: {e}")
    
    return get_fallback_notification_icon(size)

def get_fallback_notification_icon(size=(48, 48)):
    """Get the fallback notification icon"""
    try:
        fallback_path = get_relative_path("../../config/assets/icons/notification.png")
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(
            fallback_path, size[0], size[1], True
        )
    except Exception as e:
        logger.warning(f"Failed to load fallback notification icon: {e}")
        # Create a simple colored rectangle as ultimate fallback
        try:
            return GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, size[0], size[1])
        except:
            return None

def get_notification_image_cache_key(notification_id, image_pixbuf):
    """Generate a cache key for notification images"""
    try:
        # Use notification ID and image hash for unique key
        if hasattr(image_pixbuf, 'get_pixels'):
            pixel_data = image_pixbuf.get_pixels()
            image_hash = hashlib.md5(pixel_data).hexdigest()[:8]
        else:
            image_hash = str(int(time.time()))
        return f"notif_{notification_id}_{image_hash}"
    except Exception:
        return f"notif_{notification_id}_{int(time.time())}"

def cache_notification_image(notification_id, image_pixbuf, size=(64, 64)):
    """Cache a notification image pixbuf - PERMANENT cache until manual clear"""
    try:
        ensure_notification_cache_dirs()
        
        cache_key = get_notification_image_cache_key(notification_id, image_pixbuf)
        cache_path = os.path.join(NOTIFICATION_IMAGE_CACHE_DIR, f"{cache_key}.png")
        
        # Don't overwrite existing cache
        if os.path.exists(cache_path):
            return cache_path, cache_key
            
        # Scale and save the image
        scaled_pixbuf = image_pixbuf.scale_simple(size[0], size[1], GdkPixbuf.InterpType.BILINEAR)
        scaled_pixbuf.savev(cache_path, "png", [], [])
        logger.debug(f"Cached notification image: {cache_key}")
        return cache_path, cache_key
    except Exception as e:
        logger.warning(f"Failed to cache notification image: {e}")
        return None, None

def get_cached_notification_image(cache_key):
    """Get a cached notification image or return None if not found"""
    try:
        cache_path = os.path.join(NOTIFICATION_IMAGE_CACHE_DIR, f"{cache_key}.png")
        if os.path.exists(cache_path):
            logger.debug(f"Using cached notification image: {cache_key}")
            return GdkPixbuf.Pixbuf.new_from_file(cache_path)
    except Exception as e:
        logger.warning(f"Failed to load cached notification image: {e}")
    return None

def cleanup_notification_image_cache(cache_key=None):
    """Clean up notification image cache - specific key or all"""
    try:
        ensure_notification_cache_dirs()
        
        if cache_key:
            # Remove specific cached image
            cache_path = os.path.join(NOTIFICATION_IMAGE_CACHE_DIR, f"{cache_key}.png")
            if os.path.exists(cache_path):
                os.unlink(cache_path)
                logger.debug(f"Cleaned up cached notification image: {cache_key}")
        else:
            # Remove all cached images
            for filename in os.listdir(NOTIFICATION_IMAGE_CACHE_DIR):
                if filename.endswith('.png'):
                    filepath = os.path.join(NOTIFICATION_IMAGE_CACHE_DIR, filename)
                    try:
                        os.unlink(filepath)
                        logger.debug(f"Cleaned up cached notification image: {filename}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup cache file {filename}: {e}")
    except Exception as e:
        logger.warning(f"Failed to cleanup notification image cache: {e}")

def cleanup_notification_specific_caches(app_icon_source=None, notification_image_cache_key=None):
    """Clean up caches specific to a notification (both app icon and notification image)"""
    try:
        # Clean up notification image cache
        if notification_image_cache_key:
            cleanup_notification_image_cache(notification_image_cache_key)
        
        # Clean up app icon cache for this specific source
        if app_icon_source:
            cache_key = get_cache_key(app_icon_source, (24, 24))  # Standard app icon size
            cache_path = os.path.join(NOTIFICATION_ICON_CACHE_DIR, f"{cache_key}.png")
            if os.path.exists(cache_path):
                os.unlink(cache_path)
                logger.debug(f"Cleaned up cached app icon: {cache_key}")
            
            # Also clean 35x35 version used in notifications
            cache_key_35 = get_cache_key(app_icon_source, (35, 35))
            cache_path_35 = os.path.join(NOTIFICATION_ICON_CACHE_DIR, f"{cache_key_35}.png")
            if os.path.exists(cache_path_35):
                os.unlink(cache_path_35)
                logger.debug(f"Cleaned up cached app icon (35x35): {cache_key_35}")
                
    except Exception as e:
        logger.warning(f"Failed to cleanup notification specific caches: {e}")

def cleanup_all_notification_caches():
    """Clean up ALL notification caches (icons and images)"""
    try:
        # Clean icon cache
        if os.path.exists(NOTIFICATION_ICON_CACHE_DIR):
            for filename in os.listdir(NOTIFICATION_ICON_CACHE_DIR):
                if filename.endswith('.png'):
                    filepath = os.path.join(NOTIFICATION_ICON_CACHE_DIR, filename)
                    try:
                        os.unlink(filepath)
                        logger.debug(f"Cleaned up cached notification icon: {filename}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup icon cache file {filename}: {e}")
        
        # Clean image cache  
        cleanup_notification_image_cache()
        logger.info("Cleaned up all notification caches")
    except Exception as e:
        logger.warning(f"Failed to cleanup all notification caches: {e}")

# Initialize cache on module load
ensure_notification_cache_dirs()
cleanup_old_cache_files()


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
            else "end-action" if index == total - 1 else "middle-action"
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
        timeout_ms=data.NOTIFICATION_TIMEOUT,
        show_close_button=True,
        **kwargs,
    ):
        self.show_close_button = show_close_button
        self.close_button = None
        self._is_hovered = False
        self.notification_image_cache_key = None  # Track cached image for cleanup
        self.app_icon_source = notification.app_icon  # Track app icon source for cleanup
        self._should_cleanup_cache = False  # Only cleanup cache on manual dismissal

        super().__init__(
            size=(NOTIFICATION_WIDTH, -1),
            name="notification",
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
        app_icon = (
            Image(
                name="notification-icon",
                image_file=notification.app_icon[7:],
                size=24,
            )
            if "file://" in notification.app_icon
            else Image(
                name="notification-icon",
                icon_name="notifications" or notification.app_icon,
                icon_size=24,
            )
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
                Box(
                    name="notification-image",
                    children=CustomImage(
                        pixbuf=self._get_notification_pixbuf(notification)
                    ),
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
                                    markup=notification.summary.replace("\n", " "),
                                    h_align="start",
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
                                markup=notification.body.replace("\n", " "),
                                h_align="start",
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
            logger.warning(f"Icon path does not exist: {icon_path}")
            return get_fallback_notification_icon((width, height))

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_path)
            return pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
        except Exception as e:
            logger.error(f"Failed to load or scale icon: {e}")
            return get_fallback_notification_icon((width, height))

    def _get_notification_pixbuf(self, notification):
        """Safely get notification pixbuf with caching for image notifications"""
        try:
            if hasattr(notification, 'image_pixbuf') and notification.image_pixbuf:
                # Try to get/cache the notification image
                notification_id = getattr(notification, 'id', int(time.time()))
                cache_path, cache_key = cache_notification_image(
                    notification_id, notification.image_pixbuf, (64, 64)
                )
                
                if cache_path and cache_key:
                    # Store cache key for reference (but don't auto-delete)
                    self.notification_image_cache_key = cache_key
                    # Load the cached image
                    cached_pixbuf = get_cached_notification_image(cache_key)
                    if cached_pixbuf:
                        return cached_pixbuf.scale_simple(35, 35, GdkPixbuf.InterpType.BILINEAR)
                
                # Fallback to direct scaling if caching fails
                return notification.image_pixbuf.scale_simple(
                    35, 35, GdkPixbuf.InterpType.BILINEAR
                )
        except Exception as e:
            logger.warning(f"Failed to get notification image: {e}")
        
        # Fallback to cached app icon
        try:
            cached_app_icon = cache_notification_icon(notification.app_icon, (35, 35))
            if cached_app_icon:
                return cached_app_icon
        except Exception as e:
            logger.warning(f"Failed to get cached app icon: {e}")
        
        # Ultimate fallback
        return get_fallback_notification_icon((35, 35))

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
        """Handle manual close button click - mark for cache cleanup"""
        self._should_cleanup_cache = True
        self.notification.close("dismissed-by-user")

    def destroy(self):
        self.stop_timeout()
        # Only clean up caches if this was a manual dismissal
        if self._should_cleanup_cache:
            cleanup_notification_specific_caches(
                app_icon_source=getattr(self, 'app_icon_source', None),
                notification_image_cache_key=getattr(self, 'notification_image_cache_key', None)
            )
            logger.debug(f"Cleaned up caches for manually dismissed notification")
        else:
            logger.debug(f"Preserved caches for timeout/auto-dismissed notification")
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

        # Connect our own handler that manages the slide animation
        self.notification.connect("closed", self.on_resolved)

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
            if hasattr(self.notif_box, 'get_style_context'):
                style_context = self.notif_box.get_style_context()
                if style_context:
                    # Use CSS provider for smooth transforms
                    if not hasattr(self, '_css_provider') or not self._css_provider:
                        from gi.repository import Gtk
                        self._css_provider = Gtk.CssProvider()
                        style_context.add_provider(
                            self._css_provider, 
                            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
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
            scale = max(0.9, 1.0 - (progress * 0.1))   # Subtle scale

            self._apply_transform(current_offset, opacity, scale)

            if progress >= 1.0:
                # Mark notification for cache cleanup on swipe dismissal
                self.notif_box._should_cleanup_cache = True
                try:
                    self.notification.close("dismissed-by-user")
                except:
                    pass
                return False

            return True

        # Use consistent 60fps timing
        self._animation_in_progress = True
        self._spring_timer_id = GLib.timeout_add(
            16, animate_step  # ~60 FPS
        )

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
        GLib.timeout_add(timeout_duration, lambda: self._on_animation_complete(True))

    def destroy(self):
        # Clean up CSS provider and timers
        if self._spring_timer_id:
            GLib.source_remove(self._spring_timer_id)
        super().destroy()


class NotificationState:
    IDLE = 0
    SHOWING = 1
    HIDING = 2
    TRANSITIONING = 3  # New state for smooth transitions


class ModusNoti(Window):
    def __init__(self):
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

        # Initialize ignored apps list from config
        self.ignored_apps = data.NOTIFICATION_IGNORED_APPS

        self._server.connect("notification-added", self.on_new_notification)
        super().__init__(
            anchor="top right",
            child=self.notifications,
            layer="overlay",
            title="noti",
            all_visible=True,
            visible=True,
            exclusive=False,
        )

    def on_new_notification(self, fabric_notif, id):
        notification: Notification = fabric_notif.get_notification_from_id(id)

        # Check if the notification should be ignored completely (ignored apps)
        if notification.app_name in self.ignored_apps:
            return

        if self._server.dont_disturb or modus_service.dont_disturb:
            # Notification is already cached by the service, just don't show popup
            return

        # Implement smart queue management for smooth transitions
        current_time = GLib.get_monotonic_time() / 1000
        
        # If queue is getting full, remove oldest notifications smoothly
        if len(self.notification_queue) >= self.MAX_QUEUE_SIZE:
            # Remove oldest notification from queue (not current showing one)
            if self.notification_queue:
                oldest = self.notification_queue.pop(0)
                try:
                    oldest.close("dismissed-by-user")
                except:
                    pass

        # Add new notification to queue
        self.notification_queue.append(notification)
        
        # Debounce rapid notifications for smoother experience
        if self._debounce_timer_id:
            GLib.source_remove(self._debounce_timer_id)
            
        self._debounce_timer_id = GLib.timeout_add(
            self.DEBOUNCE_DELAY, 
            lambda: self._process_notification_queue_debounced() or False
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
        if (
            self.current_notification
            and not self.current_notification._is_closing
        ):
            # Don't mark for cache cleanup during smooth transitions
            # to maintain performance
            
            # Use shorter timeout for smooth transitions
            self.current_notification.notif_box.timeout_ms = 100
            
            # Force close current notification with smooth animation
            try:
                self.current_notification.notification.close("expired")
            except:
                pass

    def _show_next_notification(self):
        if (
            not self.notification_queue
            or self.notification_state != NotificationState.IDLE
        ):
            return

        notification = self.notification_queue.pop(0)
        self.notification_state = NotificationState.SHOWING

        new_box = NotificationRevealer(
            notification,
            on_transition_end=lambda: self._on_notification_finished(new_box),
            parent_window=self,
        )

        self.current_notification = new_box

        # Clear any existing children
        for child in list(self.notifications.children):
            try:
                self.notifications.remove(child)
            except:
                pass

        self.notifications.children = [new_box]
        new_box.show_all()
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

        # Safely remove notification box
        try:
            if notification_box in self.notifications.children:
                self.notifications.remove(notification_box)
        except:
            pass

        # Reset state
        self.current_notification = None
        self.notification_state = NotificationState.IDLE

        # Process next notification with optimized delay for ultra-smooth transitions
        if self.notification_queue:
            self._transition_timer_id = GLib.timeout_add(
                self.TRANSITION_DELAY,  # Consistent smooth timing
                lambda: self._show_next_notification() or False,
            )

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
                except:
                    pass
            self.notification_queue.clear()

        # Also clean current notification if showing
        if self.current_notification:
            # Mark for cache cleanup when clearing queue
            self.current_notification.notif_box._should_cleanup_cache = True

        # Clear animation timers
        if self._transition_timer_id:
            GLib.source_remove(self._transition_timer_id)
            self._transition_timer_id = None
            
        if self._debounce_timer_id:
            GLib.source_remove(self._debounce_timer_id)
            self._debounce_timer_id = None

    def get_queue_length(self):
        return len(self.notification_queue)
