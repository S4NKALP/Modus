#!/usr/bin/env python3
"""
Test script to send sample notifications for testing the dashboard notification display.
"""

import subprocess
import time
import sys

def send_test_notification(app_name, title, body, icon=None):
    """Send a test notification using notify-send"""
    cmd = ["notify-send", "-a", app_name, title, body]
    if icon:
        cmd.extend(["-i", icon])
    
    try:
        subprocess.run(cmd, check=True)
        print(f"Sent notification: {app_name} - {title}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to send notification: {e}")

def main():
    """Send a series of test notifications"""
    print("Sending test notifications for dashboard...")
    
    # Test notifications with different apps and content
    test_notifications = [
        ("Modus", "Dashboard Test", "This is a test notification for the dashboard"),
        ("System", "Low Battery", "Battery level is below 15%"),
        ("Firefox", "Download Complete", "Your file has been downloaded successfully"),
        ("Spotify", "Now Playing", "♪ Your favorite song is now playing"),
        ("Telegram", "New Message", "You have received a new message"),
    ]
    
    for i, (app, title, body) in enumerate(test_notifications):
        send_test_notification(app, title, body)
        if i < len(test_notifications) - 1:  # Don't sleep after the last notification
            time.sleep(2)  # Wait 2 seconds between notifications
    
    print("\nTest notifications sent!")
    print("Open the dashboard (SUPER+G) to see the notifications.")

if __name__ == "__main__":
    main()
