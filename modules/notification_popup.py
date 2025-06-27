import json
import locale
import os
import uuid
from datetime import datetime, timedelta

from fabric.notifications.service import Notification, NotificationAction, Notifications
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GdkPixbuf, GLib, Gtk
from loguru import logger

import config.data as data
import utils.icons as icons
from utils.custom_image import CustomImage
from utils.wayland import WaylandWindow as Window

PERSISTENT_DIR = f"/tmp/{data.APP_NAME}/notifications"
PERSISTENT_HISTORY_FILE = os.path.join(PERSISTENT_DIR, "notification_history.json")


def cache_notification_pixbuf(notification_box):
    """
    Saves a scaled pixbuf (48x48) in the cache directory and returns the cache file path.
    """
    notification = notification_box.notification
    if notification.image_pixbuf:
        os.makedirs(PERSISTENT_DIR, exist_ok=True)
        cache_file = os.path.join(
            PERSISTENT_DIR, f"notification_{notification_box.uuid}.png"
        )
        logger.debug(
            f"Caching image for notification {notification.id} to: {cache_file}"
        )
        try:
            scaled = notification.image_pixbuf.scale_simple(
                48, 48, GdkPixbuf.InterpType.BILINEAR
            )
            scaled.savev(cache_file, "png", [], [])
            logger.info(
                f"Successfully cached image for notification {notification.id} to: {
                    cache_file
                }"
            )
            return cache_file
        except Exception as e:
            logger.error(f"Error caching image for notification {notification.id}: {e}")
            return None
    else:
        logger.debug(f"Notification {notification.id} has no image_pixbuf to cache.")
        return None


def load_scaled_pixbuf(notification_box, width, height):
    """
    Loads and scales a pixbuf for a notification_box, prioritizing cached images.
    """
    notification = notification_box.notification
    if not hasattr(notification_box, "notification") or notification is None:
        logger.error(
            "load_scaled_pixbuf: notification_box.notification is None or not set!"
        )
        return None

    pixbuf = None
    if (
        hasattr(notification_box, "cached_image_path")
        and notification_box.cached_image_path
        and os.path.exists(notification_box.cached_image_path)
    ):
        try:
            logger.debug(
                f"Attempting to load cached image from: {
                    notification_box.cached_image_path
                } for notification {notification.id}"
            )
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(notification_box.cached_image_path)
            if pixbuf:
                pixbuf = pixbuf.scale_simple(
                    width, height, GdkPixbuf.InterpType.BILINEAR
                )
                logger.info(
                    f"Successfully loaded cached image from: {
                        notification_box.cached_image_path
                    } for notification {notification.id}"
                )
            return pixbuf
        except Exception as e:
            logger.error(
                f"Error loading cached image from {
                    notification_box.cached_image_path
                } for notification {notification.id}: {e}"
            )
            logger.warning(
                f"Falling back to notification.image_pixbuf for notification {
                    notification.id
                }"
            )

    if notification.image_pixbuf:
        logger.debug(
            f"Loading image directly from notification.image_pixbuf for notification {
                notification.id
            }"
        )
        pixbuf = notification.image_pixbuf.scale_simple(
            width, height, GdkPixbuf.InterpType.BILINEAR
        )
        return pixbuf

    logger.debug(
        f"No image_pixbuf or cached image found, trying app icon for notification {
            notification.id
        }"
    )
    return get_app_icon_pixbuf(notification.app_icon, width, height)


def get_app_icon_pixbuf(icon_path, width, height):
    """
    Loads and scales a pixbuf from an app icon path.
    """
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


