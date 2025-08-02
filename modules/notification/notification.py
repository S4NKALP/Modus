import os

from gi.repository import Gdk, GdkPixbuf, GLib  # type: ignore
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
from utils.roam import modus_service, notification_service
from widgets.custom_image import CustomImage
from widgets.customrevealer import SlideRevealer
from widgets.wayland import WaylandWindow as Window

NOTIFICATION_WIDTH = 360
NOTIFICATION_IMAGE_SIZE = 48


def smooth_revealer_animation(revealer: SlideRevealer, duration: int = 350):
    """Configure revealer for macOS-like smooth animation"""
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
                icon_name="dialog-information-symbolic" or notification.app_icon,
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
                        pixbuf=(
                            notification.image_pixbuf.scale_simple(
                                48, 48, GdkPixbuf.InterpType.BILINEAR
                            )
                            if notification.image_pixbuf
                            else self.get_pixbuf(notification.app_icon, 48, 48)
                        )
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
                                Label(
                                    name="notification-app-name",
                                    markup=" | " + notification.app_name,
                                    h_align="start",
                                    ellipsization="end",
                                ),
                            ],
                        ),
                        (
                            Label(
                                markup=notification.body.replace("\n", " "),
                                h_align="start",
                                ellipsization="end",
                            )
                            if notification.body
                            else Box()
                        ),
                    ],
                ),
                Box(h_expand=True),
                Box(
                    orientation="v",
                    children=[
                        self.create_close_button() if self.show_close_button else Box(),
                        Box(v_expand=True),
                    ],
                ),
            ],
        )

    def create_close_button(self):
        if self.close_button is None:
            self.close_button = Button(
                name="notification-close-button",
                visible=False,  # Initially hidden
                on_clicked=lambda *_: self.notification.close("dismissed-by-user"),
                child=Label(label="×", name="close-button-label"),
            )
        return self.close_button

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

    def destroy(self):
        self.stop_timeout()
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

        # Add swipe detection variables
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False
        self._swipe_threshold = 100  # pixels to trigger swipe dismiss

        # Wrap notification in EventBox for swipe detection
        self.event_box = EventBox(
            events=[
                "button-press-event",
                "button-release-event",
                "motion-notify-event",
            ],
            child=self.notif_box,
        )

        self.event_box.connect("button-press-event", self._on_button_press)
        self.event_box.connect("button-release-event", self._on_button_release)
        self.event_box.connect("motion-notify-event", self._on_motion)

        super().__init__(
            child=self.event_box,
            direction="right",
            duration=350,  # Optimized duration for macOS-like feel
        )

        smooth_revealer_animation(self)

        # Connect our own handler that manages the slide animation
        self.notification.connect("closed", self.on_resolved)

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
        
        # Use left-to-right slide for auto-dismiss (expired), right-to-left for manual close
        if reason == "expired":
            # Left-to-right slide for auto-dismiss
            self.set_slide_direction("left")
        else:
            # Right-to-left slide for manual close
            self.set_slide_direction("right")

        self.hide()
        # Reduced timeout for snappier transitions
        GLib.timeout_add(self.duration + 30, lambda: self._on_animation_complete(True))

    def _on_button_press(self, _widget, event):
        if event.button == 1:
            self._drag_start_x = event.x
            self._drag_start_y = event.y
            self._is_dragging = True
        return False

    def _on_button_release(self, _widget, event):
        if event.button == 3:  # Right click
            try:
                if self.parent_window:
                    self.parent_window.clear_notification_queue()
                # Also dismiss current notification
                self.notification.close("dismissed-by-user")
            except:
                pass  # Ignore errors
            return True

        elif self._is_dragging and event.button == 1:
            self._is_dragging = False

            # Calculate swipe distance
            dx = event.x - self._drag_start_x
            dy = abs(event.y - self._drag_start_y)

            # Left-to-right swipe: dismiss current notification only
            if dx > self._swipe_threshold and dy < 50:  # 50px vertical tolerance
                try:
                    self.notification.close("dismissed-by-user")
                except:
                    pass  # Ignore errors
        return False

    def _on_motion(self, _widget, event):
        if self._is_dragging:
            # TODO: Add visual feedback during swipe
            # Could add translation or opacity changes here
            pass
        return False


