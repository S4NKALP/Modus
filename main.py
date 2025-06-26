import os

import setproctitle
from fabric import Application
from fabric.utils import exec_shell_command_async, get_relative_path, monitor_file
from loguru import logger

from config.data import APP_NAME, APP_NAME_CAP, CONFIG_FILE
from modules.corners import Corners
from modules.dock.main import Dock
from modules.launcher import Launcher
from modules.notification_popup import NotificationPopup
from modules.osd import OSD
from modules.switcher import ApplicationSwitcher


for log in [
    "fabric.hyprland.widgets",
    "fabric.audio.service",
    "fabric.bluetooth.service",
    "services.network",
    "services.mpris",
]:
    logger.disable(log)

if __name__ == "__main__":
    setproctitle.setproctitle(APP_NAME)

    if not os.path.isfile(CONFIG_FILE):
        config_script_path = get_relative_path("config/config.py")
        exec_shell_command_async(f"python {config_script_path}")

    current_wallpaper = os.path.expanduser("~/.current.wall")
    if not os.path.exists(current_wallpaper):
        example_wallpaper = os.path.expanduser(
            f"~/.config/{APP_NAME_CAP}/assets/wallpapers_example/example-1.png"
        )
        os.symlink(example_wallpaper, current_wallpaper)

    # Load configuration
    from config.data import load_config

    config = load_config()

    corners = Corners()
    dock = Dock()
    switcher = ApplicationSwitcher()
    osd = OSD()
    launcher = Launcher()
    nc = NotificationPopup()

    # Set corners visibility based on config
    corners_visible = config.get("corners_visible", True)
    corners.set_visible(corners_visible)

    # Monitor CSS files for changes
    css_file = monitor_file(get_relative_path("styles"))
    _ = css_file.connect("changed", lambda *_: set_css())

    color_css_file = monitor_file(get_relative_path("./styles/colors.css"))
    _ = color_css_file.connect("changed", lambda *_: set_css())

    app = Application(
        f"{APP_NAME}", dock, corners, switcher, osd, launcher, nc
    )  # Make sure corners is added to the app

    def set_css():
        app.set_stylesheet_from_file(
            get_relative_path("main.css"),
        )

    app.set_css = set_css

    app.set_css()

    app.run()