class ActionButton(Button):
    def __init__(
        self, action: NotificationAction, index: int, total: int, notification_box
    ):
        super().__init__(
            name="action-button",
            h_expand=True,
            on_clicked=self.on_clicked,
            child=Label(
                name="button-label",
                h_expand=True,
                h_align="fill",
                ellipsization="end",
                max_chars_width=1,
                label=action.label,
            ),
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
        self.action.invoke()
        self.action.parent.close("dismissed-by-user")


class NotificationBox(Box):
    def __init__(self, notification: Notification, timeout_ms=5000, **kwargs):
        super().__init__(
            name="notification-box",
            orientation="v",
            h_align="fill",
            h_expand=True,
            children=[],
        )
        self.notification = notification
        self.uuid = str(uuid.uuid4())

        if timeout_ms == 0:
            self.timeout_ms = 0
        else:
            live_timeout = getattr(self.notification, "timeout", -1)
            self.timeout_ms = live_timeout if live_timeout != -1 else timeout_ms
        self._timeout_id = None
        self._container = None
        self.cached_image_path = None

        if self.timeout_ms > 0:
            self.start_timeout()

        if self.notification.image_pixbuf:
            cache_path = cache_notification_pixbuf(self)
            if cache_path:
                self.cached_image_path = cache_path
                logger.debug(
                    f"NotificationBox {self.uuid}: Cached image path set to: {
                        self.cached_image_path
                    }"
                )
            else:
                logger.warning(
                    f"NotificationBox {
                        self.uuid
                    }: Caching failed, cached_image_path not set."
                )
        else:
            logger.debug(f"NotificationBox {self.uuid}: No image to cache.")

        content = self.create_content()
        action_buttons = self.create_action_buttons()
        self.add(content)
        if action_buttons:
            self.add(action_buttons)

        self.connect("enter-notify-event", self.on_hover_enter)
        self.connect("leave-notify-event", self.on_hover_leave)

        self._destroyed = False
        self._is_history = False
        logger.debug(
            f"NotificationBox {self.uuid} created for notification {notification.id}"
        )

    def set_is_history(self, is_history):
        self._is_history = is_history

    def set_container(self, container):
        self._container = container

    def get_container(self):
        return self._container

    def create_header(self):
        notification = self.notification
        self.app_icon_image = (
            Image(
                name="notification-icon",
                image_file=notification.app_icon[7:],
                size=24,
            )
            if "file://" in notification.app_icon
            else Image(
                name="notification-icon",
                icon_name="dialog-information-symbolic" or notification.app_icon,
                icon_size=24,
            )
        )
        self.app_name_label_header = Label(
            notification.app_name, name="notification-app-name", h_align="start"
        )
        self.header_close_button = self.create_close_button()

        return CenterBox(
            name="notification-title",
            start_children=[
                Box(
                    spacing=4,
                    children=[
                        self.app_icon_image,
                        self.app_name_label_header,
                    ],
                )
            ],
            end_children=[self.header_close_button],
        )

    def create_content(self):
        notification = self.notification
        pixbuf = load_scaled_pixbuf(self, 48, 48)
        self.notification_image_box = Box(
            name="notification-image",
            orientation="v",
            children=[CustomImage(pixbuf=pixbuf), Box(v_expand=True)],
        )
        self.notification_summary_label = Label(
            name="notification-summary",
            markup=notification.summary,
            h_align="start",
            max_chars_width=16,
            ellipsization="end",
        )
        self.notification_app_name_label_content = Label(
            name="notification-app-name",
            markup=notification.app_name,
            h_align="start",
            max_chars_width=16,
            ellipsization="end",
        )
        self.notification_body_label = (
            Label(
                markup=notification.body,
                h_align="start",
                max_chars_width=34,
                ellipsization="end",
            )
            if notification.body
            else Box()
        )
        self.notification_body_label.set_single_line_mode(
            True
        ) if notification.body else None
        self.notification_text_box = Box(
            name="notification-text",
            orientation="v",
            v_align="center",
            h_expand=True,
            h_align="start",
            children=[
                Box(
                    name="notification-summary-box",
                    orientation="h",
                    children=[
                        self.notification_summary_label,
                        Box(
                            name="notif-sep",
                            h_expand=False,
                            v_expand=False,
                            h_align="center",
                            v_align="center",
                        ),
                        self.notification_app_name_label_content,
                    ],
                ),
                self.notification_body_label,
            ],
        )
        self.content_close_button = self.create_close_button()
        self.content_close_button_box = Box(
            orientation="v",
            children=[
                self.content_close_button,
            ],
        )

        return Box(
            name="notification-content",
            spacing=8,
            children=[
                self.notification_image_box,
                self.notification_text_box,
                self.content_close_button_box,
            ],
        )

    def create_action_buttons(self):
        notification = self.notification
        if not notification.actions:
            return None

        grid = Gtk.Grid()
        grid.set_column_homogeneous(True)
        grid.set_column_spacing(4)
        for i, action in enumerate(notification.actions):
            action_button = ActionButton(action, i, len(notification.actions), self)
            grid.attach(action_button, i, 0, 1, 1)
        return grid

    def create_close_button(self):
        self.close_button = Button(
            name="notif-close-button",
            child=Label(name="notif-close-label", markup=icons.cancel),
            on_clicked=lambda *_: self.notification.close("dismissed-by-user"),
        )
        self.close_button.connect(
            "enter-notify-event", lambda *_: self.hover_button(self.close_button)
        )
        self.close_button.connect(
            "leave-notify-event", lambda *_: self.unhover_button(self.close_button)
        )
        return self.close_button

    def on_hover_enter(self, *args):
        if self._container:
            self._container.pause_and_reset_all_timeouts()

    def on_hover_leave(self, *args):
        if self._container:
            self._container.resume_all_timeouts()

    def start_timeout(self):
        self.stop_timeout()
        self._timeout_id = GLib.timeout_add(self.timeout_ms, self.close_notification)

    def stop_timeout(self):
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

    def close_notification(self):
        if not self._destroyed:
            try:
                logger.debug(
                    f"Notification {
                        self.notification.id
                    } timeout expired, closing notification."
                )
                self.notification.close("expired")
                self.stop_timeout()
            except Exception as e:
                logger.error(
                    f"Error in close_notification for notification {
                        self.notification.id
                    }: {e}"
                )
        return False

    def destroy(self, from_history_delete=False):
        logger.debug(
            f"NotificationBox destroy called for notification: {
                self.notification.id
            }, from_history_delete: {from_history_delete}, is_history: {
                self._is_history
            }"
        )
        if (
            hasattr(self, "cached_image_path")
            and self.cached_image_path
            and os.path.exists(self.cached_image_path)
            and (not self._is_history or from_history_delete)
        ):
            try:
                os.remove(self.cached_image_path)
                logger.info(f"Deleted cached image: {self.cached_image_path}")
            except Exception as e:
                logger.error(
                    f"Error deleting cached image {self.cached_image_path}: {e}"
                )
        self._destroyed = True
        self.stop_timeout()
        super().destroy()

    def hover_button(self, button):
        if self._container:
            self._container.pause_and_reset_all_timeouts()

    def unhover_button(self, button):
        if self._container:
            self._container.resume_all_timeouts()


