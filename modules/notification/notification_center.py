from collections import defaultdict
import time

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GLib, GdkPixbuf
from loguru import logger

from modules.notification.notification import (
    NotificationWidget,
    cache_notification_icon,
    cache_notification_image,
    get_cached_notification_image,
    get_notification_image_cache_key,
    preload_notification_assets,
    cleanup_all_notification_caches,
    cleanup_notification_specific_caches,
    get_fallback_notification_icon,
)
from services.modus import notification_service
from utils.functions import escape_markup_text
from widgets.custom_image import CustomImage
from widgets.wayland import WaylandWindow as Window
from config import data


class ExpandableNotificationGroup(Box):
    def __init__(self, app_name, notifications, **kwargs):
        super().__init__(
            name="notification-group", orientation="v", spacing=0, **kwargs
        )

        self.app_name = app_name
        self.notifications = notifications
        self.is_expanded = False  # Always start collapsed

        # Create collapsed state first (shows only latest notification)
        self.create_collapsed_state()

        # Create expanded state (hidden initially)
        self.create_expanded_state()

        # Ensure we start in collapsed state
        self.collapsed_eventbox.set_visible(True)
        self.expanded_container.set_visible(False)

    def create_collapsed_state(self):
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
            notification_widget = NotificationCenterWidget(
                notification=latest_notification
            )
            self.collapsed_eventbox.add(notification_widget)
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
                )
                stack_container.add(bottom_shadow)

            # Add middle shadow layer
            if num_notifications >= 2:
                middle_shadow = Box(
                    name="stack-shadow-middle",
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
                            pixbuf=self._get_notification_pixbuf_for_group(
                                latest_notification
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
                                markup=escape_markup_text(latest_notification._notification.summary.replace(
                                    "\n", " "
                                )),
                                max_chars_width=25,
                                h_align="start",
                                ellipsization="end",
                            ),
                        ],
                    ),
                    Box(
                        name="notification-count",
                        orientation="v",
                        children=[
                            Button(
                                name="notification-close",
                                image=CustomImage(
                                    icon_name="close-symbolic", icon_size=18
                                ),
                                visible=True,
                                on_clicked=lambda *_: self._close_single_notification_and_stop_propagation(
                                    latest_notification
                                ),
                            ),
                            Label(
                                name="notification-count-label",
                                label=f"{len(self.notifications)}",
                                h_align="end",
                            ),
                        ],
                    ),
                ],
            )
            stack_container.add(main_notification)
            self.collapsed_eventbox.add(stack_container)

        self.add(self.collapsed_eventbox)

        # Create expanded state (hidden initially)
        self.create_expanded_state()

    def _get_notification_pixbuf_for_group(self, cached_notification):
        """Get notification pixbuf using cached image key - fallback to app icon"""
        notification = cached_notification._notification
        notification_id = getattr(notification, "id", None)

        # First try to get cached notification image using stored cache key
        if (
            hasattr(cached_notification, "cache_metadata")
            and cached_notification.cache_metadata
        ):
            notification_image_cache_key = cached_notification.cache_metadata.get(
                "notification_image_cache_key"
            )
            if notification_image_cache_key:
                try:
                    cached_image = get_cached_notification_image(
                        notification_image_cache_key
                    )
                    if cached_image:
                        logger.debug(
                            f"Using cached notification image: {notification_image_cache_key}"
                        )
                        return cached_image
                except Exception as e:
                    logger.debug(f"Failed to load cached notification image: {e}")

        # Fallback to app icon using cached key
        if (
            hasattr(cached_notification, "cache_metadata")
            and cached_notification.cache_metadata
        ):
            app_icon_cache_key = cached_notification.cache_metadata.get(
                "app_icon_cache_key"
            )
            if app_icon_cache_key:
                try:
                    from modules.notification.unified_cache import get_from_cache

                    cached_app_icon = get_from_cache(app_icon_cache_key, (35, 35))
                    if cached_app_icon:
                        # logger.debug(f"Using cached app icon: {app_icon_cache_key}")
                        return cached_app_icon
                except Exception as e:
                    logger.debug(f"Failed to load cached app icon: {e}")

        # Final fallback - try to cache app icon directly if available
        try:
            app_icon_source = getattr(notification, "app_icon", None)
            if app_icon_source:
                cached_app_icon = cache_notification_icon(app_icon_source, (35, 35))
                if cached_app_icon:
                    logger.debug(
                        f"Using directly cached app icon for: {app_icon_source}"
                    )
                    return cached_app_icon
        except Exception as e:
            logger.debug(f"Failed to get directly cached app icon: {e}")

        # Ultimate fallback
        logger.debug("Using fallback notification icon")
        return get_fallback_notification_icon((35, 35))

    def create_expanded_state(self):
        # Create main expanded container
        self.expanded_container = Box(
            name="notification-group-expanded-container",
            orientation="v",
            spacing=0,
        )

        # Header with app name and controls
        self.header_content = Box(
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
                    name="notification-close-summery",
                    h_expand=False,
                    v_expand=False,
                    on_clicked=self.close_all,
                    image=CustomImage(
                        icon_name="close-symbolic",
                        name="notification-close-header",
                        icon_size=18,
                        h_align="end",
                    ),
                    visible=True,
                ),
            ],
        )

        # Wrap header in revealer for slide-up animation during collapse
        self.header_revealer = Revealer(
            child=self.header_content,
            transition_type="slide-up",
            transition_duration=300,
            child_revealed=False,
        )

        # Box for individual notifications
        self.notifications_list = Box(
            name="notification-group-notifications",
            orientation="v",
            spacing=5,
        )

        # Add individual notifications to the list
        for notification in self.notifications:
            notification_widget = NotificationCenterWidget(notification=notification)
            self.notifications_list.add(notification_widget)

        # Wrap notifications list in revealer for slide-down animation
        self.notifications_revealer = Revealer(
            child=self.notifications_list,
            transition_type="slide-down",
            transition_duration=300,
            child_revealed=False,
        )

        # Wrap notifications revealer in crossfade revealer for closing animation
        self.notifications_crossfade = Revealer(
            child=self.notifications_revealer,
            transition_type="crossfade",
            transition_duration=250,
            child_revealed=True,  # Start revealed so crossfade works on close
        )

        # Add header revealer and notifications crossfade to container
        self.expanded_container.add(self.header_revealer)
        self.expanded_container.add(self.notifications_crossfade)

        # Add the container to the main group
        self.add(self.expanded_container)

        # Hide the entire expanded container initially
        self.expanded_container.set_visible(False)

    def on_clicked(self, widget, event):
        if event.button == 1:  # Left click
            # Always allow expansion, even for single notifications
            # This ensures single notifications can show their expanded entry view
            self.expand()
        return True

    def expand(self, *args):
        """Expand to show all notifications in this group with slide-down animation"""
        self.is_expanded = True
        self.collapsed_eventbox.set_visible(False)
        self.expanded_container.set_visible(True)

        # Show header immediately (no animation on expand)
        self.header_revealer.set_reveal_child(True)

        # Ensure crossfade is revealed for expand
        self.notifications_crossfade.set_reveal_child(True)

        # Small delay then animate notifications sliding down
        GLib.timeout_add(50, lambda: self.notifications_revealer.set_reveal_child(True))
        logger.debug(f"Expanded notification group: {self.app_name}")

    def collapse(self, *args):
        """Collapse with header sliding up, notifications crossfading, then sliding up"""
        self.is_expanded = False

        # Start header slide-up and notifications crossfade simultaneously
        self.header_revealer.set_reveal_child(False)
        self.notifications_crossfade.set_reveal_child(False)

        # Show collapsed state and hide expanded container halfway through crossfade
        GLib.timeout_add(125, self._show_collapsed_midway)

        # After crossfade completes, start slide-up animation (just for cleanup)
        GLib.timeout_add(
            260, lambda: self.notifications_revealer.set_reveal_child(False)
        )

        logger.debug(f"Collapsed notification group: {self.app_name}")

    def _show_collapsed_midway(self):
        """Show collapsed state and hide expanded container to prevent deformation"""
        self.collapsed_eventbox.set_visible(True)
        self.expanded_container.set_visible(False)
        return False  # Don't repeat timeout

    def _complete_collapse(self):
        """Complete the collapse animation - no longer needed but kept for compatibility"""
        return False  # Don't repeat timeout

    def close_all(self, *args):
        """Close all notifications in this group with proper cache cleanup"""
        # Close all notifications in this group
        for notification in self.notifications:
            try:
                # Get notification cache metadata for cleanup
                cache_metadata = getattr(notification, "cache_metadata", {})

                # Clean up caches using stored metadata
                from modules.notification.notification import (
                    cleanup_notification_specific_caches,
                )

                cleanup_notification_specific_caches(
                    app_icon_source=notification._notification.app_icon,
                    notification_image_cache_key=cache_metadata.get(
                        "notification_image_cache_key"
                    ),
                )

                logger.debug(
                    f"Cleaned up caches for notification ID: {notification._notification.id}"
                )

                notification_service.remove_cached_notification(notification.cache_id)
            except Exception as e:
                logger.error(
                    f"Error removing notification {notification.cache_id}: {e}"
                )

    def _close_single_notification(self, notification):
        """Close a single notification from this group with proper cache cleanup"""
        try:
            # Get notification cache metadata for cleanup
            cache_metadata = getattr(notification, "cache_metadata", {})

            # Clean up caches using stored metadata
            from modules.notification.notification import (
                cleanup_notification_specific_caches,
            )

            cleanup_notification_specific_caches(
                app_icon_source=notification._notification.app_icon,
                notification_image_cache_key=cache_metadata.get(
                    "notification_image_cache_key"
                ),
            )

            logger.debug(
                f"Cleaned up caches for notification ID: {notification._notification.id}"
            )

            notification_service.remove_cached_notification(notification.cache_id)
            logger.debug(f"Closed single notification: {notification.cache_id}")
        except Exception as e:
            logger.error(
                f"Error removing single notification {notification.cache_id}: {e}"
            )

    def _close_single_notification_and_stop_propagation(self, notification):
        """Close notification and prevent click from expanding the group"""
        self._close_single_notification(notification)

        # If this was the last notification in the group, the group will be removed
        # by the notification_removed signal handler. If there are still notifications,
        # we need to check if this group should be removed from view.
        remaining_notifications = [
            n for n in self.notifications if n.cache_id != notification.cache_id
        ]

        if not remaining_notifications:
            # This was the last notification, the group will be destroyed by signal handler
            pass
        else:
            # Update the notifications list and refresh the view immediately
            self.notifications = remaining_notifications
            # Force immediate UI update by destroying and recreating collapsed state
            if hasattr(self, "collapsed_eventbox"):
                self.collapsed_eventbox.destroy()
            self.create_collapsed_state()
            self.show_all()

        return True  # Stop event propagation


