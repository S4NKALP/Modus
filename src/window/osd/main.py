from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window

from .components import (
    AudioOSDContainer,
    BrightnessOSDContainer,
)


class OSD(Box):
    def __init__(self, window: Window, **kwargs):
        super().__init__(title="modus-osd", name="osd", **kwargs)
        self.window = window

        self.revealer = Revealer(
            transition_type="slide-up",
            transition_duration=100,
            child_revealed=False,
        )
        self.children = [self.revealer]

        self.containers = {
            "audio": AudioOSDContainer(window),
            "brightness": BrightnessOSDContainer(window),
        }

        # Set the OSD reference in containers
        for container in self.containers.values():
            container.osd = self

        self.current_container = None

    def show_container(self, container):
        if self.current_container != container:
            self.revealer.children = [container]
            self.current_container = container
        self.revealer.set_reveal_child(True)

    def show_audio_osd(self):
        from services.config import get_config

        if not get_config("panel.osd", True):
            return
        self.show_container(self.containers.get("audio"))

    def show_brightness_osd(self):
        from services.config import get_config

        if not get_config("panel.osd", True):
            return
        self.show_container(self.containers.get("brightness"))

    def destroy(self):
        """Break the OSD <-> window reference cycle before teardown."""
        self.window = None
        super().destroy()


class OSDWindow(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="osd-window",
            title="modus-osd",
            anchor="bottom",
            margin="0px 0px 40px 0px",
            visible=False,
            all_visible=False,
            pass_through=True,
            layer="overlay",
            **kwargs,
        )
        self.osd = OSD(window=self)
        self.add(self.osd)

    def osd_show_audio(self):
        from services.config import get_config

        if not get_config("panel.osd", True):
            return
        self.osd.containers["audio"].update()

    def osd_show_brightness(self):
        from services.config import get_config

        if not get_config("panel.osd", True):
            return
        self.osd.containers["brightness"].update()

    def destroy(self):
        """Break the OSD <-> window reference cycle before teardown."""
        osd = getattr(self, "osd", None)
        self.osd = None
        if osd is not None:
            osd.window = None
        super().destroy()
