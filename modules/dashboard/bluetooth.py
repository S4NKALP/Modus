from fabric.widgets.label import Label

from modules.dashboard.tile import Tile

import utils.icons as icons


class Bluetooth(Tile):
    def __init__(self, **kwargs):
        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Off",
            h_align="start",
        )
        self.state = False

        super().__init__(
            label="Bluetooth",
            props=self.label,
            markup=icons.bluetooth,
            menu=True,
            **kwargs,
        )

        if self.state:
            self.add_style_class("on")
        else:
            self.add_style_class("off")
