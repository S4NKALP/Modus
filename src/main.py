import os
from fabric import Application
from fabric.utils import get_relative_path, logger, monitor_file

from shared.data import APP_NAME, load_config
from utils.functions import set_process_name
from window.desktop.widget import Deskwidgets
from window.dock import Dock
from window.launcher.main import Launcher
from window.notification.notification import ModusNoti
from window.osd.main import OSDWindow
from window.panel.main import Panel
from window.switcher import ApplicationSwitcher

for log in [
    "fabric",
    "services",
    "window",
    "utils",
]:
    logger.disable(log)


def main():

    # Generate colors.css if it doesn't exist
    colors_css_path = get_relative_path("shared/styles/colors.css")
    if not os.path.exists(colors_css_path):
        from utils.utils import generate_colors_from_wallpaper

        default_wallpaper = get_relative_path("assets/wallpaper_example/example-1.png")
        if os.path.exists(default_wallpaper):
            generate_colors_from_wallpaper(default_wallpaper)

    set_process_name(APP_NAME)

    load_config()
    switcher = ApplicationSwitcher()
    panel = Panel()
    modusnoti = ModusNoti()
    launcher = Launcher()
    deskwidget = Deskwidgets()
    dock = Dock()
    osd = OSDWindow()

    # Monitor CSS files for changes
    css_file = monitor_file(get_relative_path("shared/styles"))
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
        dock,
    )

    def set_css():
        app.set_stylesheet_from_file(
            get_relative_path("shared/styles/main.css"),
        )

    app.set_css = set_css
    app.set_css()

    # Inject into the executing module's namespace (__main__)
    # to emulate what happened when this file was run directly.
    # This allows fabric-cli exec to execute commands flawlessly.
    import __main__

    __main__.app = app
    __main__.switcher = switcher
    __main__.panel = panel
    __main__.modusnoti = modusnoti
    __main__.launcher = launcher
    __main__.deskwidget = deskwidget
    __main__.dock = dock
    __main__.osd = osd

    app.run()


if __name__ == "__main__":
    main()
