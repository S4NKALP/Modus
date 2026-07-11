import atexit
import os

from fabric import Application
from fabric.utils import get_relative_path, logger, monitor_file

for log in [
    "fabric",
    "services",
    "window",
    "utils",
    "globalmenu",
]:
    logger.disable(log)

from services.keyboard_layout import KeyboardLayout
from shared.data import APP_NAME, load_config
from utils.functions import set_process_name
from window.desktop.widget import Deskwidgets
from window.dock import Dock
from window.notification.notification import ModusNoti
from window.osd.main import OSDWindow
from window.panel.main import Panel
from window.screencapture import ScreenCaptureWindow
from window.switcher import ApplicationSwitcher

# class LazyLauncher:
#     def __init__(self):
#         self._instance = None
#
#     def _get_instance(self):
#         if self._instance is None:
#             from window.launcher.main import Launcher
#
#             self._instance = Launcher()
#             import __main__
#
#             if hasattr(__main__, "app") and __main__.app:
#                 __main__.app.add_window(self._instance)
#         return self._instance
#
#     def __getattr__(self, name):
#         return getattr(self._get_instance(), name)


def main():

    # Generate colors.css if it doesn't exist
    colors_css_path = get_relative_path("styles/colors.css")
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
    # launcher = LazyLauncher()
    deskwidget = Deskwidgets()
    dock = Dock()
    osd = OSDWindow()
    screencapture = ScreenCaptureWindow()

    # Monitor CSS files and subdirectories for changes
    css_monitors = []
    for root, dirs, files in os.walk(get_relative_path("styles/")):
        monitor = monitor_file(root)
        monitor.connect("changed", lambda *_: set_css())
        css_monitors.append(monitor)

    app = Application(
        f"{APP_NAME}",
        panel,
        modusnoti,
        deskwidget.top_left,
        deskwidget.bottom_left,
        osd,
        switcher,
        dock,
        screencapture,
    )

    def set_css():
        app.set_stylesheet_from_file(get_relative_path("styles/main.css"))

    app.set_css = set_css
    app.set_css()

    def cleanup_css_monitors():
        for m in css_monitors:
            try:
                m.cancel()
            except Exception:
                pass

    atexit.register(cleanup_css_monitors)

    # Inject into the executing module's namespace (__main__)
    # to emulate what happened when this file was run directly.
    # This allows fabric-cli exec to execute commands flawlessly.
    import __main__

    __main__.app = app
    __main__.switcher = switcher
    __main__.panel = panel
    __main__.modusnoti = modusnoti
    # __main__.launcher = launcher
    __main__.deskwidget = deskwidget
    __main__.dock = dock
    __main__.osd = osd
    __main__.screencapture = screencapture
    __main__.switch_keyboard_layout = KeyboardLayout.switch_keyboard_layout

    app.run()


if __name__ == "__main__":
    main()
