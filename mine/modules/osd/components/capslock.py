from fabric.utils import GLib
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window

from modules.osd.components.base import BaseOSDContainer
from services import CapsLock


class CapsLockOSDContainer(BaseOSDContainer):
    def __init__(self, window: Window, **kwargs):
        super().__init__(window, **kwargs)
        self.capslock = CapsLock.get_initial()
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.icon = Image(icon_name="capslock-disabled-symbolic", icon_size=26)
        self.label = Label()

        self.update_icon(False)
        self.update_label(False)
        self.children = self.icon, self.label

    def _connect_specific_signals(self):
        self.capslock.connect("state_changed", self._on_caps_lock_state_changed)
        GLib.timeout_add(100, self._initialize_state)

    def _initialize_state(self):
        """Initialize the caps lock state after component setup."""
        is_caps_on = self.capslock.is_on
        self.update_icon(is_caps_on)
        self.update_label(is_caps_on)
        return False

    def _on_caps_lock_state_changed(self, _, is_on: bool):
        """Handle CapsLock state changes."""
        if not self.is_hovered():
            self.update_icon(is_on)
            self.update_label(is_on)
            self.show_capslock_osd()

    def show_capslock_osd(self):
        """Trigger the OSD to show the CapsLock container."""
        if self.osd:
            self.osd.show_capslock_osd()
        else:
            self.update()

    def update_icon(self, is_on: bool):
        self.icon.set_from_icon_name(
            "capslock-enabled-symbolic" if is_on else "capslock-disabled-symbolic",
            26,
        )
        if is_on:
            self.icon.style_classes = "capslock-on"
        else:
            self.icon.style_classes = "capslock-off"

    def update_label(self, is_on: bool):
        self.label.set_text("CapsLock ON" if is_on else "CapsLock OFF")
        if is_on:
            self.label.style_classes = "capslock-on"
        else:
            self.label.style_classes = "capslock-off"
