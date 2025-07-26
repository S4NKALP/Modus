from fabric.bluetooth import BluetoothClient, BluetoothDevice
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

from modules.dashboard.tile import Tile, add_hover_cursor
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
        self.bluetooth_client.connect("device-added", self._on_device_connection_changed)
        self.bluetooth_client.connect("device-removed", self._on_device_connection_changed)

        # Initialize state
        self._update_tile_state()

        # Override the type_box button behavior to toggle Bluetooth
        self._setup_content_button()

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

        # Update tile icon based on Bluetooth state
        self._update_tile_icon()

    def _setup_content_button(self):
        """Setup the content button to toggle Bluetooth instead of showing menu."""
        if hasattr(self, 'type_box'):
            # Disconnect the existing click handler
            self.type_box.disconnect_by_func(self.handle_click)
            # Connect to Bluetooth toggle handler
            self.type_box.connect("clicked", self._on_bluetooth_toggle)

    def _on_bluetooth_toggle(self, *_):
        """Handle Bluetooth toggle when clicking on the main content area."""
        # Toggle Bluetooth state
        self.bluetooth_client.enabled = not self.bluetooth_client.enabled

    def _update_tile_icon(self):
        """Update the tile icon based on Bluetooth status and connected devices."""
        if not self.bluetooth_client.enabled:
            # Bluetooth is disabled
            self.icon.set_markup(icons.bluetooth_off)
            return

        # Bluetooth is enabled - check for connected devices
        connected_devices = self.bluetooth_client.connected_devices
        if connected_devices:
            # Has connected devices
            self.icon.set_markup(icons.bluetooth_connected)
        else:
            # Enabled but no connected devices
            if self.bluetooth_client.scanning:
                # Currently scanning - could add animation here if desired
                self.icon.set_markup(icons.bluetooth)
            else:
                # Idle state
                self.icon.set_markup(icons.bluetooth)

    def create_content(self):
        """Create the detailed bluetooth content for the dashboard."""
        # Create back button with chevron left icon
        self.back_button_icon = Label(
            name="bluetooth-back-label",
            markup=icons.chevron_left
        )
        self.back_button = Button(
            name="bluetooth-back",
            child=self.back_button_icon,
            tooltip_text="Back to notifications",
            on_clicked=self._on_back_clicked
        )
        add_hover_cursor(self.back_button)

        # Create scan button with icon
        self.scan_label = Label(name="bluetooth-scan-label", markup=icons.radar)
        self.scan_button = Button(
            name="bluetooth-scan",
            child=self.scan_label,
            tooltip_text="Scan for Bluetooth devices",
            on_clicked=lambda *_: self.bluetooth_client.toggle_scan(),
        )
        add_hover_cursor(self.scan_button)

        # Create device containers
        self.paired_box = Box(spacing=2, orientation="v")
        self.available_box = Box(spacing=2, orientation="v")

        # Create content structure
        content_box = Box(spacing=4, orientation="v")
        content_box.add(self.paired_box)
        content_box.add(Label(name="bluetooth-section", label="Available"))
        content_box.add(self.available_box)

        # Create header
        header_box = CenterBox(
            name="bluetooth-header",
            start_children=[self.back_button],
            center_children=[Label(name="bluetooth-title", label="Bluetooth Devices")],
            end_children=[self.scan_button]
        )

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
                header_box,
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

        # Connect to device changes to update tile icon when connection state changes
        device.connect("changed", self._on_device_connection_changed)

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

        # Update tile icon when scanning state changes
        self._update_tile_icon()

    def _on_back_clicked(self, *_):
        """Handle back button click - return to default (notifications) view."""
        if self.dashboard_instance:
            self.dashboard_instance.reset_to_default()

    def _on_bluetooth_state_changed(self, *_):
        """Handle bluetooth state change."""
        self._update_tile_state()

    def _on_device_connection_changed(self, *_):
        """Handle device connection/disconnection changes."""
        self._update_tile_icon()


