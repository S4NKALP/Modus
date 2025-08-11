import subprocess

import gi
from fabric.bluetooth import BluetoothClient, BluetoothDevice
from fabric.utils import get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.separator import Separator
from fabric.widgets.svg import Svg
from gi.repository import Gdk, Gtk, GLib
from services.battery import Battery

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")


class BluetoothDeviceSlot(CenterBox):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(h_expand=True, name="device-button", **kwargs)
        self.device = device
        self.device.connect("changed", self.on_changed)
        self.device.connect(
            "notify::closed", lambda *_: self.device.closed and self.destroy()
        )

        self.styles = [
            "connected" if self.device.connected else "",
            "paired" if self.device.paired else "",
        ]

        self.dimage = Image(
            icon_name=device.icon_name + "-symbolic",  # type: ignore
            size=5,
            name="device-icon",
            style_classes=" ".join(self.styles),
        )

        self.start_children = [
            Button(
                on_clicked=lambda *_: self.toggle_connecting(),
                child=Box(
                    orientation="h",
                    h_expand=True,
                    children=[self.dimage, Label(label=device.name)],
                ),  # type: ignore
            ),
        ]

        # Add battery info if available
        if hasattr(device, "battery_percentage") and device.battery_percentage > 0:
            battery_box = Box(orientation="h", spacing=4)

            # Create battery icon
            battery_icon = Svg(
                size=16,
                svg_file=get_relative_path(
                    Battery.get_battery_icon_file(
                        device.battery_percentage,
                        False,  # Not charging for bluetooth devices
                        "../../config/assets/icons/",
                    )
                ),
                name="battery-icon",
            )

            # Create battery percentage label
            battery_label = Label(
                label=f"{device.battery_percentage:.0f}%", name="battery-label"
            )

            battery_box.children = [battery_icon, battery_label]
            self.end_children = [battery_box]

        self.device.emit("changed")  # to update display status

    def toggle_connecting(self):
        self.device.emit("changed")
        self.device.set_connecting(not self.device.connected)

    def on_changed(self, *_):
        try:
            # Update connection and pairing status
            new_styles = [
                "connected" if self.device.connected else "",
                "paired" if self.device.paired else "",
            ]

            self.styles = new_styles
            self.dimage.set_property("style-classes", " ".join(self.styles))
        except Exception:
            return

        # Update battery info if available
        if (
            hasattr(self.device, "battery_percentage")
            and self.device.battery_percentage > 0
        ):
            if not self.end_children:  # Add battery display if not already present
                battery_box = Box(orientation="h", spacing=4)

                # Create battery icon
                battery_icon = Svg(
                    size=16,
                    svg_file=get_relative_path(
                        Battery.get_battery_icon_file(
                            self.device.battery_percentage,
                            False,  # Not charging for bluetooth devices
                            "../../config/assets/icons/",
                        )
                    ),
                    name="battery-icon",
                )

                # Create battery percentage label
                battery_label = Label(
                    label=f"{self.device.battery_percentage:.0f}%", name="battery-label"
                )

                battery_box.children = [battery_icon, battery_label]
                self.end_children = [battery_box]
            else:  # Update existing battery display
                battery_box = self.end_children[0]
                if hasattr(battery_box, "children") and len(battery_box.children) >= 2:
                    battery_icon = battery_box.children[0]
                    battery_label = battery_box.children[1]

                    # Update battery icon
                    battery_icon.set_from_file(
                        get_relative_path(
                            Battery.get_battery_icon_file(
                                self.device.battery_percentage,
                                False,  # Not charging for bluetooth devices
                                "../../config/assets/icons/",
                            )
                        )
                    )

                    # Update battery percentage
                    battery_label.set_label(f"{self.device.battery_percentage:.0f}%")
        elif self.end_children:  # Remove battery display if no longer available
            self.end_children = []

        return


