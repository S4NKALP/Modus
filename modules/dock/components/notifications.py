from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

import config.data as data
import utils.icons as icons
from services import notification_service
from modules.notification_popup import NotificationWidget
from utils.wayland import WaylandWindow as Window


class NotificationIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-notifications", **kwargs)

        self.notification_service = notification_service
        self.notification_count = 0

        # Create the notification icon (switches between normal and dots)
        self.notification_icon = Label(
            name="notification-icon",
            markup=icons.notifications
        )

        # Add the icon directly (no overlay needed)
        self.add(self.notification_icon)

        # Connect to notification service signals
        self.notification_service.connect("notification_count", self.on_notification_count_changed)
        self.notification_service.connect("notification-added", self.on_notification_added)
        self.notification_service.connect("dnd", self.on_dnd_changed)

        # Connect click handler
        self.connect("clicked", self.on_clicked)

        # Initialize count
        self.update_count()

        # Popup window for showing notifications
        self.popup_window = None

    def on_notification_count_changed(self, _service, count):
        """Handle notification count changes."""
        print(f"[NotificationIndicator] Count changed to {count}")
        self.notification_count = count
        self.update_count()

        # If popup is open, refresh it to show new notifications
        if self.popup_window and self.popup_window.get_visible():
            print(f"[NotificationIndicator] Popup is open, refreshing...")
            self.popup_window.refresh_popup()

    def on_notification_added(self, _service, _notification_id):
        """Handle new notifications being added."""
        print(f"[NotificationIndicator] New notification added: {_notification_id}")
        # Update count immediately when new notification arrives
        self.notification_count = self.notification_service.count
        self.update_count()

        # If popup is open, refresh it to show new notifications
        if self.popup_window and self.popup_window.get_visible():
            print(f"[NotificationIndicator] Popup is open, refreshing...")
            self.popup_window.refresh_popup()

    def on_dnd_changed(self, _service, dnd_enabled):
        """Handle DND status changes."""
        print(f"[NotificationIndicator] DND changed: {dnd_enabled}")
        self.update_count()  # This will update the icon based on DND status

        # If popup is open, refresh it to reflect DND state
        if self.popup_window and self.popup_window.get_visible():
            print(f"[NotificationIndicator] DND changed, refreshing popup...")
            self.popup_window.refresh_popup()

    def update_count(self):
        """Update the notification icon display."""
        count = self.notification_service.count
        self.notification_count = count
        dnd_enabled = self.notification_service.dont_disturb

        if dnd_enabled:
            # Show DND icon when DND is enabled
            self.notification_icon.set_markup(icons.notifications_off)
            self.set_tooltip_text(f"Do Not Disturb enabled ({count} notification{'s' if count != 1 else ''})")
        elif count >= 1:
            # Show notifications_dots icon when there are notifications
            self.notification_icon.set_markup(icons.notifications_dots)
            self.set_tooltip_text(f"{count} notification{'s' if count != 1 else ''}")
        else:
            # Show regular notifications icon when no notifications
            self.notification_icon.set_markup(icons.notifications)
            self.set_tooltip_text("No notifications")

    def on_clicked(self, _button):
        """Handle click to show/hide notification popup."""
        if self.popup_window and self.popup_window.get_visible():
            self.popup_window.set_visible(False)
        else:
            self.show_notifications_popup()

    def show_notifications_popup(self):
        """Show popup window with cached notifications."""
        if self.popup_window:
            self.popup_window.destroy()

        # Get cached notifications (always get fresh data)
        notifications = self.notification_service.get_deserialized()
        print(f"[NotificationIndicator] Opening popup with {len(notifications)} notifications")

        # Create popup window (handles both empty and filled states)
        self.popup_window = NotificationPopupWindow(notifications, self.notification_service)
        self.popup_window.show_all()


