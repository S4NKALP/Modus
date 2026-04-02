from fabric.widgets.label import Label
from utils.utils import svg_file
from .base import BaseOSDContainer
from services.keyboard_layout import KeyboardLayout


class KeyboardLayoutOSDContainer(BaseOSDContainer):
    def __init__(self, window, **kwargs):
        super().__init__(window, **kwargs)
        self.keyboard_layout = KeyboardLayout.get_initial()
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.osd_image = svg_file(
            "misc/keyboard-layout.svg",
            size=(100, 100),
            name="osd-image",
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )
        self.label = Label(name="osd-label")
        self.add(self.osd_image)
        self.add(self.label)
        self.label.set_text(self.keyboard_layout.current_layout)

    def _connect_specific_signals(self):
        self.keyboard_layout.connect("layout_changed", self._on_layout_changed)

    def _on_layout_changed(self, service, layout: str):
        if not self.is_hovered():
            self.label.set_text(layout)
            self.update()

    def update(self, *_):
        self.label.set_text(self.keyboard_layout.current_layout)
        super().update()