class BluetoothConnections(Box):
    def __init__(
        self, parent, show_hidden_devices: bool = False, show_back_button=True, **kwargs
    ):
        super().__init__(
            spacing=8,
            orientation="vertical",
            style="margin: 8px",
            name="bluetooth-connections",
            **kwargs,
        )

        self.parent = parent
        self.show_hidden_devices = show_hidden_devices
        self.is_scanning = False  # Track scanning state
        self.refresh_timer = None  # Timer for periodic device refresh
        self._update_in_progress = False  # Prevent concurrent updates
        self._destroyed = False  # Track if widget is destroyed

        self.client = BluetoothClient(on_device_added=self.on_device_added)

        # Create pull-to-refresh indicator
        self.refresh_indicator = Label(
            name="bluetooth-refresh-indicator",
            label="↓ Pull to scan for devices",
            h_align="center",
            visible=False,
            style="color: #fff; font-size: 12px; padding: 5px;",
        )

        # Create title with optional back button
        title_children = []
        if show_back_button:
            title_children.append(
                Button(
                    image=Image(icon_name="back", size=10),
                    on_clicked=lambda *_: self.parent.close_bluetooth(),
                )
            )
        title_children.append(Label("Bluetooth", name="bluetooth-title"))

        self.title = Box(
            orientation="h",
            children=title_children,
        )

        self.toggle_button = Gtk.Switch(visible=True, name="toggle-button")

        # Safely set initial state
        self.toggle_button.set_active(self.client.enabled)
        self.toggle_button.connect(
            "notify::active",
            lambda *_: self.client.set_enabled(self.toggle_button.get_active()),
        )

        # Connect client signals
        self.client.connect(
            "notify::enabled",
            lambda *_: self.toggle_button.set_active(self.client.enabled),
        )
        self.client.connect("notify::scanning", lambda *_: self.update_scan_label())

        # Connect to device changes
        self.client.connect("device-added", self.update_devices)
        self.client.connect("device-removed", self.update_devices)

        # Connect to additional signals for better real-time monitoring
        self.client.connect("changed", self.on_client_changed)

        # Create Devices section
        self.paired_devices_label = Label(
            label="Devices", h_align="start", name="networks-title"
        )
        self.paired_devices = Box(
            spacing=4, orientation="vertical", name="known-networks"
        )

        # Create "No devices available" message
        self.no_devices_label = Label(
            label="No devices available",
            h_align="center",
            name="no-networks-label",
            visible=False,
        )

        # Create Other Devices section with clickable title
        self.other_devices_button = Button(
            child=Label("Other Devices", h_align="start"),
            name="wifi-other-button",
            on_clicked=self.toggle_other_devices,
        )
        self.other_devices = Box(spacing=4, orientation="vertical")

        # Create scrolled window for other devices
        self.other_devices_scrolled = ScrolledWindow(
            min_content_size=(303, 150),
            child=self.other_devices,
            overlay_scroll=True,
        )

        # Add pull-to-refresh functionality to scrolled window
        self.setup_pull_to_refresh()

        # Create revealer for Other Devices section
        self.other_devices_revealer = Revealer(
            child=self.other_devices_scrolled,
            transition_type="slide-down",
            transition_duration=100,
            child_revealed=False,
        )

        # Create More Settings button (same style as Other Devices button)
        self.more_settings_button = Button(
            child=Label("More Settings", h_align="start"),
            name="wifi-other-button",
            on_clicked=self.open_bluetooth_settings,
        )

        self.children = [
            CenterBox(
                start_children=self.title,
                end_children=self.toggle_button,
                name="bluetooth-widget-top",
            ),
            self.refresh_indicator,
            Separator(orientation="h", name="separator"),
            self.paired_devices_label,
            self.paired_devices,
            self.no_devices_label,
            Separator(orientation="h", name="separator"),
            self.other_devices_button,
            self.other_devices_revealer,
            Separator(orientation="h", name="separator"),
            self.more_settings_button,
        ]

        # Connect cleanup on destroy
        self.connect("destroy", self.on_destroy)

        self.client.notify("scanning")
        self.client.notify("enabled")

        # Initial device update
        self.update_devices()

        # Start periodic device monitoring for real-time updates
        self.start_device_monitoring()

    def toggle_other_devices(self, *_):
        """Toggle the visibility of other devices section"""
        current_state = self.other_devices_revealer.child_revealed
        self.other_devices_revealer.child_revealed = not current_state

        # Update button text based on state
        if self.other_devices_revealer.child_revealed:
            # Trigger a scan when revealing other devices and force refresh
            if self.client:
                self.client.toggle_scan()
                # Also force an immediate device refresh to catch any missed connections
                self.force_device_refresh()

    def open_bluetooth_settings(self, *_):
        """Open Blueman bluetooth manager"""
        try:
            subprocess.Popen(["blueman-manager"], start_new_session=True)
            if self.parent and hasattr(self.parent, "hide_controlcenter"):
                self.parent.hide_controlcenter()
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def update_scan_label(self):
        """Update scanning state appearance"""
        if self.client.scanning:
            # Show scanning feedback in refresh indicator
            self.refresh_indicator.set_label("Scanning for devices...")
            self.refresh_indicator.set_visible(True)
            self.refresh_indicator.add_style_class("scanning")
        else:
            # Hide scanning feedback
            self.refresh_indicator.set_visible(False)
            self.refresh_indicator.remove_style_class("scanning")

    def update_devices(self, *_):
        """Update the list of available devices"""
        # Prevent concurrent updates and check if destroyed
        if self._update_in_progress or self._destroyed or not self.client:
            return

        self._update_in_progress = True

        try:
            # Store current device addresses to detect changes
            current_paired_addresses = {
                child.device.address
                for child in self.paired_devices.get_children()
                if hasattr(child, "device")
            }
            current_other_addresses = {
                child.device.address
                for child in self.other_devices.get_children()
                if hasattr(child, "device")
            }

            # Get current devices safely
            devices = self.client.devices
            paired_devices = []
            other_devices = []
            new_paired_addresses = set()
            new_other_addresses = set()

            for device in devices:
                try:
                    if device.name and device.name != "Unknown":
                        # Categorize devices: paired devices go to "Devices (Paired)"
                        # All others go to "Other Devices"
                        if device.paired:
                            paired_devices.append(device)
                            new_paired_addresses.add(device.address)
                        else:
                            other_devices.append(device)
                            new_other_addresses.add(device.address)
                except Exception:
                    continue

            # Check if we need to update (devices added/removed)
            paired_changed = current_paired_addresses != new_paired_addresses
            other_changed = current_other_addresses != new_other_addresses

            # Only rebuild if something actually changed
            if paired_changed or other_changed:
                # Clear existing devices safely
                for child in list(self.paired_devices.get_children()):
                    if not self._destroyed:
                        child.destroy()
                for child in list(self.other_devices.get_children()):
                    if not self._destroyed:
                        child.destroy()

                # Add paired devices
                for device in paired_devices:
                    if not self._destroyed:
                        device_slot = BluetoothDeviceSlot(device)
                        self.paired_devices.add(device_slot)

                # Add other devices
                for device in other_devices:
                    if not self._destroyed:
                        device_slot = BluetoothDeviceSlot(device)
                        self.other_devices.add(device_slot)

            # Show/hide sections based on available devices
            if not self._destroyed:
                has_paired_devices = len(paired_devices) > 0
                has_other_devices = len(other_devices) > 0
                has_any_devices = has_paired_devices or has_other_devices

                # Show paired devices section only if there are paired devices
                self.paired_devices_label.set_visible(has_paired_devices)
                self.paired_devices.set_visible(has_paired_devices)

                # Show "No devices available" message if no devices at all
                self.no_devices_label.set_visible(not has_any_devices)

                # Always show the other devices button, regardless of available devices
                self.other_devices_button.set_visible(True)  # Always visible

        except Exception:
            pass
        finally:
            self._update_in_progress = False

    def start_device_monitoring(self):
        """Start periodic monitoring for device changes"""
        # Monitor for device changes every 5 seconds (less aggressive)
        # This helps catch devices that connect from external sources
        self.refresh_timer = GLib.timeout_add_seconds(5, self.periodic_device_refresh)

    def stop_device_monitoring(self):
        """Stop periodic monitoring"""
        if self.refresh_timer:
            GLib.source_remove(self.refresh_timer)
            self.refresh_timer = None

    def periodic_device_refresh(self):
        """Periodically refresh device list to catch external connections"""
        # Skip if update in progress, destroyed, or client not available
        if (
            self._update_in_progress
            or self._destroyed
            or not self.client
            or not self.client.enabled
        ):
            return True  # Continue monitoring

        try:
            # Simple check - just trigger update_devices which has its own safety checks
            # Don't force signal emissions as that can cause race conditions
            self.update_devices()

        except Exception:
            pass

        return True  # Continue monitoring

    def force_device_refresh(self):
        """Force an immediate refresh of the device list"""
        if self._update_in_progress or self._destroyed:
            return

        try:
            # Simply trigger update_devices which has its own safety checks
            # Avoid forcing signal emissions to prevent race conditions
            self.update_devices()
        except Exception:
            pass

    def on_client_changed(self, *_):
        """Handle when the bluetooth client state changes"""
        # Update devices when client state changes
        self.update_devices()

    def on_destroy(self, widget):
        """Cleanup when widget is destroyed"""
        # Mark as destroyed to prevent further updates
        self._destroyed = True
        # Stop monitoring
        self.stop_device_monitoring()
        # Make sure other devices revealer is collapsed when closing
        try:
            self.other_devices_revealer.child_revealed = False
        except:
            pass  # Widget might already be destroyed

    def close_bluetooth(self):
        """Called when Bluetooth panel is being closed"""
        # Collapse the other devices section when closing
        self.other_devices_revealer.child_revealed = False

    def setup_pull_to_refresh(self):
        """Setup pull-to-refresh gesture for the scrolled window"""
        # Get the scrolled window's vertical adjustment
        self.vadjustment = self.other_devices_scrolled.get_vadjustment()

        # Track gesture state
        self.pull_start_y = 0
        self.is_pulling = False
        self.pull_threshold = 50  # pixels to trigger refresh

        # Connect to scroll events
        self.other_devices_scrolled.connect("scroll-event", self.on_scroll_event)
        self.other_devices_scrolled.connect("button-press-event", self.on_button_press)
        self.other_devices_scrolled.connect(
            "button-release-event", self.on_button_release
        )
        self.other_devices_scrolled.connect(
            "motion-notify-event", self.on_motion_notify
        )

        # Enable events
        self.other_devices_scrolled.set_events(
            Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )

    def on_scroll_event(self, widget, event):
        """Handle scroll events for pull-to-refresh"""
        # Only handle pull-to-refresh when at the top
        if self.vadjustment.get_value() <= 0:
            if event.direction == Gdk.ScrollDirection.UP:
                # Scrolling up at the top - toggle scan and force refresh
                self.client.toggle_scan()
                self.force_device_refresh()
                return True  # Consume the event
        return False  # Let normal scrolling continue

    def on_button_press(self, widget, event):
        """Handle button press for touch/drag gestures"""
        if self.vadjustment.get_value() <= 0:
            self.pull_start_y = event.y
            self.is_pulling = True
        return False

    def on_button_release(self, widget, event):
        """Handle button release for touch/drag gestures"""
        if self.is_pulling:
            pull_distance = event.y - self.pull_start_y
            if pull_distance > self.pull_threshold:
                # Toggle scan and force refresh
                self.client.toggle_scan()
                self.force_device_refresh()
            # Hide refresh indicator
            self.refresh_indicator.set_visible(False)
            self.refresh_indicator.remove_style_class("ready-to-refresh")
            self.is_pulling = False
        return False

    def on_motion_notify(self, widget, event):
        """Handle motion events for visual feedback during pull"""
        if self.is_pulling and self.vadjustment.get_value() <= 0:
            pull_distance = event.y - self.pull_start_y
            if pull_distance > 0:
                # Show refresh indicator when pulling down
                self.refresh_indicator.set_visible(True)
                if pull_distance >= self.pull_threshold:
                    if self.client.scanning:
                        self.refresh_indicator.set_label("↑ Release to stop scanning")
                    else:
                        self.refresh_indicator.set_label("↑ Release to scan")
                    self.refresh_indicator.add_style_class("ready-to-refresh")
                else:
                    if self.client.scanning:
                        self.refresh_indicator.set_label("↓ Pull to stop scanning")
                    else:
                        self.refresh_indicator.set_label("↓ Pull to scan for devices")
                    self.refresh_indicator.remove_style_class("ready-to-refresh")
            else:
                self.refresh_indicator.set_visible(False)
        return False

    def on_device_added(self, client: BluetoothClient, address: str):
        """Handle when a new device is added"""
        # Update the device list when devices are added
        self.update_devices()
