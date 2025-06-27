#!/usr/bin/env python3
"""
Test script for the dock notification history with sample data.
This script creates sample notifications and tests the history display.
"""

import sys
import json
import os
import uuid
from datetime import datetime, timedelta
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

# Add the project path
sys.path.append('.')
import config.data as data
from modules.dock.components.notifications import NotificationHistory, NotificationHistoryWindow

def create_sample_notifications():
    """Create sample notifications for testing."""
    
    # Create the persistent directory
    persistent_dir = f"/tmp/{data.APP_NAME}/notifications"
    persistent_file = os.path.join(persistent_dir, "notification_history.json")
    
    if not os.path.exists(persistent_dir):
        os.makedirs(persistent_dir, exist_ok=True)
    
    # Sample notifications
    sample_notifications = [
        {
            "id": str(uuid.uuid4()),
            "app_icon": "firefox",
            "summary": "Download Complete",
            "body": "Your file has been downloaded successfully",
            "app_name": "Firefox",
            "timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(),
            "cached_image_path": None
        },
        {
            "id": str(uuid.uuid4()),
            "app_icon": "mail-unread",
            "summary": "New Email",
            "body": "You have received a new message from John Doe",
            "app_name": "Thunderbird",
            "timestamp": (datetime.now() - timedelta(minutes=15)).isoformat(),
            "cached_image_path": None
        },
        {
            "id": str(uuid.uuid4()),
            "app_icon": "software-update-available",
            "summary": "System Update Available",
            "body": "5 packages can be updated",
            "app_name": "Software Updater",
            "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
            "cached_image_path": None
        },
        {
            "id": str(uuid.uuid4()),
            "app_icon": "spotify",
            "summary": "Now Playing",
            "body": "The Beatles - Hey Jude",
            "app_name": "Spotify",
            "timestamp": (datetime.now() - timedelta(hours=5)).isoformat(),
            "cached_image_path": None
        },
        {
            "id": str(uuid.uuid4()),
            "app_icon": "calendar",
            "summary": "Meeting Reminder",
            "body": "Team standup in 15 minutes",
            "app_name": "Calendar",
            "timestamp": (datetime.now() - timedelta(days=1)).isoformat(),
            "cached_image_path": None
        }
    ]
    
    # Write sample notifications to file
    with open(persistent_file, "w") as f:
        json.dump(sample_notifications, f, indent=2)
    
    print(f"Created {len(sample_notifications)} sample notifications in {persistent_file}")
    return len(sample_notifications)

def test_dock_notifications():
    """Test the dock notification history with sample data."""
    print("Testing Dock Notification History with sample data...")
    
    # Create sample notifications
    count = create_sample_notifications()
    
    # Create a test window to show the notification history
    window = Gtk.Window()
    window.set_title("Dock Notification History Test - With Sample Data")
    window.set_default_size(500, 600)
    window.connect("destroy", Gtk.main_quit)
    
    # Create the notification history widget
    notification_history = NotificationHistory()
    
    # Add the history to the window
    window.add(notification_history)
    
    # Show everything
    window.show_all()
    
    print(f"Notification history test started with {count} sample notifications!")
    print("Features to test:")
    print("- Sample notification display")
    print("- Date separators (Today, Yesterday, etc.)")
    print("- DND toggle switch")
    print("- Clear history button (trash icon)")
    print("- Individual notification close buttons")
    print("- Proper notification formatting with timestamps")
    print("- Scrollable interface")
    print(f"- Loaded notifications: {len(notification_history.persistent_notifications)}")
    print(f"- Display containers: {len(notification_history.containers)}")
    print("\nPress Ctrl+C to exit")
    
    try:
        Gtk.main()
    except KeyboardInterrupt:
        print("\nTest completed!")

if __name__ == "__main__":
    test_dock_notifications()