class NotificationHistory(Box):
    def __init__(self, **kwargs):
        super().__init__(name="notification-history", orientation="v", **kwargs)
        self.do_not_disturb_enabled = False
        self.persistent_notifications = []
        self._load_persistent_history()

    def _load_persistent_history(self):
        """Load notifications from persistent file."""
        if not os.path.exists(PERSISTENT_DIR):
            os.makedirs(PERSISTENT_DIR, exist_ok=True)

        if os.path.exists(PERSISTENT_HISTORY_FILE):
            try:
                with open(PERSISTENT_HISTORY_FILE, "r") as f:
                    self.persistent_notifications = json.load(f)
                logger.info(
                    f"Loaded {
                        len(self.persistent_notifications)
                    } notifications from persistent history"
                )
            except Exception as e:
                logger.error(f"Error loading persistent history: {e}")
                self.persistent_notifications = []
        else:
            self.persistent_notifications = []

    def _save_persistent_history(self):
        """Save notifications to persistent file."""
        try:
            with open(PERSISTENT_HISTORY_FILE, "w") as f:
                json.dump(self.persistent_notifications, f, indent=2)
            logger.info(
                f"Saved {
                    len(self.persistent_notifications)
                } notifications to persistent history"
            )
        except Exception as e:
            logger.error(f"Error saving persistent history: {e}")

    def add_notification(self, notification_box):
        """Add a notification to the persistent history."""
        try:
            notification = notification_box.notification

            # Convert to persistent format
            hist_data = {
                "id": notification_box.uuid,
                "app_icon": getattr(
                    notification, "app_icon", "dialog-information-symbolic"
                ),
                "summary": getattr(notification, "summary", "No summary"),
                "body": getattr(notification, "body", ""),
                "app_name": getattr(notification, "app_name", "Unknown"),
                "timestamp": datetime.now().isoformat(),
                "cached_image_path": getattr(
                    notification_box, "cached_image_path", None
                ),
            }

            # Add to persistent notifications (keep last 100)
            self.persistent_notifications.append(hist_data)
            if len(self.persistent_notifications) > 100:
                # Remove oldest notifications but keep their cached images
                old_notif = self.persistent_notifications.pop(0)
                # Don't delete cached image here as it might be in use

            # Save to file
            self._save_persistent_history()

            logger.info(
                f"Added notification to history: {hist_data['summary']} from {
                    hist_data['app_name']
                }"
            )

        except Exception as e:
            logger.error(f"Error adding notification to history: {e}")

    def clear_history_for_app(self, app_name):
        """Clear history for a specific app."""
        try:
            original_count = len(self.persistent_notifications)
            self.persistent_notifications = [
                notif
                for notif in self.persistent_notifications
                if notif.get("app_name") != app_name
            ]
            removed_count = original_count - len(self.persistent_notifications)
            if removed_count > 0:
                self._save_persistent_history()
                logger.info(
                    f"Cleared {removed_count} notifications for app: {app_name}"
                )
        except Exception as e:
            logger.error(f"Error clearing history for app {app_name}: {e}")


