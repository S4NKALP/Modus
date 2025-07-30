from typing import cast

from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from utils.wayland import WaylandWindow as Window
from fabric.notifications import (
    NotificationAction,
    Notifications,
    Notification,
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
        body_container = Box(spacing=4, orientation="h")

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
        parent.remove(self) if (parent := self.get_parent()) else None,  # type: ignore
        self.destroy()


class EnvNoti(Window):
    def __init__(self, **kwargs):
        super().__init__(
            margin="8px 8px 8px 8px",
            name="notification-window",
            title="Notification Center",
            layer="overlay",
            anchor="top right",
            child=Box(
                size=2,
                spacing=4,
                orientation="v",
            ).build(
                lambda viewport, _: Notifications(
                    on_notification_added=self.on_notification_added
                )
            ),
            **kwargs,
        )

    def on_notification_added(self, notifs_service, nid):
        modus_service.cache_notification(notifs_service.get_notification_from_id(nid))
        if modus_service.dont_disturb == "True":
            return
        self.get_child().add(
            NotificationWidget(
                cast(Notification, notifs_service.get_notification_from_id(nid))
            )
        )
