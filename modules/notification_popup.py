import os

from fabric.notifications import (
    Notification,
    NotificationAction,
    NotificationCloseReason,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from gi.repository import Gdk, GdkPixbuf, GLib
from loguru import logger

import utils.icons as icons
from services import notification_service
from utils.animator import Animator
from utils.custom_image import CustomImage
from utils.wayland import WaylandWindow as Window


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
        self.action.invoke()
        self.action.parent.close("dismissed-by-user")


class NotificationWidget(Box):
    def __init__(self, notification: Notification, timeout_ms=5000, **kwargs):
        self.notification = notification

        self.is_expanded = False

        self.expanded_revealer = Revealer(
            name="notification-expanded-revealer",
            transition_type="slide-down",
            transition_duration=250,
            reveal_child=False,
            child=self.create_expanded_content(notification),
        )

        super().__init__(
            name="notification-box",
            orientation="v",
            h_align="fill",
            h_expand=True,
            children=[
                self.create_content(notification),
                self.expanded_revealer,
            ],
        )
        self.timeout_ms = timeout_ms
        self._timeout_id = None

        self.close_button_animator = Animator(
            bezier_curve=(0.25, 0.1, 0.25, 1.0),
            duration=0.3,
            min_value=0.0,
            max_value=1.0,
            repeat=False,
        )
        self.close_button_animator.connect(
            "notify::value", self.on_hover_animation_value_changed
        )

        self.timeout_progress_animator = Animator(
            bezier_curve=(1.0, 0.0, 1.0, 1.0),
            duration=timeout_ms / 1000.0,
            min_value=0.0,
            max_value=1.0,
            repeat=False,
        )
        self.timeout_progress_animator.connect(
            "notify::value", self.on_timeout_progress_changed
        )
        self.timeout_progress_animator.connect("finished", self.on_timeout_finished)

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
            end_children=[self.create_close_button()],
        )

    def create_content(self, notification):
        return Box(
            name="notification-content",
            spacing=8,
            children=[
                Box(
                    name="notification-image",
                    children=CustomImage(
                        pixbuf=notification.image_pixbuf.scale_simple(
                            48, 48, GdkPixbuf.InterpType.BILINEAR
                        )
                        if notification.image_pixbuf
                        else self.get_pixbuf(notification.app_icon, 48, 48)
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
                        self.create_body_label(notification),
                    ],
                ),
                Box(h_expand=True),
                Box(
                    orientation="v",
                    children=[
                        Box(
                            orientation="h",
                            spacing=4,
                            children=[
                                self.create_chevron_button(),
                                self.create_close_button(),
                            ],
                        ),
                        Box(v_expand=True),
                    ],
                ),
            ],
        )

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
        if not notification.actions:
            return Box()
        return Box(
            name="notification-action-buttons",
            spacing=4,
            h_expand=True,
            children=[
                ActionButton(action, i, len(notification.actions), self)
                for i, action in enumerate(notification.actions)
            ],
        )

    def create_close_button(self):
        close_icon = Label(name="notif-close-label", markup=icons.cancel)

        self.close_progress_bar = CircularProgressBar(
            name="notif-close-progress",
            size=28,
            line_width=2,
            start_angle=0,
            end_angle=360,
            value=0.0,
            min_value=0.0,
            max_value=1.0,
            child=close_icon,
        )

        close_button = Button(
            name="notif-close-button",
            child=self.close_progress_bar,
            on_clicked=lambda *_: self.notification.close("dismissed-by-user"),
        )
        close_button.connect(
            "enter-notify-event", lambda *_: self.hover_button(close_button)
        )
        close_button.connect(
            "leave-notify-event", lambda *_: self.unhover_button(close_button)
        )
        return close_button

    def create_body_label(self, notification):
        if not notification.body:
            return Box()

        # Store reference to body label for expanding/collapsing
        self.body_label = Label(
            name="notification-body",
            markup=notification.body.replace("\n", " "),
            h_align="start",
            ellipsization="end",
        )
        return self.body_label

    def create_chevron_button(self):
        # Only show chevron button if there's something to expand
        # (either long text that gets ellipsized or action buttons)
        has_expandable_content = (
            (self.notification.body and len(self.notification.body) > 50)  # Long text
            or bool(self.notification.actions)  # Has action buttons
        )

        if not has_expandable_content:
            return Box()  # Return empty box if nothing to expand

        self.chevron_icon = Label(name="notif-chevron-label", markup=icons.chevron_down)

        chevron_button = Button(
            name="notif-chevron-button",
            child=self.chevron_icon,
            on_clicked=self.toggle_expanded,
        )
        chevron_button.connect(
            "enter-notify-event", lambda *_: self.hover_button(chevron_button)
        )
        chevron_button.connect(
            "leave-notify-event", lambda *_: self.unhover_button(chevron_button)
        )
        return chevron_button

    def create_expanded_content(self, notification):
        # Only show action buttons in expanded content and the body text will be expanded in place
        if notification.actions:
            return Box(
                name="notification-expanded-content",
                orientation="v",
                spacing=8,
                children=[self.create_action_buttons(notification)],
            )
        else:
            return Box()

    def toggle_expanded(self, *_):
        self.is_expanded = not self.is_expanded
        self.expanded_revealer.set_reveal_child(self.is_expanded)

        # Update chevron icon direction
        if self.is_expanded:
            self.chevron_icon.set_markup(icons.chevron_up)
        else:
            self.chevron_icon.set_markup(icons.chevron_down)

        # Toggle body label properties
        if hasattr(self, "body_label") and self.body_label:
            if self.is_expanded:
                # Show full text without ellipsization and enable wrapping
                # Keep original newlines
                self.body_label.set_markup(self.notification.body)
                self.body_label.set_property("ellipsize", 0)
                self.body_label.set_property("wrap", True)
                self.body_label.set_property("wrap-mode", 2)
            else:
                # Show truncated text with ellipsization
                self.body_label.set_markup(self.notification.body.replace("\n", " "))
                self.body_label.set_property("ellipsize", 3)
                self.body_label.set_property("wrap", False)

    def on_hover_animation_value_changed(self, animator, value):
        # This is for hover effects only - we don't update the progress bar here
        # as the timeout progress takes priority
        pass

    def on_timeout_progress_changed(self, animator, value):
        if hasattr(self, "close_progress_bar"):
            # Update progress bar value based on timeout progress (convert to float to avoid type issues)
            self.close_progress_bar.value = float(animator.value)

    def on_timeout_finished(self, animator):
        # The notification will be closed by the existing timeout mechanism
        pass

    def start_timeout(self):
        self.stop_timeout()
        if hasattr(self, "timeout_progress_animator"):
            self.timeout_progress_animator.play()
        self._timeout_id = GLib.timeout_add(self.timeout_ms, self.close_notification)

    def stop_timeout(self):
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None
        if hasattr(self, "timeout_progress_animator"):
            self.timeout_progress_animator.stop()

    def close_notification(self):
        self.notification.close("expired")
        self.stop_timeout()
        return False

    def pause_timeout(self):
        self.stop_timeout()

    def resume_timeout(self):
        self.start_timeout()

    def destroy(self):
        self.stop_timeout()
        if hasattr(self, "close_button_animator"):
            self.close_button_animator.stop()
        if hasattr(self, "timeout_progress_animator"):
            self.timeout_progress_animator.stop()
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

        # On hover, show full progress (indicating ready to close)
        if hasattr(self, "close_progress_bar"):
            self.close_progress_bar.value = 1.0

    def unhover_button(self, button):
        self.resume_timeout()
        self.set_pointer_cursor(button, "arrow")

        # On unhover, resume showing timeout progress
        if hasattr(self, "timeout_progress_animator") and hasattr(
            self, "close_progress_bar"
        ):
            # Resume the timeout progress display
            current_progress = float(self.timeout_progress_animator.value)
            self.close_progress_bar.value = current_progress


