import uuid

from fabric.notifications.service import Notification, NotificationAction, Notifications
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from gi.repository import GLib, Gtk
from loguru import logger

import config.data as data
import utils.icons as icons
from utils.custom_image import CustomImage
from utils.wayland import WaylandWindow as Window
from utils.notification_utils import (
    LIMITED_APPS,
    cache_notification_pixbuf,
    load_scaled_pixbuf,
    get_shared_notification_history,
    NotificationHistory,
    delete_cached_image
)


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
        if (
            hasattr(self, "cached_image_path")
            and self.cached_image_path
            and (not self._is_history or from_history_delete)
        ):
            delete_cached_image(self.cached_image_path)
        self._destroyed = True
        self.stop_timeout()
        super().destroy()

    def hover_button(self, button):
        if self._container:
            self._container.pause_and_reset_all_timeouts()

    def unhover_button(self, button):
        if self._container:
            self._container.resume_all_timeouts()


class NotificationContainer(Box):

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
        if app_name in LIMITED_APPS:
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

    def show_previous(self, *args):
        if self.current_index > 0:
            self.current_index -= 1
            self.stack.set_visible_child(self.notifications[self.current_index])
            self.update_navigation_buttons()

    def show_next(self, *args):
        if self.current_index < len(self.notifications) - 1:
            self.current_index += 1
            self.stack.set_visible_child(self.notifications[self.current_index])
            self.update_navigation_buttons()

    def update_navigation_buttons(self):
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

            notif_box.set_is_history(True)
            notification_history_instance.add_notification(notif_box)
            notif_box.stop_timeout()

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
        if self._is_destroying:
            return
        for notification in self.notifications[:]:
            try:
                if hasattr(notification, "pause_timeout"):
                    notification.pause_timeout()
            except Exception as e:
                logger.error(f"Error pausing timeout: {e}")

    def resume_all_timeouts(self):
        if self._is_destroying:
            return
        for notification in self.notifications[:]:
            try:
                if hasattr(notification, "resume_timeout"):
                    notification.resume_timeout()
            except Exception as e:
                logger.error(f"Error resuming timeout: {e}")

    def close_all_notifications(self, *args):
        notifications_to_close = self.notifications.copy()
        for notification_box in notifications_to_close:
            notification_box.notification.close("dismissed-by-user")


class NotificationPopup(Window):
    def __init__(self, **kwargs):
        y_pos = data.NOTIF_POS.lower() if hasattr(data, "NOTIF_POS") else "top"
        x_pos = "right"

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
            self.widgets.notification_history
            if self.widgets
            else get_shared_notification_history()
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
