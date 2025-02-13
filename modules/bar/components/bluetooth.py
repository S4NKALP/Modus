from fabric.bluetooth import BluetoothClient
from fabric.widgets.box import Box
from snippets import MaterialIcon


class BluetoothIndicator(Box):
    ICON_ENABLED = "bluetooth"
    ICON_DISABLED = "bluetooth_disabled"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bluetooth_client = BluetoothClient()

        self.bluetooth_icon = None

        self.bluetooth_client.connect("changed", self.update_bluetooth_status)

        self.update_bluetooth_status()

    def update_bluetooth_status(self, *_):
        icon_label = (
            self.ICON_ENABLED if self.bluetooth_client.enabled else self.ICON_DISABLED
        )

        new_icon = MaterialIcon(icon_label, size=16)

        if self.bluetooth_icon:
            self.remove(self.bluetooth_icon)

        self.bluetooth_icon = new_icon
        self.add(self.bluetooth_icon)

    def on_destroy(self):
        self.bluetooth_client.disconnect("changed", self.update_bluetooth_status)
