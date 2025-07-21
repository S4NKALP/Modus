import subprocess

from fabric.bluetooth import BluetoothClient, BluetoothDevice
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GLib, Gtk

import utils.icons as icons


class BluetoothDeviceSlot(CenterBox):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(name="bluetooth-device", **kwargs)
        self.device = device
        self.device.connect("changed", self.on_changed)
        self.device.connect(
            "notify::closed", lambda *_: self.device.closed and self.destroy()
        )

        self.connection_label = Label(
            markup=icons.bluetooth_disconnected, style="font-size: 22px;"
        )
        self.connect_button = Button(
            label="Connect",
            on_clicked=lambda *_: self._handle_device_action(),
        )

        # Create device name label that we can update
        self.device_name_label = Label(
            label=device.alias or device.name,
            h_expand=True,
            h_align="start",
            ellipsization="end",
        )

        self.start_children = [
            Box(
                spacing=10,
                h_expand=True,
                h_align="fill",
                children=[
                    Image(icon_name=device.icon_name + "-symbolic", size=16),
                    self.device_name_label,
                    self.connection_label,
                ],
            )
        ]
        self.end_children = self.connect_button

        self.device.emit("changed")

    def _handle_device_action(self):
        """Handle connect/disconnect button click"""
        if self.device.connected:
            # Disconnect
            self.device.connected = False
        elif self.device.paired:
            # Connect to already paired device
            self.device.connected = True
        else:
            # Pair new device using bluetoothctl
            self._pair_device_with_bluetoothctl()

    def _pair_device_with_bluetoothctl(self):
        """Pair device using bluetoothctl command"""
        try:
            device_name = self.device.alias or self.device.name
            device_address = self.device.address

            # Show pairing notification
            subprocess.run(
                [
                    "notify-send",
                    "Bluetooth Pairing",
                    f"Attempting to pair with {device_name}...",
                    "--icon=bluetooth",
                    "--urgency=normal",
                    "--app-name=Bluetooth",
                ],
                check=False,
            )

            # Use bluetoothctl to pair the device
            # This will trigger the system's pairing agent which should show the pairing dialog
            pairing_process = subprocess.Popen(
                ["bluetoothctl", "pair", device_address],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Monitor the pairing process in a separate thread
            GLib.timeout_add(
                100, self._monitor_pairing_process, pairing_process, device_name
            )

        except Exception as e:
            print(f"Failed to start pairing process: {e}")
            self._show_pairing_failed_notification()

    def _monitor_pairing_process(self, process, device_name):
        """Monitor the bluetoothctl pairing process"""
        if process.poll() is None:
            # Process still running
            return True

        # Process finished, check result
        stdout, stderr = process.communicate()
        return_code = process.returncode

        if return_code == 0 and "Pairing successful" in stdout:
            self._show_pairing_success_notification()
            # Auto-trust and connect the device after successful pairing
            self._trust_and_connect_device()
        else:
            self._show_pairing_failed_notification()

        return False  # Stop monitoring

    def _trust_and_connect_device(self):
        """Trust and connect to the device after successful pairing"""
        try:
            device_address = self.device.address

            # Trust the device
            subprocess.run(["bluetoothctl", "trust", device_address], check=False)

            # Connect to the device
            GLib.timeout_add(1000, lambda: setattr(self.device, "connected", True))

        except Exception as e:
            print(f"Failed to trust/connect device: {e}")

    def _show_pairing_success_notification(self):
        """Show notification when pairing succeeds"""
        try:
            device_name = self.device.alias or self.device.name
            subprocess.run(
                [
                    "notify-send",
                    "Bluetooth Paired",
                    f"Successfully paired with {device_name}",
                    "--icon=bluetooth",
                    "--urgency=normal",
                    "--app-name=Bluetooth",
                ],
                check=False,
            )
        except Exception as e:
            print(f"Failed to send pairing success notification: {e}")

    def _show_pairing_failed_notification(self):
        """Show notification when pairing fails"""
        try:
            device_name = self.device.alias or self.device.name
            subprocess.run(
                [
                    "notify-send",
                    "Bluetooth Pairing Failed",
                    f"Failed to pair with {device_name}",
                    "--icon=bluetooth-disabled",
                    "--urgency=normal",
                    "--app-name=Bluetooth",
                ],
                check=False,
            )
        except Exception as e:
            print(f"Failed to send pairing failed notification: {e}")

    def on_changed(self, *_):
        # Update connection icon
        self.connection_label.set_markup(
            icons.bluetooth_connected
            if self.device.connected
            else icons.bluetooth_disconnected
        )

        # Check for pairing state changes and show notifications
        base_name = self.device.alias or self.device.name

        # Track pairing success/failure
        if hasattr(self, "_was_pairing") and self._was_pairing:
            if self.device.paired and not self.device.connecting:
                # Pairing succeeded
                self._show_pairing_success_notification()
                self._was_pairing = False
            elif not self.device.connecting and not self.device.paired:
                # Pairing failed
                self._show_pairing_failed_notification()
                self._was_pairing = False

        # Update device name with status
        if self.device.connecting:
            if self.device.paired:
                status_text = f"{base_name}\nConnecting..."
                self.connect_button.set_label("Connecting...")
            else:
                status_text = f"{base_name}\nPairing..."
                self.connect_button.set_label("Pairing...")
                self._was_pairing = True  # Track that we're pairing
        elif self.device.connected:
            battery_info = ""
            if self.device.battery_percentage > 0:
                battery_info = f" • {self.device.battery_percentage:.0f}%"
            status_text = f"{base_name}\nConnected{battery_info}"
            self.connect_button.set_label("Disconnect")
        else:
            status_text = base_name
            if self.device.paired:
                self.connect_button.set_label("Connect")
            else:
                self.connect_button.set_label("Pair")

        self.device_name_label.set_label(status_text)


class BluetoothTab:
    """Bluetooth device management tab for settings"""

    def __init__(self):
        self.bluetooth_client = BluetoothClient(on_device_added=self.on_device_added)
        self.device_widgets = {}
        self.window_size_enforcer = None

        # Connect to bluetooth client signals
        self.bluetooth_client.connect("notify::enabled", self._on_bluetooth_changed)
        self.bluetooth_client.connect("notify::scanning", self._update_scan_button)
        self.bluetooth_client.connect("device-removed", self.on_device_removed)

    def set_window_size_enforcer(self, enforcer_func):
        """Set the window size enforcer function from the main GUI"""
        self.window_size_enforcer = enforcer_func

    def create_bluetooth_tab(self):
        """Create the Bluetooth tab content"""
        main_vbox = Box(orientation="v", spacing=0, style="padding: 0; margin: 15px;")

        # Set fixed size for the main container to match tab stack dimensions
        main_vbox.set_size_request(580, 580)

        # Create widgets first
        self.bluetooth_subtitle = Label(
            markup="<span>Find and connect to Bluetooth devices</span>", h_align="start"
        )
        self.bluetooth_switch = Gtk.Switch()
        self.scan_icon = Label(
            name="bluetooth-tab-icon", markup=icons.radar, style="font-size: 18px;"
        )
        self.scan_button = Button(
            name="bluetooth-scan",
            child=self.scan_icon,
            tooltip_text="Scan for devices",
            on_clicked=lambda *_: self.bluetooth_client.toggle_scan(),
            style="margin:10px;",
        )

        # Header section with title and controls
        header_box = CenterBox(
            name="bluetooth-header",
            style="margin-bottom: 16px;",
            start_children=[
                Box(
                    orientation="v",
                    spacing=4,
                    children=[
                        Label(
                            markup="<span size='large'><b>Bluetooth</b></span>",
                            h_align="start",
                        ),
                        self.bluetooth_subtitle,
                    ],
                )
            ],
            end_children=[
                Box(
                    orientation="h",
                    spacing=8,
                    children=[
                        self.bluetooth_switch,
                        self.scan_button,
                    ],
                )
            ],
        )

        # Set up switch
        self.bluetooth_switch.set_valign(Gtk.Align.CENTER)
        self.bluetooth_switch.connect(
            "notify::active", self._on_bluetooth_switch_toggled
        )

        main_vbox.add(header_box)

        # Device containers with size constraints
        self.paired_box = Box(spacing=20, orientation="v")
        self.paired_box.set_size_request(560, -1)
        self.available_box = Box(spacing=20, orientation="v")
        self.available_box.set_size_request(560, -1)

        content_box = Box(
            spacing=8,
            orientation="v",
            children=[
                Label(
                    name="bluetooth-section",
                    markup="<b>Paired Devices</b>",
                    h_align="start",
                ),
                self.paired_box,
                Label(
                    name="bluetooth-section",
                    markup="<b>Available Devices</b>",
                    h_align="start",
                ),
                self.available_box,
            ],
        )
        # Set size constraints for content box
        content_box.set_size_request(560, -1)

        # Devices list in scrolled window
        devices_scrolled = ScrolledWindow(
            name="bluetooth-devices",
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=False,
            v_expand=False,
            propagate_width=False,
            propagate_height=False,
            child=content_box,
        )

        # Set fixed size to prevent dynamic resizing
        devices_scrolled.set_size_request(580, 500)
        main_vbox.add(devices_scrolled)

        # Initialize bluetooth status and populate existing devices
        self._update_bluetooth_status()
        self._populate_existing_devices()
        self.bluetooth_client.notify("enabled")
        self.bluetooth_client.notify("scanning")

        return main_vbox

    def _update_bluetooth_status(self):
        """Update Bluetooth status display"""
        if self.bluetooth_client.enabled:
            self.bluetooth_switch.set_active(True)
            self.bluetooth_subtitle.set_markup(
                "<span>Find and connect to Bluetooth devices</span>"
            )
            self.scan_button.set_sensitive(True)
        else:
            self.bluetooth_switch.set_active(False)
            self.bluetooth_subtitle.set_markup("<span>Bluetooth is turned off</span>")
            self.scan_button.set_sensitive(False)

    def _on_bluetooth_changed(self, *args):
        """Handle bluetooth state changes"""
        GLib.idle_add(self._update_bluetooth_status)
        GLib.idle_add(self._refresh_all_devices)

    def _update_scan_button(self, *args):
        """Update scan button appearance"""
        if self.bluetooth_client.scanning:
            self.scan_icon.set_markup(icons.loader)
            self.scan_icon.add_style_class("scanning")
            self.scan_button.add_style_class("scanning")
            self.scan_button.set_tooltip_text("Stop scanning for Bluetooth devices")
        else:
            self.scan_icon.set_markup(icons.radar)
            self.scan_icon.remove_style_class("scanning")
            self.scan_button.remove_style_class("scanning")
            self.scan_button.set_tooltip_text("Scan for Bluetooth devices")

    def _populate_existing_devices(self):
        """Populate existing devices when tab is created"""
        if not self.bluetooth_client or not self.bluetooth_client.enabled:
            return

        devices = self.bluetooth_client.devices

        for device in devices:
            self.on_device_added(self.bluetooth_client, device.address)

    def on_device_added(self, client: BluetoothClient, address: str):
        """Handle device added"""
        # Check if device already exists to prevent duplicates
        if address in self.device_widgets:
            return

        if not (device := client.get_device(address)):
            return

        slot = BluetoothDeviceSlot(device)

        # Store the slot in device_widgets to track it
        self.device_widgets[address] = slot

        if device.paired or device.trusted:
            self.paired_box.add(slot)
        else:
            self.available_box.add(slot)

        # Enforce window size after adding device
        if self.window_size_enforcer:
            GLib.idle_add(self.window_size_enforcer)

    def on_device_removed(self, client: BluetoothClient, address: str):
        """Handle device removed"""
        if address in self.device_widgets:
            slot = self.device_widgets[address]
            # Remove from UI
            parent = slot.get_parent()
            if parent:
                parent.remove(slot)
            # Remove from tracking
            del self.device_widgets[address]

            # Enforce window size after removing device
            if self.window_size_enforcer:
                GLib.idle_add(self.window_size_enforcer)

    def _on_bluetooth_switch_toggled(self, switch, gparam):
        """Handle Bluetooth switch toggle"""
        is_active = switch.get_active()
        self.bluetooth_client.enabled = is_active

        # Refresh devices when bluetooth is toggled
        if is_active:
            GLib.timeout_add(1000, self._populate_existing_devices)
        else:
            self._clear_all_devices()

    def _clear_all_devices(self):
        """Clear all device widgets"""
        for child in self.paired_box.get_children():
            self.paired_box.remove(child)
        for child in self.available_box.get_children():
            self.available_box.remove(child)
        self.device_widgets.clear()

    def _refresh_all_devices(self):
        """Clear and repopulate all devices"""
        self._clear_all_devices()
        self._populate_existing_devices()