class NotificationPopupWindow(Window):
    def __init__(self, notifications, notification_service):
        self.notification_service = notification_service

        # Create scrolled container for notifications
        self.notifications_box = Box(
            name="notifications-popup-box",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=False
        )

        if not notifications:
            # Show "No notifications" message
            no_notif_icon = Label(
                name="no-notifications-icon",
                markup=icons.notifications,
                h_align="center"
            )

            no_notif_message = Label(
                name="no-notifications-message",
                label="No notifications",
                h_align="center",
                v_align="center"
            )

            no_notif_content = Box(
                name="no-notifications-content",
                orientation="v",
                spacing=16,
                h_align="center",
                v_align="center",
                h_expand=True,
                v_expand=True,
                children=[no_notif_icon, no_notif_message]
            )

            self.notifications_box.add(no_notif_content)
        else:
            # Add notifications to the box (limit to recent 10)
            recent_notifications = notifications[-10:] if len(notifications) > 10 else notifications
            recent_notifications.reverse()  # Show newest first

            for notification in recent_notifications:
                # Create notification widget with dock callback passed during initialization
                notif_widget = NotificationWidget(
                    notification,
                    show_progress=False,
                    dock_callback=self.remove_notification_from_cache
                )

                self.notifications_box.add(notif_widget)

        # Create scrolled window with proper sizing
        scrolled = ScrolledWindow(
            name="notifications-scrolled",
            child=self.notifications_box,
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            min_content_size=(400, 450),
            max_content_size=(450, 500),
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False
        )

        # Create header with DND toggle and clear all button
        header_children = [
            Label(
                name="notifications-title",
                label="Notifications",
                h_align="start",
                h_expand=True
            )
        ]

        # Add DND toggle button with icon
        dnd_icon = icons.notifications_off if self.notification_service.dont_disturb else icons.notifications
        dnd_tooltip = "Do Not Disturb: ON" if self.notification_service.dont_disturb else "Do Not Disturb: OFF"
        self.dnd_button = Button(
            name="dnd-toggle-button",
            child=Label(
                name="dnd-toggle-icon",
                markup=dnd_icon
            ),
            on_clicked=self.toggle_dnd
        )
        self.dnd_button.set_tooltip_text(dnd_tooltip)
        header_children.append(self.dnd_button)

        if notifications:  # Only add clear button if there are notifications
            header_children.append(
                Button(
                    name="clear-all-button",
                    label="Clear All",
                    on_clicked=self.clear_all_notifications
                )
            )

        header_box = Box(
            name="notifications-header",
            orientation="h",
            spacing=8,
            children=header_children
        )

        main_box = Box(
            name="notifications-popup-main",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=True,
            children=[header_box, scrolled]
        )

        # Determine popup position based on dock position
        dock_position = data.DOCK_POSITION
        popup_anchor = self._get_popup_anchor(dock_position)

        print(f"[NotificationPopup] Dock position: {dock_position}, Popup anchor: {popup_anchor}")

        # Get margin based on dock position
        margin = self._get_popup_margin(dock_position)

        super().__init__(
            name="notifications-popup-window",
            anchor=popup_anchor,
            margin=margin,
            child=main_box,
            layer="top",
            exclusive=False,
            keyboard_mode="on-demand",
            visible=True,
            all_visible=True
        )

        # Auto-hide when clicking outside or pressing escape
        self.connect("button-press-event", self.on_button_press)
        self.connect("key-press-event", self.on_key_press)

        # Make sure the window can receive key events
        self.set_can_focus(True)
        self.grab_focus()

        # Set tooltip with keyboard shortcuts
        self.set_tooltip_text("Keyboard shortcuts:\n• Escape: Close popup\n• Ctrl+D: Toggle DND\n• Ctrl+A: Clear all notifications")

    def _get_popup_anchor(self, dock_position):
        """Determine popup anchor position based on dock position."""
        # Position popup on the opposite side of the dock for better UX
        anchor_map = {
            "Top": "top",      # Dock at top -> popup at top right
            "Bottom": "bottom", # Dock at bottom -> popup at bottom right
            "Left": "left",      # Dock at left -> popup at top left
            "Right": "right"     # Dock at right -> popup at top right
        }
        return anchor_map.get(dock_position, "bottom")  # Default fallback

    def _get_popup_margin(self, dock_position):
        """Get appropriate margin based on dock position."""
        # Add margin to avoid overlapping with dock
        margin_map = {
            "Top": "60px 10px 10px 10px",     # Top dock -> margin from top
            "Bottom": "10px 10px 60px 10px",  # Bottom dock -> margin from bottom
            "Left": "10px 10px 10px 60px",    # Left dock -> margin from left
            "Right": "10px 60px 10px 10px"    # Right dock -> margin from right
        }
        return margin_map.get(dock_position, "10px 10px 10px 10px")  # Default fallback

    def update_dnd_button_icon(self):
        """Update the DND button icon and tooltip to reflect current DND state."""
        if hasattr(self, 'dnd_button'):
            dnd_enabled = self.notification_service.dont_disturb
            dnd_icon = icons.notifications_off if dnd_enabled else icons.notifications
            dnd_tooltip = "Do Not Disturb: ON" if dnd_enabled else "Do Not Disturb: OFF"

            # Update the button icon
            button_label = self.dnd_button.get_child()
            button_label.set_markup(dnd_icon)

            # Update tooltip
            self.dnd_button.set_tooltip_text(dnd_tooltip)

            print(f"[NotificationPopup] Updated DND button icon: {dnd_icon}")




    def remove_notification_from_cache(self, notification):
        """Remove a specific notification from cache and refresh popup."""
        print(f"[NotificationPopup] Removing notification from cache: {notification.summary}")

        # Find and remove the notification from the service cache
        # We need to find it by matching summary and app_name since IDs might differ
        all_notifications = self.notification_service.all_notifications
        for i, cached_notif in enumerate(all_notifications):
            if (cached_notif.get("summary") == notification.summary and
                cached_notif.get("app_name") == notification.app_name):
                print(f"[NotificationPopup] Found matching notification, removing...")
                self.notification_service.all_notifications.pop(i)
                self.notification_service._write_notifications(self.notification_service.all_notifications)
                self.notification_service.emit("notification_count", len(self.notification_service.all_notifications))
                break

        # Refresh the popup immediately
        self.refresh_popup()

    def on_notification_closed(self, notification, reason):
        """Handle when a notification is closed - refresh the popup."""
        # Small delay to allow the notification service to update
        from gi.repository import GLib
        GLib.timeout_add(100, self.refresh_popup)

    def refresh_popup(self):
        """Refresh the popup content."""
        # Get updated notifications
        notifications = self.notification_service.get_deserialized()

        # Clear current content
        for child in self.notifications_box.get_children():
            self.notifications_box.remove(child)

        if not notifications:
            # Show "No notifications" message
            no_notif_icon = Label(
                name="no-notifications-icon",
                markup=icons.notifications,
                h_align="center"
            )

            no_notif_message = Label(
                name="no-notifications-message",
                label="No notifications",
                h_align="center",
                v_align="center"
            )

            no_notif_content = Box(
                name="no-notifications-content",
                orientation="v",
                spacing=16,
                h_align="center",
                v_align="center",
                h_expand=True,
                v_expand=True,
                children=[no_notif_icon, no_notif_message]
            )

            self.notifications_box.add(no_notif_content)
        else:
            # Add updated notifications
            recent_notifications = notifications[-10:] if len(notifications) > 10 else notifications
            recent_notifications.reverse()  # Show newest first

            for notification in recent_notifications:
                notif_widget = NotificationWidget(
                    notification,
                    show_progress=False,
                    dock_callback=self.remove_notification_from_cache
                )
                self.notifications_box.add(notif_widget)

        self.notifications_box.show_all()
        return False  # Don't repeat the timeout

    def toggle_dnd(self, button):
        """Toggle Do Not Disturb mode."""
        current_dnd = self.notification_service.dont_disturb
        new_dnd = not current_dnd
        self.notification_service.dont_disturb = new_dnd

        print(f"[NotificationPopup] DND toggled: {new_dnd}")

        # Update the DND button icon using the centralized method
        self.update_dnd_button_icon()

        # Emit DND signal
        self.notification_service.emit("dnd", new_dnd)

    def clear_all_notifications(self, _button):
        """Clear all cached notifications."""
        self.notification_service.clear_all_notifications()
        self.set_visible(False)

    def on_key_press(self, _widget, event):
        """Handle key press events."""
        from gi.repository import Gdk

        # Check if Escape key was pressed
        if event.keyval == Gdk.KEY_Escape:
            print(f"[NotificationPopup] Escape key pressed, closing popup")
            self.set_visible(False)
            return True  # Event handled

        # Check for Ctrl+D to toggle DND
        elif event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval == Gdk.KEY_d:
            print(f"[NotificationPopup] Ctrl+D pressed, toggling DND")
            # Toggle DND state directly
            current_dnd = self.notification_service.dont_disturb
            new_dnd = not current_dnd
            self.notification_service.dont_disturb = new_dnd

            print(f"[NotificationPopup] DND toggled via keyboard: {new_dnd}")

            # Update the DND button icon immediately
            self.update_dnd_button_icon()

            # Emit DND signal
            self.notification_service.emit("dnd", new_dnd)

            return True  # Event handled

        # Check for Ctrl+A to clear all notifications
        elif event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval == Gdk.KEY_a:
            print(f"[NotificationPopup] Ctrl+A pressed, clearing all notifications")
            if self.notification_service.count > 0:
                self.clear_all_notifications(None)  # Pass None as button parameter
            return True  # Event handled

        return False  # Let other handlers process the event

    def on_button_press(self, _widget, _event):
        """Hide popup when clicking outside."""
        # This is a simple implementation - in a real scenario you'd want
        # more sophisticated outside-click detection
        return False



class Notifications(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="notifications",
            orientation="h" if not data.VERTICAL else "v",
            spacing=4,
            children=[NotificationIndicator()],
            **kwargs
        )
        self.show_all()
