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
from fabric.utils import invoke_repeater, get_relative_path

from utils.roam import modus_service

from utils.custom_image import CustomImage

from gi.repository import GdkPixbuf  # type: ignore


NOTIFICATION_WIDTH = 360
NOTIFICATION_IMAGE_SIZE = 48
NOTIFICATION_TIMEOUT = 10 * 1000


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

        self.image = notification.image_pixbuf
        body_container = Box(spacing=4, orientation="h")

        if self._notification.image_pixbuf:
            body_container.add(
                CustomImage(
                    name="noti-image",
                    pixbuf=self.image.scale_simple(  # type: ignore
                        NOTIFICATION_IMAGE_SIZE,
                        NOTIFICATION_IMAGE_SIZE,
                        GdkPixbuf.InterpType.BILINEAR,
                    ),
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
