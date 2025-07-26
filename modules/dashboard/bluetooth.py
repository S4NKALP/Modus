from fabric.bluetooth import BluetoothClient, BluetoothDevice
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import Gtk

from modules.dashboard.tile import Tile
import utils.icons as icons


class BluetoothDeviceSlot(CenterBox):
    """A widget representing a single Bluetooth device in the dashboard."""

    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(name="bluetooth-device", **kwargs)
        self.device = device
        self.device.connect("changed", self.on_changed)
        self.device.connect(
            "notify::closed", lambda *_: self.device.closed and self.destroy()
        )

        self.connection_label = Label(
            name="bluetooth-connection",
            markup=icons.bluetooth_disconnected
        )
        self.connect_button = Button(
            name="bluetooth-connect",
            label="Connect",
            on_clicked=lambda *_: self.device.set_connecting(not self.device.connected),
            style_classes=["connected"] if self.device.connected else None,
        )

        self.start_children = [
            Box(
                spacing=8,
                h_expand=True,
                h_align="fill",
                children=[
                    Image(icon_name=device.icon_name + "-symbolic", size=16),
                    Label(
                        label=device.name,
                        h_expand=True,
                        h_align="start",
                        ellipsization="end",
                    ),
                    self.connection_label,
                ],
            )
        ]
        self.end_children = self.connect_button

        self.device.emit("changed")

    def on_changed(self, *_):
        """Handle device state changes."""
        self.connection_label.set_markup(
            icons.bluetooth_connected
            if self.device.connected
            else icons.bluetooth_disconnected
        )
        if self.device.connecting:
            self.connect_button.set_label(
                "Connecting..." if not self.device.connecting else "..."
            )
        else:
            self.connect_button.set_label(
                "Connect" if not self.device.connected else "Disconnect"
            )
        if self.device.connected:
            self.connect_button.add_style_class("connected")
        else:
            self.connect_button.remove_style_class("connected")


class Bluetooth(Tile):
    """Bluetooth tile for the dashboard that shows Bluetooth status and devices."""

    def __init__(self, **kwargs):
        # Create status label
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

        # Initialize bluetooth client with device handling
        self.bluetooth_client = BluetoothClient(on_device_added=self.on_device_added)
        self.bluetooth_client.connect("notify::enabled", self._on_bluetooth_state_changed)
        self.bluetooth_client.connect("notify::scanning", self._update_scan_label)

        # Initialize state
        self._update_tile_state()

    def _update_tile_state(self):
        """Update tile visual state based on Bluetooth status."""
        self.state = self.bluetooth_client.enabled
        if self.state:
            self.remove_style_class("off")
            self.add_style_class("on")
            self.label.set_label("On")
        else:
            self.remove_style_class("on")
            self.add_style_class("off")
            self.label.set_label("Off")

    def create_content(self):
        """Create the detailed bluetooth content for the dashboard."""
        # Create Bluetooth toggle switch (like notifications DND switch)
        self.bluetooth_switch = Gtk.Switch(name="bluetooth-switch")
        self.bluetooth_switch.set_vexpand(False)
        self.bluetooth_switch.set_valign(Gtk.Align.CENTER)
        self.bluetooth_switch.set_active(self.bluetooth_client.enabled)
        self.bluetooth_switch.connect("notify::active", self._on_bluetooth_toggle)

        # Create Bluetooth status icon
        self.bluetooth_status_icon = Label(
            name="bluetooth-status-icon",
            markup=icons.bluetooth if self.bluetooth_client.enabled else icons.bluetooth_off
        )

        # Create scan button with icon
        self.scan_label = Label(name="bluetooth-scan-label", markup=icons.radar)
        self.scan_button = Button(
            name="bluetooth-scan",
            child=self.scan_label,
            tooltip_text="Scan for Bluetooth devices",
            on_clicked=lambda *_: self.bluetooth_client.toggle_scan(),
        )

        # Create device containers
        self.paired_box = Box(spacing=2, orientation="v")
        self.available_box = Box(spacing=2, orientation="v")

        # Create content structure
        content_box = Box(spacing=4, orientation="v")
        content_box.add(self.paired_box)
        content_box.add(Label(name="bluetooth-section", label="Available"))
        content_box.add(self.available_box)

        # Main container
        main_container = Box(
            name="bluetooth-content",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=True,
            h_align="fill",
            style_classes=["tile-content"],
            children=[
                CenterBox(
                    name="bluetooth-header",
                    start_children=[self.bluetooth_switch, self.bluetooth_status_icon],
                    center_children=Label(name="bluetooth-text", label="Bluetooth Devices"),
                    end_children=self.scan_button,
                ),
                ScrolledWindow(
                    name="bluetooth-devices",
                    min_content_size=(-1, -1),
                    child=content_box,
                    v_expand=True,
                    propagate_width=False,
                    propagate_height=False,
                ),
            ]
        )

        # Initialize notifications
        self.bluetooth_client.notify("scanning")
        self.bluetooth_client.notify("enabled")

        return main_container

    def on_device_added(self, client: BluetoothClient, address: str):
        """Handle new device discovery."""
        if not (device := client.get_device(address)):
            return
        slot = BluetoothDeviceSlot(device)

        if device.paired:
            return self.paired_box.add(slot)
        return self.available_box.add(slot)

    def _update_scan_label(self, *_):
        """Update scan button appearance based on scanning state."""
        if self.bluetooth_client.scanning:
            self.scan_label.add_style_class("scanning")
            self.scan_button.add_style_class("scanning")
            self.scan_button.set_tooltip_text("Stop scanning for Bluetooth devices")
        else:
            self.scan_label.remove_style_class("scanning")
            self.scan_button.remove_style_class("scanning")
            self.scan_button.set_tooltip_text("Scan for Bluetooth devices")

    def _on_bluetooth_toggle(self, switch, *_):
        """Handle Bluetooth toggle switch."""
        enabled = switch.get_active()
        self.bluetooth_client.enabled = enabled
        self._update_content_state()

    def _on_bluetooth_state_changed(self, *_):
        """Handle bluetooth state change."""
        self._update_tile_state()
        self._update_content_state()

    def _update_content_state(self):
        """Update content area based on Bluetooth state."""
        if hasattr(self, 'bluetooth_switch'):
            self.bluetooth_switch.set_active(self.bluetooth_client.enabled)

        if hasattr(self, 'bluetooth_status_icon'):
            self.bluetooth_status_icon.set_markup(
                icons.bluetooth if self.bluetooth_client.enabled else icons.bluetooth_off
            )


