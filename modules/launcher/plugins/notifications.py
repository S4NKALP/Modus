import time
from datetime import datetime
from typing import List, Optional

import utils.icons as icons
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from gi.repository import GdkPixbuf
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
from services import notification_service


class NotificationDetailWidget(Box):
    """Widget for displaying detailed notification content."""

    def __init__(self, notification_data: dict, plugin_instance):
        super().__init__(name="notification-detail", orientation="v", spacing=8)

        self.notification_data = notification_data
        self.plugin = plugin_instance

        # Set size constraints to fit within launcher
        self.set_size_request(530, 200)
        self.set_vexpand(False)
        self.set_hexpand(True)

        self.setup_ui()

    def setup_ui(self):
        """Setup the detail view UI."""
        # Header with title and close button
        header_box = Box(orientation="h", spacing=8)

        # Title
        title_label = Label(
            label=f"📧 {self.notification_data.get('app_name', 'Unknown')}",
            name="notification-detail-title",
            h_align="start",
            h_expand=True,
        )
        header_box.add(title_label)

        # Close button
        close_btn = Button(
            child=Label(markup=icons.cancel, name="notification-close-icon"),
            name="notification-close-btn",
            on_clicked=lambda *_: self.plugin._close_detail_view(),
        )
        header_box.add(close_btn)

        self.add(header_box)

        # Content area
        content_box = Box(orientation="v", spacing=4)

        # Summary
        summary = self.notification_data.get("summary", "No title")
        summary_label = Label(
            label=f"Subject: {summary}",
            name="notification-detail-summary",
            h_align="start",
            ellipsize="end",
        )
        content_box.add(summary_label)

        # Body content
        body = self.notification_data.get("body", "")
        if body:
            body_label = Label(
                label=body,
                name="notification-detail-body",
                h_align="start",
                v_align="start",
                ellipsize="none",
            )
            # Set line wrapping using properties
            body_label.set_property("wrap", True)
            body_label.set_property("wrap-mode", 2)  # WORD wrap mode
            content_box.add(body_label)

        # Timestamp
        timestamp = self.notification_data.get("timestamp", time.time())
        time_str = self.plugin._format_timestamp(timestamp)
        time_label = Label(
            label=f"Time: {time_str}", name="notification-detail-time", h_align="start"
        )
        content_box.add(time_label)

        self.add(content_box)

        # Action buttons
        actions_box = Box(orientation="h", spacing=8)

        # Remove button
        remove_btn = Button(
            child=Label(
                markup=f"{icons.trash} Remove", name="notification-action-label"
            ),
            name="notification-action-btn",
            on_clicked=lambda *_: self._remove_notification(),
        )
        actions_box.add(remove_btn)

        self.add(actions_box)

    def _remove_notification(self):
        """Remove this notification."""
        notif_id = self.notification_data.get("notification_id", 0)
        self.plugin._clear_notification(notif_id)


class NotificationsPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "notifications"
        self.display_name = "Notification History"
        self.description = "Search and manage notification history"

        # Settings
        self.max_results = 15
        self.notification_service = notification_service
        self.showing_detail_for = None  # Track which notification is showing details

    def initialize(self):
        """Initialize the plugin."""
        self.set_triggers(["notif"])

        # Connect to notification service signals to refresh when notifications change
        self.notification_service.connect(
            "notification_count", self._on_notification_count_changed
        )

    def cleanup(self):
        """Cleanup the plugin."""
        # Disconnect from notification service signals
        try:
            self.notification_service.disconnect(
                "notification_count", self._on_notification_count_changed
            )
        except:
            pass

    def _format_timestamp(self, timestamp: float) -> str:
        """Format timestamp to human-readable string."""
        try:
            dt = datetime.fromtimestamp(timestamp)
            now = datetime.now()

            # If today, show time only
            if dt.date() == now.date():
                return dt.strftime("%H:%M")

            # If this week, show day and time
            days_diff = (now.date() - dt.date()).days
            if days_diff < 7:
                return dt.strftime("%a %H:%M")

            # Otherwise show date
            return dt.strftime("%m/%d %H:%M")
        except:
            return "Unknown"

    def _get_notification_icon(self, notification) -> Optional[GdkPixbuf.Pixbuf]:
        """Get icon for notification."""
        try:
            # Try to use notification's image first
            if hasattr(notification, "image_pixbuf") and notification.image_pixbuf:
                return notification.image_pixbuf.scale_simple(
                    32, 32, GdkPixbuf.InterpType.BILINEAR
                )

            # Try app icon
            if hasattr(notification, "app_icon") and notification.app_icon:
                if notification.app_icon.startswith("file://"):
                    icon_path = notification.app_icon[7:]
                    try:
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_path)
                        return pixbuf.scale_simple(
                            32, 32, GdkPixbuf.InterpType.BILINEAR
                        )
                    except:
                        pass

            return None
        except:
            return None

    def _truncate_text(self, text: str, max_length: int = 60) -> str:
        """Truncate text to specified length."""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def _trigger_refresh(self):
        """Trigger launcher refresh to return to default notification view."""
        try:
            from gi.repository import GLib

            def trigger_refresh():
                try:
                    # Try to access the launcher through the fabric Application
                    from fabric import Application

                    app = Application.get_default()

                    if app and hasattr(app, "launcher"):
                        launcher = app.launcher
                        if launcher and hasattr(launcher, "search_entry"):
                            # Get current search text to preserve the query
                            current_text = launcher.search_entry.get_text()
                            # Trigger the search to refresh results
                            if hasattr(launcher, "_perform_search"):
                                launcher._perform_search(current_text)
                            return False

                    # Fallback: try to find launcher instance through other means
                    import gc

                    for obj in gc.get_objects():
                        if (
                            hasattr(obj, "__class__")
                            and obj.__class__.__name__ == "Launcher"
                        ):
                            if hasattr(obj, "search_entry") and hasattr(
                                obj, "_perform_search"
                            ):
                                current_text = obj.search_entry.get_text()
                                obj._perform_search(current_text)
                                return False

                except Exception as e:
                    print(f"Error forcing launcher refresh: {e}")

                return False  # Don't repeat

            # Use immediate refresh
            GLib.timeout_add(10, trigger_refresh)

        except Exception as e:
            print(f"Could not trigger refresh: {e}")

    def _clear_notification(self, notification_id: int):
        """Remove a specific notification from history."""
        try:
            # Debug: Print notification removal
            print(f"[NotificationPlugin] Removing notification ID: {notification_id}")

            # Get count before removal for comparison
            count_before = len(self.notification_service.all_notifications)

            # Remove the notification
            self.notification_service.remove_notification(notification_id)

            # Get count after removal
            count_after = len(self.notification_service.all_notifications)

            # Debug: Print removal result
            print(
                f"[NotificationPlugin] Notifications before: {count_before}, after: {
                    count_after
                }"
            )

            if count_after < count_before:
                print(
                    f"[NotificationPlugin] Successfully removed notification {
                        notification_id
                    }"
                )
            else:
                print(
                    f"[NotificationPlugin] Warning: Notification {
                        notification_id
                    } may not have been removed"
                )

            # Trigger immediate refresh using the same pattern as OTP plugin
            self._trigger_refresh()

        except Exception as e:
            print(
                f"[NotificationPlugin] Error removing notification {notification_id}: {
                    e
                }"
            )
            # Still try to refresh even if there was an error
            self._trigger_refresh()

    def _clear_all_notifications(self):
        """Clear all notifications from history."""
        self.notification_service.clear_all_notifications()

    def _toggle_dnd(self, enable: bool = None):
        """Toggle or set DND mode."""
        try:
            if enable is None:
                # Toggle current state
                new_state = not self.notification_service.dont_disturb
            else:
                # Set specific state
                new_state = enable

            self.notification_service.dont_disturb = new_state
            status = "enabled" if new_state else "disabled"
            print(f"[NotificationPlugin] Do Not Disturb {status}")

            # Trigger refresh to show updated status
            self._trigger_refresh()

        except Exception as e:
            print(f"[NotificationPlugin] Error toggling DND: {e}")

    def _on_notification_count_changed(self, service, count: int):
        """Handle notification count changes (new notifications added or removed)."""
        try:
            print(
                f"[NotificationPlugin] Notification count changed to {
                    count
                }, triggering refresh"
            )
            self._trigger_refresh()
        except Exception as e:
            print(f"[NotificationPlugin] Error handling notification count change: {e}")

    def _get_notification_count(self) -> int:
        """Get total number of notifications."""
        try:
            return len(self.notification_service.all_notifications)
        except:
            return 0

    def _show_notification_details(self, notification_data: dict):
        """Show detailed view of a notification."""
        notif_id = notification_data.get("notification_id", 0)
        self.showing_detail_for = notif_id
        self._trigger_refresh()

    def _close_detail_view(self):
        """Close the detail view and return to list."""
        self.showing_detail_for = None
        self._trigger_refresh()

    def query(self, query_string: str) -> List[Result]:
        """Search notification history."""
        results = []

        # Check if we should show detail view for a specific notification
        if self.showing_detail_for is not None:
            try:
                notifications = self.notification_service.get_deserialized()
                for notif in notifications:
                    notif_data = (
                        notif.serialize() if hasattr(notif, "serialize") else {}
                    )
                    notif_id = notif_data.get("id", 0)

                    if notif_id == self.showing_detail_for:
                        # Create detail widget for this notification
                        detail_data = {
                            "notification_id": notif_id,
                            "app_name": getattr(notif, "app_name", "Unknown"),
                            "timestamp": getattr(notif, "timestamp", time.time()),
                            "summary": getattr(notif, "summary", "No title"),
                            "body": getattr(notif, "body", ""),
                        }

                        detail_widget = NotificationDetailWidget(detail_data, self)

                        results.append(
                            Result(
                                title="Notification Details",
                                subtitle="Press Escape to go back to list",
                                icon_markup=icons.notifications,
                                action=lambda: None,
                                relevance=1.0,
                                plugin_name=self.name,
                                custom_widget=detail_widget,
                                data={
                                    "type": "detail_view",
                                    "keep_launcher_open": True,
                                },
                            )
                        )
                        return results
            except Exception as e:
                print(f"Error showing notification details: {e}")
                self.showing_detail_for = None

        # Handle special commands
        if query_string.lower() in ["clear"]:
            results.append(
                Result(
                    title="Clear All Notifications",
                    subtitle="Remove all notifications from history",
                    description="This will permanently delete all notification history",
                    icon_markup=icons.trash,
                    relevance=1.0,
                    plugin_name=self.name,
                    action=self._clear_all_notifications,
                )
            )
            return results

        # Handle DND commands
        if query_string.lower() in ["off"]:
            current_dnd = self.notification_service.dont_disturb
            results.append(
                Result(
                    title="Enable Do Not Disturb",
                    subtitle="Turn off notification popups"
                    + (" (already enabled)" if current_dnd else ""),
                    description="Notifications will still be saved to history but won't show popups",
                    icon_markup=icons.notifications_off,
                    relevance=1.0,
                    plugin_name=self.name,
                    action=lambda: self._toggle_dnd(True),
                    data={"keep_launcher_open": True},
                )
            )
            return results

        if query_string.lower() in ["on"]:
            current_dnd = self.notification_service.dont_disturb
            results.append(
                Result(
                    title="Disable Do Not Disturb",
                    subtitle="Turn on notification popups"
                    + (" (already disabled)" if not current_dnd else ""),
                    description="Notifications will show popups normally",
                    icon_markup=icons.notifications,
                    relevance=1.0,
                    plugin_name=self.name,
                    action=lambda: self._toggle_dnd(False),
                    data={"keep_launcher_open": True},
                )
            )
            return results

        # Handle remove command
        if query_string.lower().startswith(
            "remove "
        ) or query_string.lower().startswith("delete "):
            search_term = (
                query_string[7:].strip()
                if query_string.lower().startswith("remove ")
                else query_string[7:].strip()
            )
            if search_term:
                results.append(
                    Result(
                        title=f"Remove notifications containing '{search_term}'",
                        subtitle="Search for notifications to remove",
                        description="This will show notifications matching your search term for removal",
                        icon_markup=icons.trash,
                        relevance=1.0,
                        plugin_name=self.name,
                        action=lambda: None,  # Will be handled by showing matching notifications
                    )
                )

        try:
            # Get notifications from service
            notifications = self.notification_service.get_deserialized()

            if not notifications:
                results.append(
                    Result(
                        title="No notifications found",
                        subtitle="Your notification history is empty",
                        icon_markup=icons.notifications,
                        relevance=0.5,
                        plugin_name=self.name,
                    )
                )
                return results

            # Show count if no query
            if not query_string:
                count = len(notifications)
                dnd_status = self.notification_service.dont_disturb

                # Add DND status result
                if dnd_status:
                    results.append(
                        Result(
                            title="Do Not Disturb: ON",
                            subtitle="Notification popups are disabled • Type 'on' to enable",
                            icon_markup=icons.notifications_off,
                            relevance=0.9,
                            plugin_name=self.name,
                            action=lambda: self._toggle_dnd(False),
                            data={"keep_launcher_open": True},
                        )
                    )
                else:
                    results.append(
                        Result(
                            title="Do Not Disturb: OFF",
                            subtitle="Notification popups are enabled • Type 'off' to disable",
                            icon_markup=icons.notifications,
                            relevance=0.9,
                            plugin_name=self.name,
                            action=lambda: self._toggle_dnd(True),
                            data={"keep_launcher_open": True},
                        )
                    )

                results.append(
                    Result(
                        title=f"Notification History ({count} notifications)",
                        subtitle="Type to search notifications or 'clear' to remove all",
                        icon_markup=icons.notifications,
                        relevance=0.8,
                        plugin_name=self.name,
                    )
                )

            # Filter notifications based on query
            query_lower = query_string.lower() if query_string else ""
            filtered_notifications = []

            for notif in notifications:
                # Get notification data
                notif_data = notif.serialize() if hasattr(notif, "serialize") else {}
                notif_id = notif_data.get("id", 0)
                timestamp = getattr(notif, "timestamp", time.time())

                # Search in summary, body, and app name
                searchable_text = " ".join(
                    [
                        getattr(notif, "summary", ""),
                        getattr(notif, "body", ""),
                        getattr(notif, "app_name", ""),
                    ]
                ).lower()

                if not query_lower or query_lower in searchable_text:
                    filtered_notifications.append((notif, notif_id, timestamp))

            # Sort by timestamp (newest first)
            filtered_notifications.sort(key=lambda x: x[2], reverse=True)

            # Limit results (leave room for header if no query)
            max_notif_results = self.max_results - (1 if not query_string else 0)
            filtered_notifications = filtered_notifications[:max_notif_results]

            # Create results
            for notif, notif_id, timestamp in filtered_notifications:
                summary = getattr(notif, "summary", "No title")
                body = getattr(notif, "body", "")
                app_name = getattr(notif, "app_name", "Unknown")

                # Create title and subtitle
                title = self._truncate_text(summary, 50)
                subtitle_parts = []

                if body:
                    subtitle_parts.append(self._truncate_text(body, 40))

                subtitle_parts.append(f"from {app_name}")
                subtitle_parts.append(self._format_timestamp(timestamp))
                subtitle = " • ".join(subtitle_parts)

                # Get icon
                icon = self._get_notification_icon(notif)

                result = Result(
                    title=title,
                    subtitle=subtitle,
                    description="",  # Don't show description by default
                    icon=icon,
                    icon_markup=icons.notifications if not icon else None,
                    relevance=1.0,
                    plugin_name=self.name,
                    action=lambda nd={
                        "notification_id": notif_id,
                        "app_name": app_name,
                        "timestamp": timestamp,
                        "summary": summary,
                        "body": body,
                    }: self._show_notification_details(nd),
                    data={
                        "notification_id": notif_id,
                        "app_name": app_name,
                        "timestamp": timestamp,
                        "can_remove": True,
                        "alt_action": lambda nid=notif_id: self._clear_notification(
                            nid
                        ),
                        "keep_launcher_open": True,
                    },
                )
                results.append(result)

        except Exception as e:
            results.append(
                Result(
                    title="Error loading notifications",
                    subtitle=str(e),
                    icon_markup=icons.alert,
                    relevance=0.0,
                    plugin_name=self.name,
                )
            )

        return results
