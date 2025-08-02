from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from modules.notification.notification import NotificationWidget
from utils.roam import modus_service
from widgets.wayland import WaylandWindow as Window
from fabric.widgets.image import Image


class NotificationCenterWidget(NotificationWidget):
    def __init__(self, notification, notification_id, **kwargs):
        self.notification_id = notification_id

        super().__init__(notification, timeout_ms=0, show_close_button=True, **kwargs)

    def create_close_button(self):
        close_button = Button(
            name="notif-close-button",
            child=Image(icon_name="close-symbolic", name="notif-close-label", size=5),
            on_clicked=self._on_close_clicked,
        )
        close_button.connect(
            "enter-notify-event", lambda *_: self.hover_button(close_button)
        )
        close_button.connect(
            "leave-notify-event", lambda *_: self.unhover_button(close_button)
        )
        return close_button

    # Override to disable the action buttons
    def create_action_buttons(self, notification):
        return Box(name="notification-action-buttons")

    def _on_close_clicked(self, *args):
        try:
            modus_service.remove_notification(self.notification_id)
        except Exception as e:
            logger.error(f"Error removing notification {self.notification_id}: {e}")
        finally:
            self.destroy()

    # Override to disable timeout functionality
    def start_timeout(self):
        pass

    # Override to disable timeout functionality
    def stop_timeout(self):
        pass

    # Override to disable auto-close functionality
    def close_notification(self):
        pass


class NotificationCenter(Window):
    def __init__(self):
        super().__init__(
            layer="overlay",
            anchor="top right",
            visible=False,
            keyboard_mode="on-demand",
            title="modus",
        )

        NOTIFICATION_CENTER_WIDTH = 410
        self.set_size_request(NOTIFICATION_CENTER_WIDTH, 600)

        main_box = Box(
            orientation="v",
            spacing=5,
            name="noti-center-box",
        )

        # Header
        header = Box(
            orientation="h",
            spacing=10,
            style="margin-bottom: 10px;",
        )
        header.add(
            Label(
                label="Notification Center",
                h_align="center",
                h_expand=True,
                style="font-size: 16px; font-weight: bold; color: #ffffff;",
            )
        )
        main_box.add(header)

        self.scrolled = ScrolledWindow(h_expand=True, v_expand=True)
        self.notifications_box = Box(
            v_expand=True,
            h_expand=True,
            style="margin: 1px 0px 1px 1px;",
            orientation="v",
            spacing=5,
        )
        self.scrolled.add(self.notifications_box)
        main_box.add(self.scrolled)

        self.clear_all_button = Button(
            name="noti-clear-button",
            label="Clear All",
            on_clicked=self.clear_all_notifications,
        )
        main_box.add(self.clear_all_button)

        self.children = main_box

        # Connect service signal
        modus_service.connect(
            "notification_count_changed", self._on_notification_count_changed
        )

        self.add_keybinding("Escape", self._on_escape_pressed)

        self.connect("destroy", self._on_destroy)

    def clear_all_notifications(self, *_):
        modus_service.clear_all_notifications()
        self.refresh_notifications()
        self.mousecapture.hide_child_window()

    def _on_escape_pressed(self, *_):
        self.mousecapture.hide_child_window()

    def _init_mousecapture(self, mousecapture):
        self.mousecapture = mousecapture

    def _set_mousecapture(self, visible):
        self.refresh_notifications()

    def _on_notification_count_changed(self, *_):
        self.refresh_notifications()

    def _on_destroy(self, *_):
        # Disconnect service signal
        modus_service.disconnect(
            "notification_count_changed", self._on_notification_count_changed
        )

    def refresh_notifications(self):
        try:
            for child in self.notifications_box.get_children():
                child.destroy()

            notifications_with_ids = modus_service.get_deserialized_with_ids()
            logger.info(f"Found {len(notifications_with_ids)} notifications to display")

            if not notifications_with_ids:
                no_notifications_label = Label(
                    label="No notifications",
                    h_align="center",
                    style="color: #888888; font-style: italic; margin: 20px;",
                )
                self.notifications_box.add(no_notifications_label)
                return

            for notification, notification_id in notifications_with_ids:
                try:
                    logger.debug(
                        f"Notification from {notification.app_name}: ID={
                            notification_id
                        }"
                    )
                    notification_widget = NotificationCenterWidget(
                        notification=notification, notification_id=notification_id
                    )
                    self.notifications_box.add(notification_widget)
                except Exception as e:
                    logger.error(f"Error creating notification widget: {e}")

            self.clear_all_button.set_visible(len(notifications_with_ids) > 0)

        except Exception as e:
            logger.error(f"Error refreshing notifications: {e}")
