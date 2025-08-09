from fabric.widgets.centerbox import CenterBox
from loguru import logger
from collections import defaultdict

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from modules.notification.notification import (
    NotificationWidget,
    cleanup_notification_image_cache,
    cleanup_all_notification_caches,
    cleanup_notification_specific_caches,
)
from services.modus import notification_service
from widgets.wayland import WaylandWindow as Window
from fabric.widgets.image import Image
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer


class ExpandableNotificationGroup(Box):
    def __init__(self, app_name, notifications, **kwargs):
        super().__init__(
            name="notification-group", orientation="v", spacing=0, **kwargs
        )

        self.app_name = app_name
        self.notifications = notifications
        self.is_expanded = False

        # Create collapsed state (shows only latest notification)
        self.create_collapsed_state()

    def create_collapsed_state(self):
        from widgets.custom_image import CustomImage

        latest_notification = self.notifications[0]  # Most recent notification

        # Create clickable event box
        self.collapsed_eventbox = EventBox(
            events=["button-press-event"],
        )
        self.collapsed_eventbox.connect("button-press-event", self.on_clicked)

        # Only create stacked effect if we have multiple notifications
        num_notifications = len(self.notifications)

        if num_notifications == 1:
            # Single notification - no stacking needed
            single_notification = Box(
                name="single-notification-content",
                spacing=8,
                children=[
                    Box(
                        name="notification-image",
                        children=CustomImage(
                            pixbuf=self._get_notification_pixbuf(
                                latest_notification._notification
                            )
                        ),
                    ),
                    Box(
                        name="notification-text",
                        orientation="v",
                        v_align="center",
                        h_expand=True,
                        children=[
                            Box(
                                name="notification-summary-box",
                                orientation="h",
                                children=[
                                    Label(
                                        name="notification-summary",
                                        markup=f"<b>{self.app_name}</b>",
                                        h_align="start",
                                        ellipsization="end",
                                    ),
                                ],
                            ),
                            Label(
                                name="notification-body",
                                markup=latest_notification._notification.summary.replace(
                                    "\n", " "
                                ),
                                h_align="start",
                                ellipsization="end",
                            ),
                        ],
                    ),
                ],
            )
            self.collapsed_eventbox.add(single_notification)
        else:
            # Multiple notifications - create stacked effect
            # Create container for the entire stack
            stack_container = Box(
                name="notification-stack-container",
                orientation="v",
                spacing=0,
            )

            # Add bottom shadow layer first (deepest)
            if num_notifications >= 3:
                bottom_shadow = Box(
                    name="stack-shadow-bottom",
                    # style="min-height: 16px; margin-left: 20px; margin-right: -4px; margin-bottom: -8px;",
                )
                stack_container.add(bottom_shadow)

            # Add middle shadow layer
            if num_notifications >= 2:
                middle_shadow = Box(
                    name="stack-shadow-middle",
                    # style="min-height: 20px; margin-left: 10px; margin-right: -2px; margin-bottom: -12px;",
                )
                stack_container.add(middle_shadow)

            # Add the main notification content on top
            main_notification = Box(
                name="stack-main-notification",
                spacing=8,
                children=[
                    Box(
                        name="notification-image",
                        children=CustomImage(
                            pixbuf=self._get_notification_pixbuf(
                                latest_notification._notification
                            )
                        ),
                    ),
                    Box(
                        name="notification-text",
                        orientation="v",
                        v_align="center",
                        h_expand=True,
                        children=[
                            Box(
                                name="notification-summary-box",
                                orientation="h",
                                children=[
                                    Label(
                                        name="notification-summary",
                                        markup=f"<b>{self.app_name}</b>",
                                        h_align="start",
                                        ellipsization="end",
                                    ),
                                ],
                            ),
                            Label(
                                name="notification-body",
                                markup=latest_notification._notification.summary.replace(
                                    "\n", " "
                                ),
                                h_align="start",
                                ellipsization="end",
                            ),
                        ],
                    ),
                    Box(
                        name="notification-count",
                        children=[
                            Label(
                                name="notification-count-label",
                                label=f"{len(self.notifications)}",
                                h_align="end",
                            )
                        ],
                    ),
                ],
            )
            stack_container.add(main_notification)
            self.collapsed_eventbox.add(stack_container)

        self.add(self.collapsed_eventbox)

        # Create expanded state (hidden initially)
        self.create_expanded_state()

    def create_expanded_state(self):
        self.expanded_box = Box(
            name="notification-group-expanded",
            orientation="v",
            spacing=5,
            visible=False,
        )

        # Header with app name and controls

        # App name and show less button
        header_content = Box(
            orientation="h",
            h_expand=True,
            children=[
                Label(
                    name="notification-group-title",
                    markup=f"<b>{self.app_name}</b>",
                    h_align="start",
                    h_expand=True,
                ),
                Button(
                    name="notification-show-less",
                    label="Show less",
                    on_clicked=self.collapse,
                    h_align="end",
                ),
                Button(
                    name="notification-close-all",
                    label="×",
                    on_clicked=self.close_all,
                    h_align="end",
                ),
            ],
        )

        self.expanded_box.add(header_content)

        # Individual notifications
        for notification in self.notifications:
            notification_widget = NotificationCenterWidget(notification=notification)
            self.expanded_box.add(notification_widget)

        self.add(self.expanded_box)

    def _get_notification_pixbuf(self, notification):
        # Use the same logic as NotificationWidget
        try:
            if hasattr(notification, "image_pixbuf") and notification.image_pixbuf:
                return notification.image_pixbuf.scale_simple(
                    35, 35, 2
                )  # GdkPixbuf.InterpType.BILINEAR = 2
        except Exception:
            pass

        # Fallback to app icon
        try:
            from modules.notification.notification import cache_notification_icon

            cached_app_icon = cache_notification_icon(notification.app_icon, (35, 35))
            if cached_app_icon:
                return cached_app_icon
        except Exception:
            pass

        # Ultimate fallback
        from modules.notification.notification import get_fallback_notification_icon

        return get_fallback_notification_icon((35, 35))

    def on_clicked(self, widget, event):
        if event.button == 1:  # Left click
            self.expand()
        return True

    def expand(self, *args):
        self.is_expanded = True
        self.collapsed_eventbox.set_visible(False)
        self.expanded_box.set_visible(True)

    def collapse(self, *args):
        self.is_expanded = False
        self.collapsed_eventbox.set_visible(True)
        self.expanded_box.set_visible(False)

    def close_all(self, *args):
        # Close all notifications in this group
        for notification in self.notifications:
            try:
                cleanup_notification_specific_caches(
                    app_icon_source=getattr(notification, "app_icon_source", None),
                    notification_image_cache_key=getattr(
                        notification, "notification_image_cache_key", None
                    ),
                )
                notification_service.remove_cached_notification(notification.cache_id)
            except Exception as e:
                logger.error(
                    f"Error removing notification {notification.cache_id}: {e}"
                )