class NotificationContainer(Box):
    LIMITED_APPS = ["Spotify"]

    def __init__(
        self,
        notification_history_instance: NotificationHistory,
        revealer_transition_type: str = "slide-down",
    ):
        super().__init__(name="notification-container-main", orientation="v", spacing=4)
        self.notification_history = notification_history_instance

        self._server = Notifications()
        self._server.connect("notification-added", self.on_new_notification)
        self._pending_removal = False
        self._is_destroying = False

        self.stack = Gtk.Stack(
            name="notification-stack",
            transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
            transition_duration=200,
            visible=True,
        )
        self.navigation = Box(
            name="notification-navigation", spacing=4, h_align="center"
        )
        self.stack_box = Box(
            name="notification-stack-box",
            h_align="center",
            h_expand=False,
            children=[self.stack],
        )
        self.prev_button = Button(
            name="nav-button",
            child=Label(name="nav-button-label", markup=icons.chevron_left),
            on_clicked=self.show_previous,
        )
        self.close_all_button = Button(
            name="nav-button",
            child=Label(name="nav-button-label", markup=icons.cancel),
            on_clicked=self.close_all_notifications,
        )
        self.close_all_button_label = self.close_all_button.get_child()
        self.close_all_button_label.add_style_class("close")
        self.next_button = Button(
            name="nav-button",
            child=Label(name="nav-button-label", markup=icons.chevron_right),
            on_clicked=self.show_next,
        )
        for button in [self.prev_button, self.close_all_button, self.next_button]:
            button.connect(
                "enter-notify-event", lambda *_: self.pause_and_reset_all_timeouts()
            )
            button.connect("leave-notify-event", lambda *_: self.resume_all_timeouts())
        self.navigation.add(self.prev_button)
        self.navigation.add(self.close_all_button)
        self.navigation.add(self.next_button)

        self.navigation_revealer = Revealer(
            transition_type="slide-down",
            transition_duration=200,
            child=self.navigation,
            reveal_child=False,
        )

        self.notification_box_container = Box(
            name="notification-box-internal-container",
            orientation="v",
            children=[self.stack_box, self.navigation_revealer],
        )

        self.main_revealer = Revealer(
            name="notification-main-revealer",
            transition_type=revealer_transition_type,
            transition_duration=250,
            child_revealed=False,
            child=self.notification_box_container,
        )

        self.add(self.main_revealer)

        self.notifications = []
        self.current_index = 0
        self.update_navigation_buttons()
        self._destroyed_notifications = set()

    def on_new_notification(self, fabric_notif, id):
        notification_history_instance = self.notification_history
        if notification_history_instance.do_not_disturb_enabled:
            logger.info(
                "Do Not Disturb mode enabled: adding notification directly to history."
            )
            notification = fabric_notif.get_notification_from_id(id)
            new_box = NotificationBox(notification)
            if notification.image_pixbuf:
                cache_notification_pixbuf(new_box)
            new_box.set_is_history(True)
            notification_history_instance.add_notification(new_box)
            return

        notification = fabric_notif.get_notification_from_id(id)
        new_box = NotificationBox(notification)
        new_box.set_container(self)
        notification.connect("closed", self.on_notification_closed)

        app_name = notification.app_name
        if app_name in self.LIMITED_APPS:
            notification_history_instance.clear_history_for_app(app_name)

            existing_notification_index = -1
            for index, existing_box in enumerate(self.notifications):
                if existing_box.notification.app_name == app_name:
                    existing_notification_index = index
                    break

            if existing_notification_index != -1:
                old_notification_box = self.notifications.pop(
                    existing_notification_index
                )
                self.stack.remove(old_notification_box)
                # Add old notification to history before destroying
                old_notification_box.set_is_history(True)
                notification_history_instance.add_notification(old_notification_box)
                old_notification_box.destroy()

                self.stack.add_named(new_box, str(id))
                self.notifications.append(new_box)
                self.current_index = len(self.notifications) - 1
                self.stack.set_visible_child(new_box)
            else:
                while len(self.notifications) >= 5:
                    oldest_notification = self.notifications[0]
                    oldest_notification.set_is_history(True)
                    notification_history_instance.add_notification(oldest_notification)
                    self.stack.remove(oldest_notification)
                    self.notifications.pop(0)
                    if self.current_index > 0:
                        self.current_index -= 1
                self.stack.add_named(new_box, str(id))
                self.notifications.append(new_box)
                self.current_index = len(self.notifications) - 1
                self.stack.set_visible_child(new_box)
        else:
            while len(self.notifications) >= 5:
                oldest_notification = self.notifications[0]
                oldest_notification.set_is_history(True)
                notification_history_instance.add_notification(oldest_notification)
                self.stack.remove(oldest_notification)
                self.notifications.pop(0)
                if self.current_index > 0:
                    self.current_index -= 1
            self.stack.add_named(new_box, str(id))
            self.notifications.append(new_box)
            self.current_index = len(self.notifications) - 1
            self.stack.set_visible_child(new_box)

        for notification_box in self.notifications:
            notification_box.start_timeout()
        self.main_revealer.show_all()
        self.main_revealer.set_reveal_child(True)
        self.update_navigation_buttons()

        logger.info(
            f"[NotificationContainer] New notification from {notification.app_name}"
        )

    def show_previous(self, *args):
        """Show the previous notification in the stack."""
        if self.current_index > 0:
            self.current_index -= 1
            self.stack.set_visible_child(self.notifications[self.current_index])
            self.update_navigation_buttons()

    def show_next(self, *args):
        """Show the next notification in the stack."""
        if self.current_index < len(self.notifications) - 1:
            self.current_index += 1
            self.stack.set_visible_child(self.notifications[self.current_index])
            self.update_navigation_buttons()

    def update_navigation_buttons(self):
        """Update navigation button states and visibility."""
        self.prev_button.set_sensitive(self.current_index > 0)
        self.next_button.set_sensitive(self.current_index < len(self.notifications) - 1)
        should_reveal = len(self.notifications) > 1
        self.navigation_revealer.set_reveal_child(should_reveal)

    def on_notification_closed(self, notification, reason):
        if self._is_destroying:
            return
        if notification.id in self._destroyed_notifications:
            return
        self._destroyed_notifications.add(notification.id)
        try:
            logger.info(f"Notification {notification.id} closing with reason: {reason}")
            notif_to_remove = None
            for i, notif_box in enumerate(self.notifications):
                if notif_box.notification.id == notification.id:
                    notif_to_remove = (i, notif_box)
                    break
            if not notif_to_remove:
                return
            i, notif_box = notif_to_remove
            reason_str = str(reason)

            notification_history_instance = self.notification_history

            # Always add to history regardless of close reason
            logger.info(
                f"Adding notification {notification.id} to history (reason: {
                    reason_str
                })"
            )
            notif_box.set_is_history(True)
            notification_history_instance.add_notification(notif_box)
            notif_box.stop_timeout()

            # Only destroy if explicitly dismissed by user
            if reason_str == "NotificationCloseReason.DISMISSED_BY_USER":
                logger.info(
                    f"User dismissed notification {
                        notification.id
                    }, but still added to history"
                )
            elif (
                reason_str == "NotificationCloseReason.EXPIRED"
                or reason_str == "NotificationCloseReason.CLOSED"
                or reason_str == "NotificationCloseReason.UNDEFINED"
            ):
                logger.info(
                    f"Notification {
                        notification.id
                    } closed automatically, added to history"
                )
            else:
                logger.warning(
                    f"Unknown close reason: {reason_str} for notification {
                        notification.id
                    }. Still added to history."
                )

            if len(self.notifications) == 1:
                self._is_destroying = True
                self.main_revealer.set_reveal_child(False)
                GLib.timeout_add(
                    self.main_revealer.get_transition_duration(),
                    self._destroy_container,
                )
                return

            new_index = i
            if i == self.current_index:
                new_index = max(0, i - 1)
            elif i < self.current_index:
                new_index = self.current_index - 1

            if notif_box.get_parent() == self.stack:
                self.stack.remove(notif_box)
            self.notifications.pop(i)

            if new_index >= len(self.notifications) and len(self.notifications) > 0:
                new_index = len(self.notifications) - 1

            self.current_index = new_index

            if len(self.notifications) > 0:
                self.stack.set_visible_child(self.notifications[self.current_index])

            self.update_navigation_buttons()
        except Exception as e:
            logger.error(f"Error closing notification: {e}")

    def _destroy_container(self):
        """Clean up the container when all notifications are closed."""
        try:
            self.notifications.clear()
            self._destroyed_notifications.clear()
            for child in self.stack.get_children():
                self.stack.remove(child)
                child.destroy()
            self.current_index = 0
        except Exception as e:
            logger.error(f"Error cleaning up the container: {e}")
        finally:
            self._is_destroying = False
            return False

    def pause_and_reset_all_timeouts(self):
        """Pause timeouts for all notifications."""
        if self._is_destroying:
            return
        for notification in self.notifications[:]:
            try:
                if hasattr(notification, "pause_timeout"):
                    notification.pause_timeout()
            except Exception as e:
                logger.error(f"Error pausing timeout: {e}")

    def resume_all_timeouts(self):
        """Resume timeouts for all notifications."""
        if self._is_destroying:
            return
        for notification in self.notifications[:]:
            try:
                if hasattr(notification, "resume_timeout"):
                    notification.resume_timeout()
            except Exception as e:
                logger.error(f"Error resuming timeout: {e}")

    def close_all_notifications(self, *args):
        """Close all notifications."""
        notifications_to_close = self.notifications.copy()
        for notification_box in notifications_to_close:
            notification_box.notification.close("dismissed-by-user")


class NotificationPopup(Window):
    def __init__(self, **kwargs):
        y_pos = data.NOTIF_POS.lower() if hasattr(data, "NOTIF_POS") else "top"
        x_pos = "right"

        # Simple positioning logic - can be enhanced later
        if hasattr(data, "DOCK_POSITION") and data.DOCK_POSITION in ["Top", "Bottom"]:
            x_pos = "right"

        super().__init__(
            name="notification-popup",
            anchor=f"{x_pos} {y_pos}",
            layer="top",
            keyboard_mode="none",
            exclusivity="none",
            visible=True,
            all_visible=True,
        )

        self.widgets = kwargs.get("widgets", None)

        self.notification_history = (
            self.widgets.notification_history if self.widgets else NotificationHistory()
        )
        self.notification_container = NotificationContainer(
            notification_history_instance=self.notification_history,
            revealer_transition_type="slide-down" if y_pos == "top" else "slide-up",
        )

        self.show_box = Box()
        self.show_box.set_size_request(1, 1)

        self.add(
            Box(
                name="notification-popup-box",
                orientation="v",
                children=[self.notification_container, self.show_box],
            )
        )