class NotificationState:
    IDLE = 0
    SHOWING = 1
    HIDING = 2


class NotificationCenter(Window):
    def __init__(self):
        self._server = notification_service
        self.notifications = Box(
            v_expand=True,
            h_expand=True,
            title="Notification Center",
            style="margin: 1px 0px 1px 1px;",
            orientation="v",
            spacing=5,
        )

        # Enhanced queue system for smooth transitions
        self.notification_queue = []
        self.current_notification = None
        self.notification_state = NotificationState.IDLE
        self._transition_timer_id = None

        # Initialize ignored apps list from config
        self.ignored_apps = data.NOTIFICATION_IGNORED_APPS

        self._server.connect("notification-added", self.on_new_notification)
        super().__init__(
            anchor="top right",
            child=self.notifications,
            layer="overlay",
            all_visible=True,
            visible=True,
            exclusive=False,
        )

    def on_new_notification(self, fabric_notif, id):
        notification: Notification = fabric_notif.get_notification_from_id(id)

        # Cache the notification to the modus service for persistence
        try:
            modus_service.cache_notification(notification)
            logger.debug(
                f"Cached notification: {notification.app_name} - {notification.summary}"
            )
        except Exception as e:
            logger.error(f"Failed to cache notification: {e}")

        # Check if the notification is in the "do not disturb" mode, hacky way
        if self._server.dont_disturb or notification.app_name in self.ignored_apps:
            return

        if modus_service.dont_disturb:
            notification.close("dismissed-by-user")
            return

        # Clear any pending notifications in queue (except the current one being shown)
        for pending_notification in list(self.notification_queue):
            try:
                pending_notification.close("dismissed-by-user")
            except:
                pass
        self.notification_queue.clear()

        # Add new notification to queue
        self.notification_queue.append(notification)
        
        # Process the queue
        self._process_notification_queue()

    def _process_notification_queue(self):
        # If we're currently showing a notification and there's a new one in queue
        if (self.notification_state == NotificationState.SHOWING and 
            self.current_notification and 
            self.notification_queue):
            
            # Start hiding the current notification to make room for the new one
            self._start_hiding_current_notification()
            
        elif self.notification_state == NotificationState.IDLE and self.notification_queue:
            # If we're idle and have notifications in queue, show the next one
            self._show_next_notification()

    def _start_hiding_current_notification(self):
        if (self.current_notification and 
            self.notification_state == NotificationState.SHOWING and
            not self.current_notification._is_closing):
            
            self.notification_state = NotificationState.HIDING
            
            # Force close the current notification to trigger hiding animation
            try:
                self.current_notification.notification.close("dismissed-by-user")
            except:
                pass

    def _show_next_notification(self):
        if not self.notification_queue or self.notification_state != NotificationState.IDLE:
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

        # Process next notification with a small delay for smooth transitions
        if self.notification_queue:
            self._transition_timer_id = GLib.timeout_add(
                50,  # Very short delay for seamless transitions
                lambda: self._show_next_notification() or False
            )

    def show_next_notification(self):
        # Legacy method for compatibility - redirect to new implementation
        self._show_next_notification()

    def on_notification_finished(self, notification_box):
        # Legacy method for compatibility - redirect to new implementation
        self._on_notification_finished(notification_box)

    def clear_notification_queue(self):
        queue_length = len(self.notification_queue)
        if queue_length > 0:
            for notification in list(self.notification_queue):
                try:
                    notification.close("dismissed-by-user")
                except:
                    pass  # Ignore errors if notification is already closed
            self.notification_queue.clear()

        # Cancel any pending transition timer
        if self._transition_timer_id:
            GLib.source_remove(self._transition_timer_id)
            self._transition_timer_id = None

    def get_queue_length(self):
        return len(self.notification_queue)
