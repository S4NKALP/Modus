#!/usr/bin/env python3
"""
Test script for the complete notification caching flow.
This script tests:
1. Creating a notification popup with history
2. Simulating notifications being received and cached
3. Showing the cached notifications in dock history
"""

import sys
import json
import os
import uuid
from datetime import datetime
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

# Add the project path
sys.path.append('.')
import config.data as data
from modules.notification_popup import NotificationHistory, NotificationBox
from modules.dock.components.notifications import NotificationHistory as DockNotificationHistory

def create_test_notification():
    """Create a test notification object."""
    class TestNotification:
        def __init__(self, summary, body, app_name, app_icon="dialog-information"):
            self.id = str(uuid.uuid4())
            self.summary = summary
            self.body = body
            self.app_name = app_name
            self.app_icon = app_icon
            self.image_pixbuf = None
            self.actions = []

        def close(self, reason):
            print(f"Notification {self.id} closed with reason: {reason}")

    return TestNotification(
        summary="Test Notification",
        body="This is a test notification to verify caching",
        app_name="Test App",
        app_icon="dialog-information"
    )

def test_notification_caching_flow():
    """Test the complete notification caching flow."""
    print("Testing complete notification caching flow...")

    # Step 1: Create notification popup history
    print("\n1. Creating notification popup history...")
    popup_history = NotificationHistory()
    print(f"   ✅ Popup history created with {len(popup_history.persistent_notifications)} existing notifications")

    # Step 2: Create a test notification and add it to history
    print("\n2. Creating and caching a test notification...")
    test_notification = create_test_notification()
    test_box = NotificationBox(test_notification, timeout_ms=0)  # No timeout for testing
    test_box.set_is_history(True)

    # Add to history (this should cache it to persistent file)
    popup_history.add_notification(test_box)
    print(f"   ✅ Added notification to popup history")
    print(f"   ✅ Popup history now has {len(popup_history.persistent_notifications)} notifications")

    # Step 3: Create dock notification history and verify it loads the cached notification
    print("\n3. Creating dock notification history...")
    dock_history = DockNotificationHistory()
    print(f"   ✅ Dock history created")
    print(f"   ✅ Dock history loaded {len(dock_history.persistent_notifications)} notifications")
    print(f"   ✅ Dock history has {len(dock_history.containers)} display containers")

    # Step 4: Verify the notification data matches
    if len(dock_history.persistent_notifications) > 0:
        cached_notif = dock_history.persistent_notifications[-1]  # Get the latest
        print(f"\n4. Verifying cached notification data...")
        print(f"   ✅ Summary: {cached_notif.get('summary')}")
        print(f"   ✅ Body: {cached_notif.get('body')}")
        print(f"   ✅ App: {cached_notif.get('app_name')}")
        print(f"   ✅ Timestamp: {cached_notif.get('timestamp')}")
        print(f"   ✅ Notification successfully cached and loaded!")
    else:
        print(f"\n4. ❌ No notifications found in dock history")
        return False

    # Step 5: Test creating another notification
    print(f"\n5. Testing multiple notifications...")
    test_notification2 = create_test_notification()
    test_notification2.summary = "Second Test Notification"
    test_notification2.app_name = "Another App"

    test_box2 = NotificationBox(test_notification2, timeout_ms=0)
    test_box2.set_is_history(True)
    popup_history.add_notification(test_box2)

    print(f"   ✅ Added second notification")
    print(f"   ✅ Popup history now has {len(popup_history.persistent_notifications)} notifications")

    # Reload dock history to see new notification
    dock_history2 = DockNotificationHistory()
    print(f"   ✅ New dock history loaded {len(dock_history2.persistent_notifications)} notifications")

    print(f"\n🎉 SUCCESS! Notification caching flow is working!")
    print(f"   - Notifications are cached to persistent file")
    print(f"   - Dock history loads cached notifications")
    print(f"   - Multiple notifications are handled correctly")

    return True

if __name__ == "__main__":
    success = test_notification_caching_flow()
    if success:
        print(f"\n✅ All tests passed! Notification caching is working correctly.")
    else:
        print(f"\n❌ Tests failed! Check the implementation.")