class NotificationCenterWidget(NotificationWidget):
    def __init__(self, notification, **kwargs):
        self.notification_id = notification.cache_id

        super().__init__(
            notification._notification,
            timeout_ms=0,
            show_close_button=True,
            name="notification-centre-notifs",
            **kwargs,
        )

    def create_content(self, notification):
        # Create our custom close button for notification center
        from widgets.custom_image import CustomImage

        self.close_button = Button(
            name="notif-close-button",
            image=CustomImage(icon_name="close-symbolic", icon_size=18),
            visible=True,  # Always visible in notification center
            on_clicked=self._on_close_clicked,
        )
        self.close_button.connect(
            "enter-notify-event", lambda *_: self.hover_button(self.close_button)
        )
        self.close_button.connect(
            "leave-notify-event", lambda *_: self.unhover_button(self.close_button)
        )

        # Create the content box manually with our custom close button
        from fabric.widgets.box import Box
        from fabric.widgets.label import Label

        return Box(
            name="notification-content",
            spacing=8,
            children=[
                Box(
                    name="notification-image",
                    children=CustomImage(
                        pixbuf=self._get_notification_pixbuf(notification)
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
                            ],
                        ),
                        (
                            Label(
                                markup=notification.body.replace("\n", " "),
                                h_align="start",
                                ellipsization="end",
                            )
                            if notification.body
                            else Label(
                                markup="",
                                h_align="start",
                                ellipsization="end",
                            )
                        ),
                    ],
                ),
                Box(h_expand=True),
                Box(
                    orientation="v",
                    children=[
                        self.close_button,  # Use our custom close button
                        Box(v_expand=True),
                    ],
                ),
            ],
        )

    # Override to disable the action buttons
    def create_action_buttons(self, notification):
        return Box(name="notification-action-buttons")

    def _on_close_clicked(self, *args):
        try:
            # Clean up this notification's cached icons AND images
            cleanup_notification_specific_caches(
                app_icon_source=getattr(self, "app_icon_source", None),
                notification_image_cache_key=getattr(
                    self, "notification_image_cache_key", None
                ),
            )
            logger.debug(
                f"Cleaned up all caches for notification center: {self.notification_id}"
            )

            notification_service.remove_cached_notification(self.notification_id)
        except Exception as e:
            logger.error(f"Error removing notification {self.notification_id}: {e}")

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

        # Group notifications by app name
        self.notification_groups = defaultdict(list)
        self.group_widgets = {}

        notification_service.connect(
            "cached-notification-added", self.on_notification_added
        )
        notification_service.connect(
            "cached-notification-removed", self.on_notification_removed
        )
        notification_service.connect("clear-all", self.on_clear_all)
        notification_service.connect("notify::count", self.on_count_changed)

        main_box = Box(
            orientation="v",
            spacing=5,
            name="noti-center-box",
        )

        self.scrolled = ScrolledWindow(h_expand=False, v_expand=False)
        self.notifications_box = Box(
            v_expand=False,
            h_expand=False,
            style="margin: 1px 0px 1px 1px;",
            orientation="v",
            spacing=5,
        )
        self.scrolled.add(self.notifications_box)
        main_box.add(self.scrolled)

        # # No notifications label
        # self.not_found_label = Label(
        #     label="No notifications",
        #     h_align="center",
        #     v_align="center",
        #     h_expand=True,
        #     v_expand=True,
        #     style="color: #888888; font-style: italic; margin: 20px;",
        #     visible=(notification_service.count == 0),
        # )
        # main_box.add(self.not_found_label)

        self.clear_all_button = Button(
            name="noti-clear-button",
            label="Clear",
            on_clicked=self.clear_all_notifications,
            visible=(notification_service.count > 0),
        )
        self.button_centre_box = CenterBox(
            center_children=[self.clear_all_button],
        )
        main_box.add(self.button_centre_box)

        self.children = main_box

        # Load existing notifications and group them
        self._rebuild_notification_groups()

        self.add_keybinding("Escape", self._on_escape_pressed)
        self.connect("destroy", self._on_destroy)

    def _rebuild_notification_groups(self):
        """Rebuild notification groups from scratch"""
        # Clear existing groups
        self.notification_groups.clear()
        self.group_widgets.clear()

        # Clear notifications box
        for child in self.notifications_box.get_children():
            child.destroy()

        # Group notifications by app name
        for cached_notification in notification_service.cached_notifications:
            app_name = cached_notification._notification.app_name
            self.notification_groups[app_name].append(cached_notification)

        # Create group widgets
        for app_name, notifications in self.notification_groups.items():
            # Sort notifications by timestamp (newest first)
            notifications.sort(key=lambda n: getattr(n, "timestamp", 0), reverse=True)

            group_widget = ExpandableNotificationGroup(app_name, notifications)
            self.group_widgets[app_name] = group_widget
            self.notifications_box.add(group_widget)

    def on_notification_added(self, service, cached_notification):
        try:
            app_name = cached_notification._notification.app_name

            # Add to groups
            self.notification_groups[app_name].insert(
                0, cached_notification
            )  # Insert at beginning (newest first)

            # Update or create group widget
            if app_name in self.group_widgets:
                # Update existing group
                group_widget = self.group_widgets[app_name]
                group_widget.notifications = self.notification_groups[app_name]
                # Refresh the group widget
                self._refresh_group_widget(group_widget)
            else:
                # Create new group widget
                group_widget = ExpandableNotificationGroup(
                    app_name, self.notification_groups[app_name]
                )
                self.group_widgets[app_name] = group_widget
                self.notifications_box.pack_start(group_widget, False, False, 0)
                group_widget.show_all()

            logger.debug(f"Added notification to group {app_name}")
        except Exception as e:
            logger.error(f"Error adding notification to group: {e}")

    def _refresh_group_widget(self, group_widget):
        """Refresh a group widget's content"""
        try:
            # Remove existing children
            for child in group_widget.get_children():
                group_widget.remove(child)

            # Recreate content
            group_widget.create_collapsed_state()
            group_widget.show_all()

        except Exception as e:
            logger.error(f"Error refreshing group widget: {e}")

    def on_notification_removed(self, service, cached_notification):
        try:
            app_name = cached_notification._notification.app_name

            # Remove from groups
            if app_name in self.notification_groups:
                self.notification_groups[app_name] = [
                    n
                    for n in self.notification_groups[app_name]
                    if n.cache_id != cached_notification.cache_id
                ]

                # If no more notifications for this app, remove group widget
                if not self.notification_groups[app_name]:
                    if app_name in self.group_widgets:
                        group_widget = self.group_widgets[app_name]
                        group_widget.destroy()
                        del self.group_widgets[app_name]
                        del self.notification_groups[app_name]
                else:
                    # Update existing group widget
                    group_widget = self.group_widgets[app_name]
                    group_widget.notifications = self.notification_groups[app_name]
                    self._refresh_group_widget(group_widget)

            # Clean up caches
            cleanup_notification_specific_caches(
                app_icon_source=getattr(cached_notification, "app_icon_source", None),
                notification_image_cache_key=getattr(
                    cached_notification, "notification_image_cache_key", None
                ),
            )

            logger.debug(f"Removed notification from group {app_name}")
        except Exception as e:
            logger.error(f"Error removing notification from group: {e}")

    def on_clear_all(self, service):
        try:
            # Clear all groups
            self.notification_groups.clear()
            self.group_widgets.clear()

            # Clear all remaining cached notification images AND icons
            cleanup_all_notification_caches()
            for child in self.notifications_box.get_children():
                child.destroy()
            logger.debug("Cleared all notification groups and remaining cached images")
        except Exception as e:
            logger.error(f"Error clearing notification groups: {e}")

    def on_count_changed(self, service, count=None):
        current_count = notification_service.count
        self.not_found_label.set_visible(current_count == 0)
        self.clear_all_button.set_visible(current_count > 0)
        self.scrolled.set_visible(current_count > 0)

    def clear_all_notifications(self, *_):
        # Clear all groups
        self.notification_groups.clear()
        self.group_widgets.clear()

        # Clear all remaining cached notification images AND icons when clear all is clicked
        cleanup_all_notification_caches()  # Clear ALL caches (icons + images)
        notification_service.clear_all_cached_notifications()
        if hasattr(self, "mousecapture"):
            self.mousecapture.hide_child_window()

    def _on_escape_pressed(self, *_):
        if hasattr(self, "mousecapture"):
            self.mousecapture.hide_child_window()

    def _init_mousecapture(self, mousecapture):
        self.mousecapture = mousecapture

    def _set_mousecapture(self, visible):
        # No need to refresh on visibility change since we use signals
        pass

    def _on_destroy(self, *_):
        try:
            notification_service.disconnect(
                "cached-notification-added", self.on_notification_added
            )
            notification_service.disconnect(
                "cached-notification-removed", self.on_notification_removed
            )
            notification_service.disconnect("clear-all", self.on_clear_all)
            notification_service.disconnect("notify::count", self.on_count_changed)
        except Exception as e:
            logger.error(f"Error disconnecting signals: {e}")
