#!/usr/bin/env python3
"""
Test script for the new NotificationContainer functionality.
This script demonstrates the notification popup with navigation between multiple notifications.
"""

import sys
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk
from modules.notification_popup import NotificationPopup

def test_notification_container():
    """Test the notification container with multiple notifications."""
    print("Testing NotificationContainer functionality...")

    # Create the notification popup
    popup = NotificationPopup()

    def create_mock_notification(app_name, summary, body, notif_id):
        """Create a mock notification for testing."""
        # Create a simple mock notification object
        class MockNotification:
            def __init__(self, app_name, summary, body, notif_id):
                self.app_name = app_name
                self.summary = summary
                self.body = body
                self.id = notif_id
                self.app_icon = "dialog-information-symbolic"
                self.image_pixbuf = None
                self.actions = []
                self.timeout = 5000
                self._callbacks = {}

            def connect(self, signal, callback):
                if signal not in self._callbacks:
                    self._callbacks[signal] = []
                self._callbacks[signal].append(callback)

            def close(self, reason):
                if "closed" in self._callbacks:
                    for callback in self._callbacks["closed"]:
                        callback(self, reason)

        return MockNotification(app_name, summary, body, notif_id)

    def send_test_notifications():
        """Send multiple test notifications to demonstrate the container."""
        notifications = [
            {
                "app_name": "Test App 1",
                "summary": "First Notification",
                "body": "This is the first test notification to demonstrate the container functionality."
            },
            {
                "app_name": "Test App 2",
                "summary": "Second Notification",
                "body": "This is the second notification. You should see navigation buttons appear."
            },
            {
                "app_name": "Test App 3",
                "summary": "Third Notification",
                "body": "Third notification with even more content to test the display."
            },
            {
                "app_name": "Music Player",
                "summary": "Now Playing",
                "body": "Song Title - Artist Name\\nAlbum: Album Name"
            },
            {
                "app_name": "Email Client",
                "summary": "New Email",
                "body": "You have received a new email from someone important."
            }
        ]

        # Send notifications with delays
        for i, notif_data in enumerate(notifications):
            def send_notification(data, index):
                print(f"Sending notification {index + 1}: {data['summary']}")

                # Create mock notification
                notification = create_mock_notification(
                    data["app_name"],
                    data["summary"],
                    data["body"],
                    f"test_id_{index}"
                )

                # Create mock fabric notification service
                class MockFabricNotif:
                    def get_notification_from_id(self, notif_id):
                        return notification

                # Simulate the notification service adding the notification
                popup.notification_container.on_new_notification(
                    MockFabricNotif(),
                    f"test_id_{index}"
                )

                return False  # Don't repeat

            # Schedule each notification with a delay
            GLib.timeout_add(i * 2000, lambda data=notif_data, idx=i: send_notification(data, idx))

        return False  # Don't repeat

    # Start sending notifications after a short delay
    GLib.timeout_add(1000, send_test_notifications)

    print("Notification container test started!")
    print("Features to test:")
    print("- Multiple notifications in a stack")
    print("- Navigation buttons (previous/next/close all)")
    print("- Automatic timeout management")
    print("- Hover to pause timeouts")
    print("- Close individual notifications")
    print("- Container auto-hide when all notifications are closed")
    print("\\nPress Ctrl+C to exit")

    try:
        Gtk.main()
    except KeyboardInterrupt:
        print("\\nTest completed!")

if __name__ == "__main__":
    test_notification_container()
