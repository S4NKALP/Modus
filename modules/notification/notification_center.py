from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from modules.notification.notification import NotificationWidget, cleanup_notification_image_cache, cleanup_all_notification_caches, cleanup_notification_specific_caches
from services.modus import notification_service
from widgets.wayland import WaylandWindow as Window
from fabric.widgets.image import Image


class NotificationCenterWidget(NotificationWidget):
    def __init__(self, notification, **kwargs):
        self.notification_id = notification.cache_id

        super().__init__(
            notification._notification, timeout_ms=0, show_close_button=True, **kwargs
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
                app_icon_source=getattr(self, 'app_icon_source', None),
                notification_image_cache_key=getattr(self, 'notification_image_cache_key', None)
            )
            logger.debug(f"Cleaned up all caches for notification center: {self.notification_id}")
            
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

        header = Box(
            orientation="h",
            spacing=10,
            style="margin-bottom: 10px;",
        )

        header.add(
            Label(
                label="Notification Center",
                h_align="start",
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

        # No notifications label
        self.not_found_label = Label(
            label="No notifications",
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
            style="color: #888888; font-style: italic; margin: 20px;",
            visible=(notification_service.count == 0),
        )
        main_box.add(self.not_found_label)

        self.clear_all_button = Button(
            name="noti-clear-button",
            label="Clear All",
            on_clicked=self.clear_all_notifications,
            visible=(notification_service.count > 0),
        )
        main_box.add(self.clear_all_button)

        self.children = main_box

        # Load existing notifications
        for cached_notification in notification_service.cached_notifications:
            self.notifications_box.add(
                NotificationCenterWidget(notification=cached_notification)
            )

        self.add_keybinding("Escape", self._on_escape_pressed)
        self.connect("destroy", self._on_destroy)

    def on_notification_added(self, service, cached_notification):
        try:
            notification_widget = NotificationCenterWidget(
                notification=cached_notification
            )
            # Insert at the beginning to show newest first
            self.notifications_box.pack_start(notification_widget, False, False, 0)
            notification_widget.show_all()
            logger.debug(
                f"Added notification widget for {cached_notification.app_name}"
            )
        except Exception as e:
            logger.error(f"Error adding notification widget: {e}")

    def on_notification_removed(self, service, cached_notification):
        try:
            # Find and remove the corresponding widget with cache cleanup
            for child in self.notifications_box.get_children():
                if (
                    hasattr(child, "notification_id")
                    and child.notification_id == cached_notification.cache_id
                ):
                    # Clean up the widget's cached icons AND images before destroying
                    cleanup_notification_specific_caches(
                        app_icon_source=getattr(child, 'app_icon_source', None),
                        notification_image_cache_key=getattr(child, 'notification_image_cache_key', None)
                    )
                    logger.debug(f"Cleaned up all caches for removed notification: {child.notification_id}")
                    
                    child.destroy()
                    break
            logger.debug(
                f"Removed notification widget and all caches for {cached_notification.app_name}"
            )
        except Exception as e:
            logger.error(f"Error removing notification widget: {e}")

    def on_clear_all(self, service):
        try:
            # Clear all remaining cached notification images AND icons  
            # Individual notifications clean up their own images, this handles any remaining
            cleanup_all_notification_caches()
            for child in self.notifications_box.get_children():
                child.destroy()
            logger.debug("Cleared all notification widgets and remaining cached images")
        except Exception as e:
            logger.error(f"Error clearing notification widgets: {e}")

    def on_count_changed(self, service, count=None):
        current_count = notification_service.count
        self.not_found_label.set_visible(current_count == 0)
        self.clear_all_button.set_visible(current_count > 0)
        self.scrolled.set_visible(current_count > 0)

    def clear_all_notifications(self, *_):
        # Clear all remaining cached notification images AND icons when clear all is clicked
        # Individual notifications clean up their own images, this handles any remaining
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
