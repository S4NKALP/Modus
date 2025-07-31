from typing import cast

from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from widgets.wayland import WaylandWindow as Window
from fabric.widgets.revealer import Revealer
from fabric.notifications import (
    NotificationAction,
    Notifications,
    Notification,
    NotificationCloseReason,
    NotificationImagePixmap,
)
import os
from fabric.utils import invoke_repeater, get_relative_path

from utils.roam import modus_service

from utils.custom_image import CustomImage

from gi.repository import GdkPixbuf  # type: ignore


NOTIFICATION_WIDTH = 360
NOTIFICATION_IMAGE_SIZE = 48
NOTIFICATION_TIMEOUT = 10 * 1000


# TODO: make the revealer animation smoother and the on every new notification the revealer work as it work for initial notification (rapid notification issue)


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

        # Load and show image (from app_icon, image_file, or pixbuf)
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
                                ellipsization="middle",
                                style_classes="summary",
                            )
                        ],
                        h_expand=True,
                        v_expand=True,
                    ),
                    Label(
                        label=self._notification.body,  # type: ignore
                        line_wrap="word-char",
                        v_align="start",
                        h_align="start",
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


class NotificationRevealer(Revealer):
    def __init__(self, notification: Notification, on_transition_end=None, **kwargs):
        self.notif_box = NotificationWidget(notification)
        self.notification = notification
        self.on_transition_end = on_transition_end
        super().__init__(
            child=Box(
                children=[self.notif_box],
            ),
            transition_duration=300,
            transition_type="slide-left",
        )

        self.connect(
            "notify::child-revealed",
            self._on_child_revealed,
        )
        self.notification.connect("closed", self.on_resolved)

    def _on_child_revealed(self, *args):
        if not self.get_child_revealed():
            if self.on_transition_end:
                self.on_transition_end()
            self.destroy()

    def on_resolved(
        self,
        notification: Notification,
        reason: NotificationCloseReason,
    ):
        self.set_property("transition-type", "slide-right")
        self.set_reveal_child(False)


class ModusNoti(Window):
    def __init__(self):
        self._server = Notifications()
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
        new_box = NotificationRevealer(notification, on_transition_end=None)
        self.notifications.add(new_box)
        new_box.set_reveal_child(True)
