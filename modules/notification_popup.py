import time

import gi

gi.require_version("GdkPixbuf", "2.0")

from fabric.notifications import (
    Notification,
    NotificationAction,
    NotificationCloseReason,
    Notifications,
)
from fabric.utils import invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window
from gi.repository import GdkPixbuf, GLib, GObject
from snippets import Animator, CustomImage


class AnimatedCircularProgressBar(CircularProgressBar):
    def __init__(self, duration=0.6, bezier_curve=(0.34, 1.56, 0.64, 1.0), **kwargs):
        super().__init__(**kwargs)

        self.animator = (
            Animator(
                bezier_curve=bezier_curve,
                duration=duration,
                min_value=self.min_value,
                max_value=self.value,
                tick_widget=self,
                notify_value=lambda p, *_: self.set_value(p.value),
            )
            .build()
            .play()
            .unwrap()
        )

    def animate_value(self, value: float):
        self.animator.pause()
        self.animator.min_value = self.value
        self.animator.max_value = value
        self.animator.play()
        return


class ActionButton(Button):
    def __init__(
        self, action: NotificationAction, action_number: int, total_actions: int
    ):
        self.action = action
        super().__init__(
            label=action.label,
            h_expand=True,
            on_clicked=self.on_clicked,
        )
        if action_number == 0:
            self.add_style_class("start-action")
        elif action_number == total_actions - 1:
            self.add_style_class("end-action")
        else:
            self.add_style_class("middle-action")

    def on_clicked(self, *_):
        self.action.invoke()
        self.action.parent.close("dismissed-by-user")


class NotificationWidget(Box):
    def __init__(self, notification: Notification, **kwargs):
        super().__init__(
            name="notification",
            spacing=8,
            orientation="v",
            **kwargs,
        )

        self._notification = notification
        self._timer = None
        self.anim_parts = 20
        self.anim_interval = self.get_timeout() / self.anim_parts
        self.timeout_in_sec = self.get_timeout() / 1000
        self.time = GLib.DateTime.new_from_unix_local(time.time()).format("%m/%d")
        self.connect("button-press-event", self.on_button_press)

        header_container = Box(spacing=8, orientation="h")
        self.progress_timeout = AnimatedCircularProgressBar(
            name="notification-circular-progress-bar",
            size=30,
            min_value=0,
            max_value=1,
            radius_color=True,
            value=0,
        )

        header_container.children = (
            self.get_icon(notification.app_icon, notification.app_name, 25),
            Label(
                markup=str(
                    self._notification.summary
                    if self._notification.summary
                    else notification.app_name
                ),
                h_align="start",
                style="font-weight: 900;",
                ellipsization="end",
            ),
        )

        header_container.pack_end(
            Box(
                v_align="start",
                children=(
                    Overlay(
                        child=self.progress_timeout,
                        overlays=Button(
                            image=Image(
                                icon_name="window-close-symbolic",
                                icon_size=16,
                            ),
                            style_classes="close-button",
                            on_clicked=lambda *_: self._notification.close(
                                "dismissed-by-user"
                            ),
                        ),
                    ),
                ),
            ),
            False,
            False,
            0,
        )

        body_container = Box(spacing=4, orientation="h")

        if image_pixbuf := self._notification.image_pixbuf:
            body_container.add(
                Box(
                    v_expand=True,
                    v_align="center",
                    children=CustomImage(
                        pixbuf=image_pixbuf.scale_simple(
                            64, 64, GdkPixbuf.InterpType.BILINEAR
                        ),
                        style_classes="image",
                    ),
                )
            )

        body_container.add(
            Label(
                markup=self._notification.body,
                line_wrap="word-char",
                v_align="start",
                ellipsization="end",
                max_chars_width=40,
                h_align="start",
            )
        )

        actions_container = Box(
            spacing=4,
            orientation="h",
            name="notification-action-buttons",
            children=[
                ActionButton(action, i, len(self._notification.actions))
                for i, action in enumerate(self._notification.actions)
            ],
            h_expand=True,
        )

        self.add(header_container)
        self.add(body_container)
        self.add(actions_container)

        # Destroy this widget once the notification is closed
        self._notification.connect(
            "closed",
            lambda *_: (
                parent.remove(self) if (parent := self.get_parent()) else None,  # type: ignore
                self.destroy(),
            ),
            invoke_repeater(
                5 * 1000,
                lambda: self._notification.close("expired"),
                initial_call=False,
            ),
        )

        self.start_timer()

    def start_timer(self):
        self._timer = GObject.timeout_add(200, self.update_progress)

    def update_progress(self):
        self.progress_timeout.animate_value(
            self.progress_timeout.value + 1 / self.anim_parts
        )
        if self.progress_timeout.value >= self.timeout_in_sec:
            self.progress_timeout.value = self.timeout_in_sec
            self.stop_timer()
        return True  # Continue the timer

    def stop_timer(self):
        if self._timer:
            GObject.source_remove(self._timer)
            self._timer = None

    def get_icon(self, app_icon, app_name, size) -> Image:
        app_name = (
            app_name.lower().replace(" ", "-")
            if isinstance(app_name, str)
            else app_name
        )
        if isinstance(app_icon, str) and app_icon.strip():
            if app_icon.startswith("file://") or app_icon.startswith("/"):
                file_path = app_icon[7:] if app_icon.startswith("file://") else app_icon
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_path)
                    scaled_pixbuf = pixbuf.scale_simple(
                        size, size, GdkPixbuf.InterpType.BILINEAR
                    )
                    return Image(name="notification-icon", pixbuf=scaled_pixbuf)
                except Exception as e:
                    print(f"DEBUG: Failed to load image from {file_path}: {e}")

        if app_icon and not app_icon.startswith(("file://", "/")):
            icon_name = app_icon
        elif app_name and app_name.strip() not in ["notify-send", ""]:
            icon_name = app_name.strip()
        else:
            icon_name = "dialog-information-symbolic"

        return Image(name="notification-icon", icon_name=icon_name, icon_size=size)

    def on_button_press(self, _, event):
        if event.button != 1:
            (self._notification.close("dismissed-by-user"),)

    def get_timeout(self):
        return (
            self._notification.timeout if self._notification.timeout != -1 else 5 * 1000
        )


class NotificationRevealer(Revealer):
    def __init__(self, notification: Notification, **kwargs):
        self.notif_box = NotificationWidget(notification)
        self._notification = notification
        super().__init__(
            child=Box(
                style="margin: 12px;",
                children=[self.notif_box],
            ),
            transition_duration=500,
            transition_type="crossfade",
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
        self.set_reveal_child(False)


class NotificationPopup(Window):
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
            anchor="bottom",
            child=self.notifications,
            layer="overlay",
            all_visible=True,
            visible=True,
            exclusive=False,
        )

    def on_new_notification(self, fabric_notif, id):
        new_box = NotificationRevealer(fabric_notif.get_notification_from_id(id))
        self.notifications.add(new_box)
        new_box.set_reveal_child(True)
