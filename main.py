import os

import setproctitle
from fabric import Application
from fabric.utils import get_relative_path, monitor_file
from loguru import logger

from modules.bar.bar import Bar, ScreenCorners
from modules.launcher.launcher import Launcher
from modules.dock import Dock
from modules.notification_popup import NotificationPopup

from modules.osd import OSD

from services import sc
from config.config import open_config

for log in [
    "fabric.hyprland.widgets",
    "fabric.audio.service",
    "fabric.bluetooth.service",
]:
    logger.disable(log)

config_path = os.path.expanduser("~/Modus/config/assets/config.json")


def update_main_css():
    colors_css_path = f"/home/{os.getlogin()}/.cache/material/colors.css"
    main_css_path = get_relative_path("styles/main.css")

    if os.path.exists(colors_css_path):
        with open(main_css_path, "r+") as css_file:
            content = css_file.read()
            updated_content = content.replace("@COLORS_CSS_PATH", colors_css_path)
            css_file.seek(0)
            css_file.write(updated_content)
            css_file.truncate()
    else:
        logger.warning(f"[Main] colors.css not found at {colors_css_path}")


def apply_style(app: Application):
    logger.info("[Main] Applying CSS")
    app.set_stylesheet_from_file(get_relative_path("styles/main.css"))


if __name__ == "__main__":
    update_main_css()
    if not os.path.isfile(config_path):
        open_config()
    sc = sc
    bar = Bar()
    dock = Dock()
    corners = ScreenCorners()
    osd = OSD()
    notif = NotificationPopup()
    launcher = Launcher()

    app = Application(
        "modus",
        bar,
        launcher,
        osd,
        dock,
    )
    setproctitle.setproctitle("modus")

    # Monitor CSS files for changes
    css_file = monitor_file(get_relative_path("styles"))
    _ = css_file.connect("changed", lambda *_: apply_style(app))

    color_css_file = monitor_file(f"/home/{os.getlogin()}/.cache/material/colors.css")
    _ = color_css_file.connect("changed", lambda *_: apply_style(app))

    # Apply the styles and run the application
    apply_style(app)
    app.run()
