"""
Dashboard notification components for Modus.
Provides notification display functionality for the dashboard.
"""

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GLib, Gtk
import os
import json
from datetime import datetime

from utils.notification_utils import (
    get_shared_notification_history,
    PERSISTENT_HISTORY_FILE,
    create_historical_notification_from_data,
    compute_time_label,
)

import utils.icons as icons


class DashboardNotificationItem(Box):
    """Individual notification item for dashboard"""
    
    def __init__(self, notification_data, **kwargs):
        super().__init__(
            name="notification-container",
            orientation="v",
            h_align="fill",
            h_expand=True,
            **kwargs
        )
        
        self.notification_data = notification_data
        
        # Create historical notification from data
        hist_notif = create_historical_notification_from_data(notification_data)
        
        # Create timestamp
        try:
            arrival_time = datetime.fromisoformat(hist_notif.timestamp)
        except Exception:
            arrival_time = datetime.now()
        
        # Create time label
        self.time_label = Label(
            name="notification-timestamp",
            markup=compute_time_label(arrival_time),
            h_align="start",
            ellipsization="end",
        )
        
        # Create notification image box
        # For dashboard, we'll use a simple icon instead of trying to load cached images
        self.notif_image_box = Box(
            name="notification-image",
            orientation="v",
            children=[
                Label(name="notification-icon", markup=icons.notifications),
                Box(v_expand=True),
            ],
        )
        
        # Create summary label
        self.notif_summary_label = Label(
            name="notification-summary",
            markup=hist_notif.summary,
            h_align="start",
            ellipsization="end",
        )
        
        # Create app name label
        self.notif_app_name_label = Label(
            name="notification-app-name",
            markup=f"{hist_notif.app_name}",
            h_align="start",
            ellipsization="end",
        )
        
        # Create body label
        self.notif_body_label = (
            Label(
                name="notification-body",
                markup=hist_notif.body,
                h_align="start",
                ellipsization="end",
                line_wrap="word-char",
            )
            if hist_notif.body
            else Box()
        )
        if hist_notif.body:
            self.notif_body_label.set_single_line_mode(True)
        
        # Create summary box with separators
        self.notif_summary_box = Box(
            name="notification-summary-box",
            orientation="h",
            children=[
                self.notif_summary_label,
                Box(
                    name="notif-sep",
                    h_expand=False,
                    v_expand=False,
                    h_align="center",
                    v_align="center",
                ),
                self.notif_app_name_label,
                Box(
                    name="notif-sep",
                    h_expand=False,
                    v_expand=False,
                    h_align="center",
                    v_align="center",
                ),
                self.time_label,
            ],
        )
        
        # Create text box
        self.notif_text_box = Box(
            name="notification-text",
            orientation="v",
            v_align="center",
            h_expand=True,
            children=[
                self.notif_summary_box,
                self.notif_body_label,
            ],
        )
        
        # Create close button
        self.notif_close_button = Button(
            name="notif-close-button",
            child=Label(name="notif-close-label", markup=icons.cancel),
            on_clicked=lambda *_: self.remove_notification(),
        )
        
        self.notif_close_button_box = Box(
            orientation="v",
            children=[
                self.notif_close_button,
                Box(v_expand=True),
            ],
        )
        
        # Create main content box
        content_box = Box(
            name="notification-box-hist",
            spacing=8,
            children=[
                self.notif_image_box,
                self.notif_text_box,
                self.notif_close_button_box,
            ],
        )
        
        self.add(content_box)
        
    def remove_notification(self):
        """Remove this notification from the dashboard"""
        if self.get_parent():
            self.get_parent().remove(self)
            self.destroy()


