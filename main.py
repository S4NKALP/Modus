from fabric import Application
from fabric.utils import get_relative_path, logger, monitor_file

from config.data import APP_NAME
from modules.desktop.widget import Deskwidgets
from modules.launcher.main import Launcher
from modules.notification.notification import ModusNoti
from modules.osd.main import OSDWindow
from modules.panel.main import Panel
from modules.switcher import ApplicationSwitcher
from utils.functions import set_process_name

for log in [
    "fabric.hyprland.widgets",
    "fabric.audio.service",
    "fabric.bluetooth.service",
    "services.network",
    "utils.wayland",
]:
    logger.disable(log)

if __name__ == "__main__":
    set_process_name(APP_NAME)

    # Load configuration
    from config.data import load_config

    # About().toggle(None)
    config = load_config()
    switcher = ApplicationSwitcher()
    panel = Panel()
    modusnoti = ModusNoti()
    launcher = Launcher()
    deskwidget = Deskwidgets()
    osd = OSDWindow()
    # Monitor CSS files for changes
    css_file = monitor_file(get_relative_path("styles"))
    _ = css_file.connect("changed", lambda *_: set_css())

    app = Application(
        f"{APP_NAME}",
        panel,
        modusnoti,
        deskwidget.top_left,
        deskwidget.bottom_left,
        osd,
        launcher,
        switcher,
    )

    def set_css():
        app.set_stylesheet_from_file(
            get_relative_path("styles/main.css"),
        )

    app.set_css = set_css

    app.set_css()

    app.run()