class NotificationRevealer(Revealer):
    def __init__(self, notification: Notification, cache_service, **kwargs):
        self.notif_box = NotificationWidget(notification)
        self._notification = notification
        self.cache_service = cache_service
        super().__init__(
            child=Box(
                children=[self.notif_box],
            ),
            transition_duration=250,
            transition_type="slide-down",
        )

        self.connect(
            "notify::child-revealed",
            lambda *_: self.destroy() if not self.get_child_revealed() else None,
        )

        self._notification.connect("closed", self.on_resolved)

    def on_resolved(
        self,
        notification: Notification,
        reason: NotificationCloseReason,
    ):
        # Cache the notification to history when it's actually closed/dismissed
        self.cache_service.cache_notification(notification)
        logger.info(
            f"[Notification] Cached notification from {notification.app_name} (reason: {
                reason
            })"
        )
        self.set_reveal_child(False)


class NotificationPopup(Window):
    def __init__(self):
        self._server = notification_service
        self.cache_notification_service = notification_service
        self.notifications = Box(
            v_expand=True,
            h_expand=True,
            style="margin: 1px 0px 1px 1px;",
            orientation="v",
            spacing=5,
        )
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

        # Only show popup if DND is not enabled
        if not self.cache_notification_service.dont_disturb:
            new_box = NotificationRevealer(
                fabric_notif.get_notification_from_id(id),
                self.cache_notification_service,
            )
            self.notifications.add(new_box)
            new_box.set_reveal_child(True)
            logger.info(f"[Notification] New notification from {notification.app_name}")
        else:
            # Even in DND mode, we should cache the notification when it would have been closed
            # For DND notifications, cache them immediately since they won't be shown
            self.cache_notification_service.cache_notification(notification)
            logger.info(
                f"[Notification] DND enabled, notification from {
                    notification.app_name
                } cached without showing popup"
            )
