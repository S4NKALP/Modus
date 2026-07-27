from fabric.widgets.box import Box
from fabric.widgets.label import Label

from window.desktop.registry import DesktopWidgetRegistry


class ExampleClockWidget(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="example-widget",
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="center",
            v_align="center",
            **kwargs,
        )
        self.label = Label(
            name="examplelabel",
            label="Hello Desktop",
            justification="center",
        )
        self.add(self.label)


DesktopWidgetRegistry.register(
    "example",
    ExampleClockWidget,
    (174, 174),
    (0.45, 0.45),
)