class DashboardNotifications(Box):
    """Dashboard notifications container that shows real notifications"""
    
    def __init__(self, **kwargs):
        super().__init__(
            name="notification-history",
            orientation="v",
            **kwargs
        )
        
        self.notification_items = []
        self.max_notifications = 5  # Limit to 5 notifications in dashboard
        
        # Create header components (matching dock notifications)
        self.header_label = Label(
            name="nhh",
            label="Notifications",
            h_align="start",
            h_expand=True,
        )
        self.header_switch = Gtk.Switch(name="dnd-switch")
        self.header_switch.set_vexpand(False)
        self.header_switch.set_valign(Gtk.Align.CENTER)
        self.header_switch.set_active(False)
        self.header_clean = Button(
            name="nhh-button",
            child=Label(name="nhh-button-label", markup=icons.trash),
            on_clicked=self.clear_history,
        )
        self.do_not_disturb_enabled = False
        self.header_switch.connect("notify::active", self.on_do_not_disturb_changed)
        self.dnd_label = Label(name="dnd-label", markup=icons.notifications_off)

        self.history_header = CenterBox(
            name="notification-history-header",
            spacing=8,
            start_children=[self.header_switch, self.dnd_label],
            center_children=[self.header_label],
            end_children=[self.header_clean],
        )
        
        # Create notifications list
        self.notifications_list = Box(
            name="notifications-list",
            orientation="v",
            spacing=4,
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
        )
        
        # Create "no notifications" label
        self.no_notifications_label = Label(
            name="no-notif",
            markup=icons.notifications_clear,
            v_align="fill",
            h_align="fill",
            v_expand=True,
            h_expand=True,
            justification="center",
        )
        self.no_notifications_box = Box(
            name="no-notifications-box",
            v_align="fill",
            h_align="fill",
            v_expand=True,
            h_expand=True,
            children=[self.no_notifications_label],
        )
        
        # Create scrolled window for notifications list only
        self.notifications_scrolled = ScrolledWindow(
            name="notification-history-scrolled-window",
            child=self.notifications_list,
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            min_content_size=(400, 200),
            max_content_size=(450, 300),
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            propagate_width=False,
            propagate_height=False,
        )

        # Add components to main container - header outside, scrolled list inside
        self.add(self.history_header)
        self.add(self.notifications_scrolled)

        # Add the no notifications box initially to the notifications list
        self.notifications_list.add(self.no_notifications_box)
        
        # Connect to shared notification history
        self._connect_to_notifications()
        
        # Load and sync DND state
        self._load_and_sync_dnd_state()
        
        # Load initial notifications
        self._load_recent_notifications()
        
    def _connect_to_notifications(self):
        """Connect to the shared notification history for real-time updates"""
        try:
            self.shared_history = get_shared_notification_history()
            self.shared_history.connect("notification-added", self._on_notification_added)
            self.shared_history.connect("dnd-state-changed", self._on_dnd_state_changed)
        except Exception as e:
            print(f"Could not connect to notification history: {e}")
            
    def _on_notification_added(self, shared_history):
        """Handle new notification added"""
        GLib.idle_add(self._refresh_notifications)
        
    def _on_dnd_state_changed(self, notification_history, dnd_enabled):
        """Handle DND state change"""
        self.do_not_disturb_enabled = dnd_enabled
        self.header_switch.set_active(dnd_enabled)
        
    def _load_and_sync_dnd_state(self):
        """Load and sync DND state from shared history"""
        try:
            if hasattr(self, 'shared_history'):
                dnd_enabled = self.shared_history.do_not_disturb_enabled
                self.header_switch.set_active(dnd_enabled)
                self.do_not_disturb_enabled = dnd_enabled
        except Exception as e:
            print(f"Could not sync DND state: {e}")
            
    def on_do_not_disturb_changed(self, switch, pspec):
        """Handle DND switch toggle"""
        self.do_not_disturb_enabled = switch.get_active()
        
        try:
            if hasattr(self, 'shared_history'):
                self.shared_history.set_do_not_disturb_enabled(self.do_not_disturb_enabled)
        except Exception as e:
            print(f"Could not update shared DND state: {e}")

    def clear_history(self, *args):
        """Clear all notifications"""
        # Clear notification items
        for item in self.notification_items[:]:
            self.notifications_list.remove(item)
            item.destroy()
        self.notification_items.clear()

        # Clear persistent history
        try:
            if hasattr(self, 'shared_history'):
                self.shared_history.clear_history()
        except Exception as e:
            print(f"Could not clear shared history: {e}")

        # Update visibility
        self._update_no_notifications_visibility()

    def _load_recent_notifications(self):
        """Load recent notifications from persistent storage"""
        try:
            if os.path.exists(PERSISTENT_HISTORY_FILE):
                with open(PERSISTENT_HISTORY_FILE, "r") as f:
                    notifications = json.load(f)

                # Get the most recent notifications (up to max_notifications)
                recent_notifications = notifications[-self.max_notifications:]

                for notif_data in reversed(recent_notifications):
                    self._add_notification_item(notif_data)

        except Exception as e:
            print(f"Error loading recent notifications: {e}")

    def _refresh_notifications(self):
        """Refresh the notification list"""
        # Clear existing notifications
        for item in self.notification_items[:]:
            self.notifications_list.remove(item)
            item.destroy()
        self.notification_items.clear()

        # Reload recent notifications
        self._load_recent_notifications()

        # Update visibility
        self._update_no_notifications_visibility()

    def _add_notification_item(self, notification_data):
        """Add a notification item to the dashboard"""
        # Remove no notifications box if it's showing
        if self.no_notifications_box in self.notifications_list.get_children():
            self.notifications_list.remove(self.no_notifications_box)

        if len(self.notification_items) >= self.max_notifications:
            # Remove oldest notification
            oldest = self.notification_items.pop(0)
            self.notifications_list.remove(oldest)
            oldest.destroy()

        # Create new notification item
        item = DashboardNotificationItem(notification_data)
        self.notification_items.append(item)
        self.notifications_list.add(item)

        # Update visibility
        self._update_no_notifications_visibility()

        # Show all to ensure visibility
        self.show_all()

    def _update_no_notifications_visibility(self):
        """Update visibility of no notifications label"""
        has_notifications = bool(self.notification_items)

        if has_notifications:
            # Hide no notifications box
            if self.no_notifications_box in self.notifications_list.get_children():
                self.notifications_list.remove(self.no_notifications_box)
        else:
            # Show no notifications box
            if self.no_notifications_box not in self.notifications_list.get_children():
                self.notifications_list.add(self.no_notifications_box)
