import getpass

import pam
from fabric import Application
from fabric.utils import Gdk, GLib, get_relative_path, logger, os
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.shapes import Corner
from fabric.widgets.window import Window
from gi.repository import GtkSessionLock  # pyright: ignore[reportAttributeAccessIssue]

from shared.widgets.circle_image import CircleImage as Image
from utils.functions import set_process_name
from utils.utils import svg_file
from window.panel.components.indicators import (
    BatteryIndicator,
    BluetoothIndicator,
    NetworkIndicator,
)

for log in [
    "fabric.audio.service",
    "fabric.core.application",
    "fabric.bluetooth.service",
    "fabric.notifications.service",
    "services.network",
]:
    logger.disable(log)


class IndicatorBox(Box):
    def __init__(self, *args, **kwargs):
        super().__init__(
            h_align="end",
            name="indicator-box",
            spacing=5,
            h_expand=True,
            children=[
                BatteryIndicator(show_window=False),
                BluetoothIndicator(show_window=False),
                NetworkIndicator(show_window=False),
            ],
        )


class ContentBox(CenterBox):
    def __init__(self, on_activate, *args, **kwargs):
        self.password_entry = Entry(
            placeholder="Enter Password",
            name="password-entry",
            h_align="center",
            v_align="center",
            visible=False,
            password=True,
            on_activate=on_activate,
        )

        face_icon = os.path.expanduser("~/.face.icon")
        if not os.path.exists(face_icon):
            face_icon = get_relative_path("../assets/default.png")
        self.password_entry.set_property("xalign", 0.5)
        self.username_label = Label(
            label=f"{getpass.getuser().title()}",
            name="username",
            visible=True,
            h_align="center",
            v_align="center",
        )
        self.unlock_text = Label(
            label="Touch ID or Enter Password",
            name="unlock-text",
        )
        super().__init__(
            name="content-box",
            h_expand=True,
            orientation="vertical",
            v_expand=True,
            start_children=[
                IndicatorBox(),
                DateTime(
                    formatters=["%A,%B %-d"],
                    interval=10000,
                    h_expand=False,
                    v_align="start",
                    v_expand=False,
                    name="lock-date",
                ),
                DateTime(formatters=["%I:%M"], name="lock-clock"),
            ],
            end_children=[
                Box(
                    name="profile-box",
                    h_align="center",
                    h_expand=True,
                    v_expand=True,
                    v_align="end",
                    children=[
                        Image(
                            name="face-icon",
                            image_file=face_icon,
                            size=64,
                        ),
                    ],
                ),
                Box(
                    name="container-box",
                    orientation="v",
                    v_align="end",
                    h_align="center",
                    h_expand=True,
                    v_expand=True,
                    children=[
                        self.username_label,
                        self.password_entry,
                    ],
                ),
                Box(
                    name="unlock-box",
                    v_align="end",
                    h_align="center",
                    h_expand=True,
                    v_expand=True,
                    children=[
                        self.unlock_text,
                    ],
                ),
            ],
            **kwargs,
        )


class LockScreen(Window):
    def __init__(self, lock: GtkSessionLock.Lock):
        self._hide_timeout_id = None
        self.lock = lock
        self.content = ContentBox(self.on_activate)
        self.lock_notch = self._build_lock_notch()
        super().__init__(
            title="lock",
            visible=False,
            all_visible=False,
            name="lockscreen-bg",
            anchor="center",
            child=Box(
                orientation="vertical",
                children=[self.lock_notch, self.content],
            ),
        )

        self.content.password_entry.set_visible(False)
        self.connect("key-press-event", self._on_keypress)

        bg = os.path.expanduser("~/.current.wall")
        if not os.path.exists(bg):
            bg = get_relative_path("../assets/wallpapers_example/example-1.png")
        self.set_style(f"background-image: url('{bg}');")

    def _build_lock_notch(self):
        return CenterBox(
            name="lock-notch",
            orientation="h",
            h_align="center",
            v_align="center",
            start_children=Box(
                name="lock-notch-corner-left",
                orientation="v",
                h_align="start",
                children=[
                    Corner(
                        name="lock-notch-corner",
                        orientation="top-right",
                        size=20,
                    ),
                ],
            ),
            center_children=CenterBox(
                name="lock-notch-stack",
                v_expand=True,
                h_expand=True,
                end_children=Box(
                    children=[svg_file("notch/lock.svg", size=16)],
                    style="margin-right: 12px;",
                ),
            ),
            end_children=Box(
                name="lock-notch-corner-right",
                orientation="v",
                h_align="end",
                children=[
                    Corner(
                        name="lock-notch-corner",
                        orientation="top-left",
                        size=20,
                    ),
                ],
            ),
        )

    def _on_keypress(self, widget, event):
        keyval = event.keyval

        # ESC pressed → hide entry immediately
        if keyval == Gdk.KEY_Escape and self.content.password_entry.get_visible():
            self._hide_entry()
            return

        # Show entry if hidden
        if not self.content.password_entry.get_visible():
            self.content.username_label.set_visible(False)
            self.content.password_entry.set_visible(True)
            self.content.password_entry.grab_focus()
            self._start_hide_timer()
        else:
            # Reset timer if already visible
            self._restart_hide_timer()

    def _start_hide_timer(self):
        self._stop_hide_timer()  # just in case
        self._hide_timeout_id = GLib.timeout_add_seconds(5, self._hide_entry)
        # 10 seconds of inactivity before hiding

    def _restart_hide_timer(self):
        self._start_hide_timer()

    def _stop_hide_timer(self):
        if self._hide_timeout_id:
            GLib.source_remove(self._hide_timeout_id)
            self._hide_timeout_id = None

    def _hide_entry(self):
        self._stop_hide_timer()
        self.content.password_entry.set_visible(False)
        self.content.username_label.set_visible(True)
        return False  # stop timeout

    def on_activate(self, entry: Entry, *args):
        if not pam.authenticate(getpass.getuser(), (entry.get_text() or "").strip()):
            entry.set_text("")
            entry.set_placeholder_text("Wrong Password")
            return
        self.lock.unlock_and_destroy()
        self.destroy()
        GLib.idle_add(app.quit)  # schedules quit after unlock


def initialize():
    lock = GtkSessionLock.prepare_lock()
    lock.lock_lock()
    lockscreen = LockScreen(lock)
    lock.new_surface(
        lockscreen,
        Gdk.Display.get_default().get_monitor(  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
            0
        ),
    )
    lockscreen.show()


def main():
    set_process_name("lockscreen")
    initialize()
    lockscreen = LockScreen(GtkSessionLock.Lock())

    global app
    app = Application("lock", lockscreen)

    def set_css():
        app.set_stylesheet_from_file(
            get_relative_path("../styles/main.css"),
        )

    app.set_css = set_css  # pyright: ignore[reportAttributeAccessIssue]

    app.set_css()  # pyright: ignore[reportAttributeAccessIssue]
    app.run()


if __name__ == "__main__":
    main()
