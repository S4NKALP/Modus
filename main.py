import setproctitle
from loguru import logger

from config.data import APP_NAME
from fabric import Application
from fabric.utils import get_relative_path, monitor_file
from modules.dock import Dock
from modules.launcher.main import Launcher
from modules.osd import OSD
from modules.about import About

# from modules.corners import Corners
from modules.panel.main import Panel
from modules.switcher import ApplicationSwitcher

for log in [
    "fabric.hyprland.widgets",
    "fabric.audio.service",
    "fabric.bluetooth.service",
    "services.network",
    "utils.wayland",
]:
    logger.disable(log)


if __name__ == "__main__":
    setproctitle.setproctitle(APP_NAME)

    # Load configuration
    from config.data import load_config

    About().toggle(None)
    config = load_config()

    panel = Panel()
    # corners = Corners()
    dock = Dock()
    switcher = ApplicationSwitcher()
    launcher = Launcher()
    panel.launcher = launcher
    osd = OSD()

    # Set corners visibility based on config
    # corners_visible = config.get("corners_visible", True)
    # corners.set_visible(corners_visible)

    # Monitor CSS files for changes
    css_file = monitor_file(get_relative_path("styles"))
    _ = css_file.connect("changed", lambda *_: set_css())

    # Make sure corners is added to the app
    app = Application(f"{APP_NAME}", panel, dock, switcher, launcher, osd)

    def set_css():
        app.set_stylesheet_from_file(
            get_relative_path("main.css"),
        )

    app.set_css = set_css

    app.set_css()

    app.run()
