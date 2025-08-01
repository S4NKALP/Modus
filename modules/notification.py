import os
import sys
from typing import cast

from gi.repository import GdkPixbuf, GLib  # type: ignore

from config.data import NOTIFICATION_TIMEOUT
from fabric.notifications import (
    Notification,
    NotificationAction,
    NotificationCloseReason,
    Notifications,
)
from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from utils.roam import modus_service
from widgets.custom_image import CustomImage
from widgets.customrevealer import SlideRevealer
from widgets.wayland import WaylandWindow as Window

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

NOTIFICATION_WIDTH = 360
NOTIFICATION_IMAGE_SIZE = 48


# Improved animation smoothness and consistent behavior for rapid notifications.
def smooth_revealer_animation(revealer: SlideRevealer, duration: int = 600):
    revealer.duration = duration


def get_notification_image_pixbuf(
    notification: Notification,
) -> GdkPixbuf.Pixbuf | None:
    width = NOTIFICATION_IMAGE_SIZE
    height = NOTIFICATION_IMAGE_SIZE

    try:
        if notification.image_file and os.path.exists(notification.image_file):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(notification.image_file)
            return pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
        elif notification.image_pixbuf:
            return notification.image_pixbuf.scale_simple(
                width, height, GdkPixbuf.InterpType.BILINEAR
            )
    except Exception as e:
        print("Failed to load image:", e)

    return None


class NotificationWidget(Box):
    def __init__(self, notification: Notification, **kwargs):
        super().__init__(
            size=(NOTIFICATION_WIDTH, -1),
            name="notification",
            spacing=8,
            orientation="v",
            **kwargs,
        )

        self._notification = notification

        self.image = notification.app_icon
        body_container = Box(name="noti-image", spacing=4, orientation="h")

        pixbuf = get_notification_image_pixbuf(notification)
        image_file = None

        if notification.app_icon:
            if notification.app_icon.startswith("file://"):
                image_file = notification.app_icon[7:]
            elif os.path.exists(notification.app_icon):
                image_file = notification.app_icon

        if image_file:
            body_container.add(
                CustomImage(
                    name="noti-image",
                    image_file=image_file,
                    size=NOTIFICATION_IMAGE_SIZE,
                )
            )
        elif pixbuf:
            body_container.add(
                CustomImage(
                    name="noti-image",
                    image_pixbuf=pixbuf,
                    size=NOTIFICATION_IMAGE_SIZE,
                )
            )
        else:
            body_container.add(
                CustomImage(
                    name="noti-image",
                    icon_name="dialog-information-symbolic",
                    icon_size=NOTIFICATION_IMAGE_SIZE,
                )
            )

        body_container.add(
            Box(
                spacing=4,
                orientation="v",
                children=[
                    Box(
                        orientation="h",
                        children=[
                            Label(
                                markup=self._notification.summary,  # type: ignore
                                ellipsization="end",
                                max_chars_width=20,
                                style_classes="summary",
                            )
                        ],
                        h_expand=True,
                        v_expand=True,
                    ),
                    Label(
                        label=self._notification.body,  # type: ignore
                        v_align="start",
                        h_align="start",
                        ellipsization="end",
                        max_chars_width=34,
                        style_classes="body",
                    ),
                ],
                h_expand=True,
                v_expand=True,
            )
        )

        self.add(body_container)

        if actions := self._notification.actions:
            actions = cast(list[NotificationAction], actions)  # type: ignore
            self.add(
                Box(
                    spacing=4,
                    orientation="h",
                    children=[
                        Button(
                            label=action.label,
                            h_expand=True,
                            name="notification-action",
                            v_expand=True,
                            on_clicked=lambda *_, action=action: (
                                action.invoke(),
                                action.parent.close("dismissed-by-user"),
                            ),
                        )
                        for action in actions  # type: ignore
                    ],
                )
            )

        self._notification.connect(
            "closed",
            self.destroy_noti,
        )

        invoke_repeater(
            NOTIFICATION_TIMEOUT,
            lambda: self._notification.close("expired"),
            initial_call=False,
        )

    def close_noti(self, *_):
        modus_service.remove_notification(self._notification["id"])
        self._notification.close()
        self.destroy()

    def destroy_noti(self, *_):
        (parent.remove(self) if (parent := self.get_parent()) else None,)  # type: ignore
        self.destroy()