class NotificationCenterWidget(NotificationWidget):
    def __init__(self, notification, **kwargs):
        self.notification_id = notification.cache_id
        self.cache_metadata = getattr(notification, "cache_metadata", {})

        super().__init__(
            notification._notification,
            timeout_ms=0,
            show_close_button=True,
            name="notification-centre-notifs",
            **kwargs,
        )

    def _get_notification_pixbuf(self, notification):
        """Get notification pixbuf using cached image key - fallback to app icon"""
        notification_id = getattr(notification, "id", None)

        # First try to get cached notification image using stored cache key
        if self.cache_metadata:
            notification_image_cache_key = self.cache_metadata.get(
                "notification_image_cache_key"
            )
            if notification_image_cache_key:
                try:
                    cached_image = get_cached_notification_image(
                        notification_image_cache_key
                    )
                    if cached_image:
                        logger.debug(
                            f"Using cached notification image: {notification_image_cache_key}"
                        )
                        return cached_image
                except Exception as e:
                    logger.debug(f"Failed to load cached notification image: {e}")

        # Fallback to app icon using cached key
        if self.cache_metadata:
            app_icon_cache_key = self.cache_metadata.get("app_icon_cache_key")
            if app_icon_cache_key:
                try:
                    from modules.notification.unified_cache import get_from_cache

                    cached_app_icon = get_from_cache(app_icon_cache_key, (35, 35))
                    if cached_app_icon:
                        # logger.debug(f"Using cached app icon: {app_icon_cache_key}")
                        return cached_app_icon
                except Exception as e:
                    logger.debug(f"Failed to load cached app icon: {e}")

        # Final fallback - try to cache app icon directly if available
        try:
            app_icon_source = getattr(notification, "app_icon", None)
            if app_icon_source:
                cached_app_icon = cache_notification_icon(app_icon_source, (35, 35))
                if cached_app_icon:
                    logger.debug(
                        f"Using directly cached app icon for: {app_icon_source}"
                    )
                    return cached_app_icon
        except Exception as e:
            logger.debug(f"Failed to get directly cached app icon: {e}")

        # Ultimate fallback
        logger.debug("Using fallback notification icon")
        return get_fallback_notification_icon((35, 35))

    def create_content(self, notification):
        # Create our custom close button for notification center

        self.close_button = Button(
            name="notif-close-button",
            image=CustomImage(
                icon_name="close-symbolic", name="notification-close", icon_size=18
            ),
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
                                    markup=escape_markup_text(notification.summary.replace("\n", " ")),
                                    h_align="start",
                                    max_chars_width=25,
                                    ellipsization="end",
                                ),
                            ],
                        ),
                        (
                            Label(
                                markup=escape_markup_text(notification.body.replace("\n", " ")),
                                h_align="start",
                                max_chars_width=35,
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
            # Use instance cache metadata instead of notification attribute
            cache_metadata = self.cache_metadata

            # Clean up caches using stored metadata
            from modules.notification.notification import (
                cleanup_notification_specific_caches,
            )

            cleanup_notification_specific_caches(
                app_icon_source=self.notification.app_icon,
                notification_image_cache_key=cache_metadata.get(
                    "notification_image_cache_key"
                ),
            )

            logger.debug(
                f"Cleaned up caches for notification center ID: {self.notification.id}"
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
        return False


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

        # No notifications label - REMOVED

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

        # Wrap main content in revealer for slide-left animation
        self.main_revealer = Revealer(
            child=main_box,
            transition_type="slide-left",
            transition_duration=400,
            child_revealed=False,
        )

        self.children = self.main_revealer

        # Load existing notifications and group them
        self._rebuild_notification_groups()

        self.add_keybinding("Escape", self._on_escape_pressed)
        self.connect("destroy", self._on_destroy)

    def _rebuild_notification_groups(self):
        """Rebuild notification groups from scratch with enhanced asset preloading and debugging"""
        # Clear existing groups
        self.notification_groups.clear()
        self.group_widgets.clear()

        # Clear notifications box
        for child in self.notifications_box.get_children():
            child.destroy()

        # Group notifications by app name and preload assets with debugging
        rebuild_count = 0
        for cached_notification in notification_service.cached_notifications:
            app_name = cached_notification._notification.app_name
            notification_id = getattr(cached_notification._notification, "id", None)

            # Skip ignored apps during rebuild
            if app_name in data.NOTIFICATION_IGNORED_APPS_HISTORY:
                continue

            # Preload assets for each cached notification to ensure display consistency
            preload_notification_assets(cached_notification._notification)

            self.notification_groups[app_name].append(cached_notification)
            rebuild_count += 1

        logger.info(
            f"Rebuilt {rebuild_count} notifications into {
                len(self.notification_groups)
            } groups"
        )

        # Create group widgets and handle limited apps
        for app_name, notifications in self.notification_groups.items():
            # Sort notifications by ID (highest ID first - newest notifications)
            # This ensures the latest notifications appear at the top of each group
            notifications.sort(
                key=lambda n: getattr(n._notification, "id", 0), reverse=True
            )

            # Handle limited apps history - only keep 5 notifications during rebuild
            if app_name in data.NOTIFICATION_LIMITED_APPS_HISTORY:
                if len(notifications) > 5:
                    # Keep only the 5 most recent notifications
                    self.notification_groups[app_name] = notifications[:5]

            group_widget = ExpandableNotificationGroup(
                app_name, self.notification_groups[app_name]
            )
            self.group_widgets[app_name] = group_widget
            self.notifications_box.add(group_widget)

    def on_notification_added(self, service, cached_notification):
        try:
            app_name = cached_notification._notification.app_name

            # Check if this app should be ignored for history (don't add to notification center)
            if app_name in data.NOTIFICATION_IGNORED_APPS_HISTORY:
                return

            # Preload assets for notification center display (ensure caching consistency)
            preload_notification_assets(cached_notification._notification)

            # Add to groups in sorted order (highest ID first - maintains newest-first ordering)
            notifications_list = self.notification_groups[app_name]
            new_notification_id = getattr(cached_notification._notification, "id", 0)

            # Find the correct position to insert based on ID (highest first)
            insert_position = 0
            for i, existing_notification in enumerate(notifications_list):
                existing_id = getattr(existing_notification._notification, "id", 0)
                if new_notification_id > existing_id:
                    insert_position = i
                    break
                insert_position = i + 1

            notifications_list.insert(insert_position, cached_notification)

            # Handle limited apps history - only keep 5 notifications
            if app_name in data.NOTIFICATION_LIMITED_APPS_HISTORY:
                notifications_for_app = self.notification_groups[app_name]
                if len(notifications_for_app) > 5:
                    # Remove oldest notifications beyond the limit
                    excess_notifications = notifications_for_app[5:]
                    self.notification_groups[app_name] = notifications_for_app[:5]

                    # Remove excess notifications from the service cache
                    for excess_notification in excess_notifications:
                        try:
                            notification_service.remove_cached_notification(
                                excess_notification.cache_id
                            )
                        except Exception as e:
                            logger.error(f"Error removing excess notification: {e}")

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
        # No notifications label removed - only update clear button and scrolled visibility
        self.clear_all_button.set_visible(current_count > 0)
        self.scrolled.set_visible(current_count > 0)

        # Auto-close notification center when no notifications remain
        if current_count == 0 and hasattr(self, "mousecapture"):
            self.mousecapture.hide_child_window()

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
        """Control notification center visibility with slide-left animation"""
        if visible:
            self.main_revealer.set_reveal_child(True)
        else:
            self.main_revealer.set_reveal_child(False)
        logger.debug(f"Notification center visibility set to: {visible}")

    def _on_destroy(self, *_):
        # Signals will be automatically disconnected when the object is destroyed
        pass
