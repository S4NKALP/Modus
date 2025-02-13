from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.bluetooth import BluetoothClient, BluetoothDevice
from snippets import MaterialIcon


class BluetoothDeviceSlot(CenterBox):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(name="bluetooth-device", **kwargs)
        self.device = device
        self.device.connect("changed", self.on_changed)
        self.device.connect(
            "notify::closed", lambda *_: self.device.closed and self.destroy()
        )

        self.connection_icon = MaterialIcon("bluetooth_disabled", 12)
        self.connect_button = Button(
            name="bluetooth-connect",
            label="Connect",
            on_clicked=lambda *_: self.device.set_connecting(not self.device.connected),
        )

        self.start_children = [
            Box(
                spacing=8,
                children=[
                    Image(icon_name=device.icon_name + "-symbolic", size=32),
                    Label(label=device.name),
                    self.connection_icon,
                ],
            )
        ]
        self.end_children = self.connect_button

        self.device.emit("changed")  # to update display status

    def on_changed(self, *_):
        self.connection_icon.set_label(
            "bluetooth" if self.device.connected else "bluetooth_disabled"
        )

        if self.device.connecting:
            self.connect_button.set_label(
                "Connecting..." if not self.device.connecting else "Disconnecting..."
            )
        else:
            self.connect_button.set_label(
                "Connect" if not self.device.connected else "Disconnect"
            )
        return


class BluetoothConnections(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="bluetooth",
            spacing=8,
            orientation="vertical",
            **kwargs,
        )

        self.client = BluetoothClient(on_device_added=self.on_device_added)
        self.toggle_icon = MaterialIcon("bluetooth_disabled")
        self.scan_icon = MaterialIcon("stop")

        self.scan_button = Button(
            name="bluetooth-scan",
            child=self.scan_icon,
            tooltip_text="scan",
            on_clicked=lambda *_: self.client.toggle_scan(),
        )
        self.toggle_button = Button(
            name="bluetooth-toggle",
            tooltip_text="bluetooth-toggle",
            child=self.toggle_icon,
            on_clicked=lambda *_: self.client.toggle_power(),
        )

        self.client.connect(
            "notify::enabled",
            lambda *_: self.toggle_icon.set_label(
                "bluetooth" if self.client.enabled else "bluetooth_disabled"
            ),
        )
        self.client.connect(
            "notify::scanning",
            lambda *_: self.scan_icon.set_label(
                "stop" if self.client.scanning else "bluetooth_searching"
            ),
        )

        self.paired_box = Box(spacing=2, orientation="vertical")
        self.available_box = Box(spacing=2, orientation="vertical")

        self.children = [
            CenterBox(
                name="bluetooth-header",
                start_children=self.scan_button,
                center_children=Label(name="bluetooth-text", label="Bluetooth Devices"),
                end_children=self.toggle_button,
            ),
            Label(name="bluetooth-section", label="Paired"),
            ScrolledWindow(
                name="bluetooth-paired",
                v_expand=True,
                child=self.paired_box,
            ),
            Label(name="bluetooth-section", label="Available"),
            ScrolledWindow(
                name="bluetooth-paired",
                v_expand=True,
                child=self.available_box,
            ),
        ]

        # to run notify closures thus display the status
        # without having to wait until an actual change
        self.client.notify("scanning")
        self.client.notify("enabled")

    def on_device_added(self, client: BluetoothClient, address: str):
        if not (device := client.get_device(address)):
            return
        slot = BluetoothDeviceSlot(device)

        if device.paired:
            return self.paired_box.add(slot)
        return self.available_box.add(slot)
