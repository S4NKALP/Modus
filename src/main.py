import atexit
import os

# App-capture typelib path (built via meson in src/window/switcher/app-capture/builddir)
# Must be set before gi is imported so the typelib search path includes it.
# Note: LD_LIBRARY_PATH does not take effect in the current process, so the
# .so is preloaded via ctypes in window/switcher/main.py instead.
_app_capture_builddir = os.path.join(
    os.path.dirname(__file__), "window", "switcher", "app-capture", "builddir"
)
if os.path.isdir(_app_capture_builddir):
    _cur = os.environ.get("GI_TYPELIB_PATH", "")
    if _app_capture_builddir not in _cur.split(os.pathsep):
        os.environ["GI_TYPELIB_PATH"] = _app_capture_builddir + (
            os.pathsep + _cur if _cur else ""
        )

from fabric import Application
from fabric.utils import get_relative_path, logger, monitor_file

for log in [
    "fabric",
    "services",
    "window",
    "utils",
    "window.globalmenu",
]:
    logger.disable(log)

from services.keyboard_layout import KeyboardLayout
from shared.data import APP_NAME, load_config
from utils.functions import set_process_name
from window.desktop.widget import Deskwidgets
from window.dock import Dock
from window.lock import LockScreenWrapper
from window.notification.notification import ModusNoti
from window.osd.main import OSDWindow
from window.panel.main import Panel
from window.screencapture import ScreenCaptureWindow
from window.spotlight.main import SpotlightWindow
from window.switcher import ApplicationSwitcher


def main():

    # Generate colors.css if it doesn't exist
    colors_css_path = get_relative_path("styles/colors.css")
    if not os.path.exists(colors_css_path):
        from utils.gtk_utils import generate_colors_from_wallpaper

        default_wallpaper = get_relative_path("assets/wallpaper_example/example-1.png")
        if os.path.exists(default_wallpaper):
            generate_colors_from_wallpaper(default_wallpaper)

    set_process_name(APP_NAME)

    load_config()

    from services.config import config

    _debug = config().get("debug", False)

    if not _debug:
        logger.disable("modus_plugin_builtin_emoji")
    else:
        logger.enable("fabric")
        logger.enable("services")
        logger.enable("window")
        logger.enable("utils")
        logger.enable("window.globalmenu")

    switcher = ApplicationSwitcher()
    panel = Panel()
    modusnoti = ModusNoti()
    spotlight = SpotlightWindow()
    panel.set_spotlight_toggle(spotlight.toggle)
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
        spotlight,
    )

    def set_css():
        app.set_stylesheet_from_file(get_relative_path("styles/main.css"))

    app.set_css = set_css
    app.set_css()

    def cleanup_css_monitors():
        for m in css_monitors:
            try:
                m.cancel()
            except Exception as e:
                logger.warning(f"[main] m.cancel() failed: {e}")

    atexit.register(cleanup_css_monitors)

    # Inject into the executing module's namespace (__main__)
    # to emulate what happened when this file was run directly.
    # This allows fabric-cli exec to execute commands flawlessly.
    import __main__

    __main__.app = app
    __main__.switcher = switcher
    __main__.panel = panel
    __main__.modusnoti = modusnoti
    __main__.spotlight = spotlight
    __main__.deskwidget = deskwidget
    __main__.dock = dock
    __main__.osd = osd
    __main__.osd_show_audio = osd.osd_show_audio
    __main__.osd_show_brightness = osd.osd_show_brightness
    __main__.screencapture = screencapture
    __main__.lock_screen = LockScreenWrapper()
    __main__.switch_keyboard_layout = KeyboardLayout.switch_keyboard_layout

    app.run()


if __name__ == "__main__":
    main()
