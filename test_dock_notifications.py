#!/usr/bin/env python3
"""
Test script for the dock notification history functionality.
This script demonstrates the notification history with persistent storage.
"""

import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk
from modules.dock.components.notifications import NotificationHistory, NotificationHistoryWindow

def test_dock_notifications():
    """Test the dock notification history functionality."""
    print("Testing Dock Notification History functionality...")
    
    # Create a test window to show the notification history
    window = Gtk.Window()
    window.set_title("Dock Notification History Test")
    window.set_default_size(500, 600)
    window.connect("destroy", Gtk.main_quit)
    
    # Create the notification history widget
    notification_history = NotificationHistory()
    
    # Add the history to the window
    window.add(notification_history)
    
    # Show everything
    window.show_all()
    
    print("Notification history test started!")
    print("Features to test:")
    print("- Persistent notification history loading")
    print("- Date separators (Today, Yesterday, etc.)")
    print("- DND toggle switch")
    print("- Clear history button (trash icon)")
    print("- Individual notification close buttons")
    print("- Proper notification formatting with timestamps")
    print("- Scrollable interface")
    print("- 'No notifications' state when empty")
    print("\nPress Ctrl+C to exit")
    
    try:
        Gtk.main()
    except KeyboardInterrupt:
        print("\nTest completed!")

if __name__ == "__main__":
    test_dock_notifications()
