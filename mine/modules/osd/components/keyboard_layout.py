from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window

from modules.osd.components.base import BaseOSDContainer
from services import KeyboardLayout


class KeyboardLayoutOSDContainer(BaseOSDContainer):
    def __init__(self, window: Window, **kwargs):
        super().__init__(window, **kwargs)
        self.icon = Image(icon_name="input-keyboard-symbolic", icon_size=26)
        self.label = Label()

        self.keyboard_layout = KeyboardLayout.get_initial()

        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        # Get initial layout from service
        layout = self.keyboard_layout.current_layout
        self.label.set_text(layout)
        self.children = self.icon, self.label

    def _connect_specific_signals(self):
        # Connect to layout change signal from service
        self.keyboard_layout.connect("layout_changed", self._on_layout_changed)

    def _on_layout_changed(self, service, layout: str):
        """Handle layout changes from the service."""
        if not self.is_hovered():
            current_text = self.label.get_text()
            if current_text != layout:
                self.label.set_text(layout)
                self.show_kb_layout_osd()

    def show_kb_layout_osd(self):
        """Trigger the OSD to show the keyboard layout container."""
        if self.osd:
            self.osd.show_kb_layout_osd()
        else:
            self.update()

    def update(self, *_):
        """Override to update display before showing OSD."""
        # Update the display with current layout
        layout = self.keyboard_layout.current_layout
        self.label.set_text(layout)

        # Call parent's update to show the OSD
        super().update()
