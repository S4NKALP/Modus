#!/usr/bin/env python3
"""
Test script to verify mouse navigation works in the launcher.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.launcher.main import Launcher
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

def test_mouse_navigation():
    """Test mouse navigation functionality."""
    print("Testing mouse navigation in launcher...")
    
    # Create launcher instance
    launcher = Launcher()
    
    # Show launcher with a trigger to get some results
    launcher.show_launcher("app")
    
    print("Launcher opened with 'app' trigger")
    print("You should be able to:")
    print("1. Hover over result items to see selection change (without scrolling)")
    print("2. Click on result items to activate them")
    print("3. Use keyboard navigation (arrow keys) which should scroll")
    print("Press Ctrl+C to exit test")
    
    try:
        Gtk.main()
    except KeyboardInterrupt:
        print("\nTest completed!")
        launcher.close_launcher()

if __name__ == "__main__":
    test_mouse_navigation()
