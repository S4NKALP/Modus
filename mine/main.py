import faulthandler

from fabric import Application
from fabric.utils import get_relative_path, logger, monitor_file, os

import config.data as data
from modules.launcher.main import LauncherWindow
from modules.notifications import NotificationWindow
from modules.osd.main import OSDWindow
from modules.panel.main import Panel
from services import KeyboardLayout, start_config_service
from services.wallpaper import generate_colors_from_wallpaper
from utils.corners import corners
from utils.functions import set_process_name

if __name__ == "__main__":
    # Enable faulthandler to capture segfault information
    faulthandler.enable()

    set_process_name(data.APP_NAME)

    data.generate_default_config()

    # Generate colors.css if it doesn't exist
    colors_css_path = get_relative_path("styles/colors.css")
    if not os.path.exists(colors_css_path):
        default_wallpaper = get_relative_path("assets/example_wallpaper.png")
        if os.path.exists(default_wallpaper):
            generate_colors_from_wallpaper(default_wallpaper)

    debug_enabled = data.DATA().get("debug")
    if not debug_enabled:
        for log in ["fabric", "services", "utils", "modules", "config"]:
            logger.disable(log)

    config_service = start_config_service()

    panel = Panel()
    launcher = LauncherWindow()
    osd = OSDWindow()
    notif = NotificationWindow()

    css_file = monitor_file(get_relative_path("styles"))
    _ = css_file.connect("changed", lambda *_: set_css())

    app = Application(f"{data.APP_NAME}", panel, *corners, osd, launcher, notif)

    @Application.action()
    def set_css():
        app.set_stylesheet_from_file(
            get_relative_path("styles/main.css"),
        )

    @Application.action()
    def switch_keyboard_layout():
        keyboard_layout = KeyboardLayout.get_initial()
        keyboard_layout.switch_to_next()

    @Application.action()
    def osd_show_audio():
        osd.get_child().show_audio_osd()

    @Application.action()
    def osd_show_brightness():
        osd.get_child().show_brightness_osd()

    app.set_css = set_css
    app.set_css()

    app.run()
