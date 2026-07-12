import os

import setproctitle
from fabric import Application
from fabric.utils import get_relative_path, monitor_file, exec_shell_command_async
from loguru import logger

from modules.bar.bar import Bar, Corners
from modules.launcher.launcher import Launcher

from modules.dock import Dock
from modules.notification_popup import NotificationPopup
from modules.osd import OSD
from config.data import APP_NAME, CACHE_DIR, CONFIG_FILE, DOCK_ICON_SIZE, VERTICAL, APP_NAME_CAP


for log in [
    "fabric.hyprland.widgets",
    "fabric.audio.service",
    "fabric.bluetooth.service",
]:
    logger.disable(log)



if __name__ == "__main__":
    setproctitle.setproctitle(APP_NAME)

    if not os.path.isfile(CONFIG_FILE):
        exec_shell_command_async(f"python {get_relative_path('../config/config.py')}")
    bar = Bar()
    dock = Dock()
    corners = Corners()
    osd = OSD()
    notif = NotificationPopup()
    launcher = Launcher()
    bar.launcher = launcher
    launcher.bar = bar

    app = Application(f"{APP_NAME}", bar, launcher, osd, dock)

    # Monitor CSS files for changes
    css_file = monitor_file(get_relative_path("styles"))
    _ = css_file.connect("changed", lambda *_: set_css())

    color_css_file = monitor_file(get_relative_path("./styles/colors.css"))
    _ = color_css_file.connect("changed", lambda *_: set_css())

    def set_css():
        logger.info("[Main] Applying CSS")
        app.set_stylesheet_from_file(get_relative_path("styles/main.css"),
                                     exposed_functions={
               "dock_nmargin": lambda: f"margin-bottom: -{32 + DOCK_ICON_SIZE}px;" if not VERTICAL else f"margin-right: -{32 + DOCK_ICON_SIZE}px;",
                "dock_sep": lambda: f"margin: 8px 0;" if not VERTICAL else f"margin: 0 8px;",
            },)

    app.set_css = set_css

    app.set_css()

    app.run()
