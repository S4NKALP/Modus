import gi, pam, fabric

gi.require_version("GtkSessionLock", "0.1")
from gi.repository import Gdk, GtkSessionLock

from fabric.widgets.window import Window

# from widgets.wayland import WaylandWindow as Window
from fabric.widgets.entry import Entry
from fabric.widgets.datetime import DateTime
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric import Application

from fabric.utils import get_relative_path


class ContentBox(CenterBox):
    def __init__(self, *args, **kwargs):
        super().__init__(
            name="content-box",
            h_expand=True,
            orientation="vertical",
            v_expand=True,
            start_children=[
                DateTime(
                    formatters=["%A. %d %B"],
                    interval=10000,
                    h_expand=False,
                    v_align="start",
                    v_expand=False,
                    name="date",
                ),
                DateTime(formatters=["%I:%M"], name="clock"),
            ],
            end_children=[
                Entry(
                    placeholder="gib password",
                    name="password-entry",
                    h_align="center",
                    v_align="end",
                    password=True,
                    on_activate=on_activate(self),
                ),
            ],
            **kwargs
        )


class LockScreen(Window):
    def __init__(self, lock: GtkSessionLock.Lock):
        self.lock = lock
        super().__init__(
            title="lock",
            visible=True,
            all_visible=False,
            name="lockscreen-bg",
            anchor="center",
            child=ContentBox(),
        )

    def on_activate(self, entry: Entry, *args):
        if entry.get_text() == "help":
            pass
        elif not pam.authenticate("saumya", (entry.get_text() or "").strip()):
            return
        self.lock.unlock_and_destroy()
        self.destroy()


def initialize():
    lock = GtkSessionLock.prepare_lock()
    lock.lock_lock()
    lockscreen = LockScreen(lock)
    lock.new_surface(lockscreen, Gdk.Display.get_default().get_monitor(0))
    lockscreen.show_all()


if __name__ == "__main__":
    initialize()
    lock = LockScreen(GtkSessionLock.Lock())
    app = Application("lock", lock)

    def set_css():
        app.set_stylesheet_from_file(
            get_relative_path("main.css"),
        )

    app.set_css = set_css

    app.set_css()
    app.run()