class NotificationRevealer(SlideRevealer):
    def __init__(self, notification: Notification, on_transition_end=None, **kwargs):
        self.notif_box = NotificationWidget(notification)
        self.notification = notification
        self.on_transition_end = on_transition_end

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
            duration=600,
        )

        smooth_revealer_animation(self)

        # Disconnect the destroy_noti handler from the notification widget
        # to prevent immediate destruction that interferes with slide animation
        self.notification.disconnect_by_func(self.notif_box.destroy_noti)

        # Connect our own handler that manages the slide animation
        self.notification.connect("closed", self.on_resolved)

    def _on_animation_complete(self, is_hiding=False):
        if is_hiding:
            # Manually destroy the notification widget since we disconnected its handler
            self.notif_box.destroy_noti()

            if self.on_transition_end:
                self.on_transition_end()
            self.destroy()

    def on_resolved(
        self,
        _notification: Notification,
        reason: NotificationCloseReason,
    ):
        # Use left-to-right slide for auto-dismiss (expired), right-to-left for manual close
        if reason == "expired":
            # Left-to-right slide for auto-dismiss
            self.set_slide_direction("left")
        else:
            # Right-to-left slide for manual close
            self.set_slide_direction("right")

        self.hide()
        GLib.timeout_add(self.duration + 50, lambda: self._on_animation_complete(True))

    def _on_button_press(self, _widget, event):
        if event.button == 1:
            self._drag_start_x = event.x
            self._drag_start_y = event.y
            self._is_dragging = True
        return False

    def _on_button_release(self, _widget, event):
        if self._is_dragging and event.button == 1:
            self._is_dragging = False

            # Calculate swipe distance
            dx = event.x - self._drag_start_x
            dy = abs(event.y - self._drag_start_y)

            if dx > self._swipe_threshold and dy < 50:  # 50px vertical tolerance
                # Follow the swipe gesture direction
                self.set_slide_direction("right")
                self.hide()
                # Schedule cleanup after animation
                GLib.timeout_add(
                    self.duration + 50, lambda: self._on_animation_complete(True)
                )
        return False

    def _on_motion(self, _widget, event):
        if self._is_dragging:
            # TODO: Add visual feedback during swipe
            # Could add translation or opacity changes here
            pass
        return False


class ModusNoti(Window):
    def __init__(self):
        self._server = Notifications()
        self.notifications = Box(
            v_expand=True,
            h_expand=True,
            title="Notification Center",
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

        # Check if Do Not Disturb is enabled
        if modus_service.dont_disturb:
            # Still cache the notification for notification center, but don't show it
            modus_service.cache_notification(notification)
            # Close the notification immediately to prevent it from showing
            notification.close("dismissed-by-user")
            return

        new_box = NotificationRevealer(
            notification, on_transition_end=lambda: self.notifications.remove(new_box)
        )

        # Insert at the beginning (index 0) to show new notifications at the top
        current_children = list(self.notifications.children)
        current_children.insert(0, new_box)
        self.notifications.children = current_children

        # This ensures each notification's container is fully laid out before animation

        if len(current_children) >= 4:
            # Animate close for the oldest notification if we exceed the limit
            oldest_notification = current_children[-1]
            if hasattr(oldest_notification, 'notification'):
                # Trigger the close animation by closing the underlying notification
                # This will use the same slide animation as auto-dismiss (left-to-right)
                oldest_notification.notification.close("expired")
            current_children.pop()

        def start_animation():
            if new_box.get_parent():  # Only animate if still in the tree
                new_box.reveal()
            return False

        GLib.timeout_add(32, start_animation)
