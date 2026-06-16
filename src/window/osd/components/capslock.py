from fabric.utils import logger
from fabric.widgets.label import Label
from utils.utils import svg_file
from .base import BaseOSDContainer
from services.capslock import CapsLock


class CapsLockOSDContainer(BaseOSDContainer):
    def __init__(self, window, **kwargs):
        super().__init__(window, **kwargs)
        self.capslock = CapsLock.get_initial()
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.osd_image = svg_file(
            "misc/caps-lock.svg",
            size=(100, 100),
            name="osd-image",
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )
        self.label = Label(name="osd-label")
        self.add(self.osd_image)
        self._update_display(self.capslock.is_on)

    def _connect_specific_signals(self):
        self.capslock.connect("state_changed", self._on_caps_lock_state_changed)

    def _on_caps_lock_state_changed(self, _, is_on: bool):
        self._update_display(is_on)
        self.update()

    def _update_display(self, is_on: bool):
        icon_path = "caps-lock.svg" if is_on else "caps-lock-off.svg"
        self.osd_image.set_from_file(f"misc/{icon_path}")
        if is_on:
            self.add_style_class("capslock-on")
            self.remove_style_class("capslock-off")
        else:
            self.add_style_class("capslock-off")
            self.remove_style_class("capslock-on")

    def update(self, *_):
        # We don't need a separate display update here as it's handled in the signal
        super().update()

    def destroy(self):
        """Disconnect signals from CapsLock service"""
        try:
            self.capslock.disconnect_by_func(self._on_caps_lock_state_changed)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        super().destroy()
