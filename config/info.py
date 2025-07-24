from gi.repository import Gtk
import os
import gi

gi.require_version("Gtk", "3.0")

ALLOWED_PLAYERS = ["vlc", "cmus", "firefox", "spotify", "chromium"]
USERNAME = os.getlogin()
HOSTNAME = os.uname().nodename
HOME_DIR = os.path.expanduser("~")
WALLPAPERS_DIR = os.path.expanduser("~/Pictures/wallpapers/")
VERTICAL = False
BRIGHTNESS_DEV = "intel_backlight"
print(USERNAME, HOSTNAME, HOME_DIR)
print(Gtk)
