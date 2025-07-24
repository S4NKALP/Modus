from fabric.widgets.label import Label

from modules.dashboard.tile import Tile
from services.nett import NetworkService

import utils.icons as icons


class Network(Tile):
    def __init__(self, **kwargs):
        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Disconnected",
            h_align="start",
        )
        self.state = False

        super().__init__(
            label="Wi-Fi",
            props=self.label,
            markup=icons.wifi,
            menu=True,
            **kwargs,
        )
        self.nm = NetworkService()
        self.nm.connect("connection-change", self.handle_connection_change)
        self.nm.init_props()

    def handle_connection_change(
        self, source, con_label: str, connected: bool, status: str
    ):
        if self.state != connected:
            self.state = connected
            if self.state:
                self.remove_style_class("off")
                self.add_style_class("on")
            else:
                self.remove_style_class("on")
                self.add_style_class("off")
            print("State change:", connected)

        if not connected:
            if status == "Wi-Fi Off":
                self.label.set_label("Off")
            elif status == "Wi-Fi On (No Connection)":
                self.label.set_label("Disconnected")
            elif status == "Connecting…":
                self.label.set_label("Connecting…")
            else:
                self.label.set_label("Unknown")
        else:
            self.label.set_label(con_label or "Connected")
