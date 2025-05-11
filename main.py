from loguru import logger
import setproctitle
from fabric import Application
from fabric.utils import get_relative_path, exec_shell_command_async, monitor_file

from config.data import APP_NAME, CACHE_DIR, CONFIG_FILE, DOCK_ICON_SIZE,  APP_NAME_CAP
from modules.bar.bar import Bar
from modules.dock import Dock
from modules.corners import Corners


# Disable unnecessary logging immediately
for log in [
    "fabric.hyprland.widgets",
    "fabric.audio.service",
    "fabric.bluetooth.service",
    "fabric.widgets.wayland",
    "fabric.utils.helpers",
]:
    logger.disable(log)

if __name__ == "__main__":
    setproctitle.setproctitle(APP_NAME)

    # Load configuration
    from config.data import load_config
    config = load_config()
    
    bar = Bar()
    dock = Dock() 
    corners = Corners()

    app = Application(f"{APP_NAME}", bar, dock)

    css_file = monitor_file(get_relative_path("styles"))
    _ = css_file.connect("changed", lambda *_: set_css())

    color_css_file = monitor_file(get_relative_path("./styles/colors.css"))
    _ = color_css_file.connect("changed", lambda *_: set_css())


    def set_css():
        app.set_stylesheet_from_file(
            get_relative_path("styles/main.css"),
            exposed_functions={
                "dock_nmargin": lambda: f"margin-bottom: -{32 + DOCK_ICON_SIZE}px;",
                "dock_sep": lambda: f"margin: 8px 0;",
            },
        )
    app.set_css = set_css

    app.set_css()

    app.run()