from fabric.widgets.label import Label

from modules.dashboard.tile import Tile
from services.network import NetworkClient

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
        self.nm = NetworkClient()
        self.nm.connect("changed", self.handle_connection_change)
        self.nm.connect("ready", self.handle_connection_change)

    def handle_connection_change(self, *args):
        # Get current network state from NetworkClient properties
        connected = False
        con_label = "Disconnected"

        if self.nm.wifi_device and self.nm.wifi_device.active_access_point:
            connected = True
            con_label = self.nm.wifi_device.active_access_point.ssid
        elif not self.nm.wireless_enabled:
            con_label = "Off"

        if self.state != connected:
            self.state = connected
            if self.state:
                self.remove_style_class("off")
                self.add_style_class("on")
            else:
                self.remove_style_class("on")
                self.add_style_class("off")
            print("State change:", connected)

        self.label.set_label(con_label)
