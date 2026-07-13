from enum import Enum, auto

from fabric.utils import Gdk, GLib, Gtk, exec_shell_command, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.separator import Separator

from services.bluetooth import BluetoothClient, BluetoothDevice
from shared.widgets.smooth_switch import SmoothSwitch
from shared.window.animated_scrollwindow import AnimatedScrollable
from utils.functions import spawn_detached
from utils.utils import svg_file


def get_battery_icon_file(
    percentage: int, is_charging: bool, icon_path: str = ""
) -> str:
    """
    Get the battery icon file path based on percentage and charging status.

    Args:
        percentage: Battery percentage (0-100)
        is_charging: Whether the device is charging
        icon_path: Base path for icons (unused, kept for compatibility)

    Returns:
        Relative path to the battery icon file
    """
    clamped = max(0, min(100, percentage))
    step = int((clamped // 10) * 10)
    filename = f"battery-{step:03d}{'-charging' if is_charging else ''}.svg"
    return f"battery/{filename}"


def set_bluetooth_enabled_with_fallback(client, enabled: bool):
    if enabled:
        command = "rfkill unblock bluetooth"
    else:
        command = "rfkill block bluetooth"

    result = exec_shell_command(command)
    if result is False:
        logger.error(f"rfkill fallback failed: command '{command}' returned False")
    elif isinstance(result, str) and result.strip():
        logger.warning(f"rfkill command output: {result.strip()}")

    try:
        if hasattr(client, "set_enabled"):
            client.set_enabled(enabled)
        else:
            client.enabled = enabled
    except Exception as e:
        logger.warning(f"Bluetooth set_enabled({enabled}) failed: {e}")


class BTState(Enum):
    IDLE = auto()
    CONNECTED = auto()
    CONNECTING = auto()
    FAILED = auto()


class BluetoothDeviceSlot(Box):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(h_expand=True, name="device-button", **kwargs)
        self.device = device
        self._destroyed = False
        self._state = BTState.IDLE
        self._signal_ids = []
        self._signal_ids.append(self.device.connect("changed", self.on_changed))
        self._signal_ids.append(
            self.device.connect(
                "notify::closed",
                lambda *_: getattr(self.device, "closed", False) and self.destroy(),
            )
        )

        self.styles = [
            "connected" if self.device.connected else "",
            "paired" if self.device.paired else "",
        ]

        self.dimage = Image(
            icon_name=self._get_icon_for_device(self.device),
            size=5,
            name="device-icon",
            style_classes=" ".join(self.styles),
        )

        self.status_icon = Image(
            icon_name="process-working-symbolic",
            size=5,
            name="device-icon",
        )
        self.status_icon.set_visible(False)

        self.battery_icon = None
        self.battery_label = None
        if hasattr(device, "battery_percentage") and device.battery_percentage > 0:
            self.battery_icon = svg_file(
                get_battery_icon_file(
                    device.battery_percentage,
                    False,
                ),
                size=24,
            )
            self.battery_label = Label(
                label=f"{device.battery_percentage:.0f}%", name="battery-label"
            )

        button_children = [
            self.dimage,
            Label(label=device.name),
            Box(h_expand=True),  # Spacer
            self.status_icon,
        ]
        if self.battery_icon and self.battery_label:
            button_children.insert(-1, self.battery_icon)
            button_children.insert(-1, self.battery_label)

        self.device_button = Button(
            on_clicked=lambda *_: self.toggle_connecting(),
            h_expand=True,
            h_align="fill",
            child=Box(
                orientation="h",
                h_expand=True,
                spacing=8,
                children=button_children,
            ),
        )
        self.children = [self.device_button]

        self.device_button.connect("enter-notify-event", self.on_button_enter)
        self.device_button.connect("leave-notify-event", self.on_button_leave)
        # Right-click for pair / trust / remove actions
        self.device_button.connect("button-press-event", self._on_button_press)

        self._refresh_state()
        self.device.emit("changed")

    def _get_icon_for_device(self, device) -> str:
        return getattr(device, "type", None) or getattr(
            device, "icon_name", "bluetooth"
        )

    def destroy(self):
        """Clean up device signal connections to prevent memory leaks."""
        if self._destroyed:
            return
        self._destroyed = True
        for sig_id in self._signal_ids:
            try:
                self.device.disconnect(sig_id)
            except Exception as e:
                logger.error(f"[Bluetooth] Failed to disconnect signal {sig_id}: {e}")
        self._signal_ids.clear()
        self.device = None
        super().destroy()

    def on_button_enter(self, widget, event):
        self.add_style_class("button-hovered")

    def on_button_leave(self, widget, event):
        self.remove_style_class("button-hovered")

    def toggle_connecting(self):
        if self._destroyed:
            return
        if self._state == BTState.CONNECTED:
            self.device.connecting = False
            self._set_state(BTState.IDLE)
        elif self._state != BTState.CONNECTING:
            self._set_state(BTState.CONNECTING)
            self.device.connecting = True
        self.device.emit("changed")

    def on_changed(self, *_):
        if self._destroyed or self.device is None:
            return

        if getattr(self.device, "connected", False):
            self._set_state(BTState.CONNECTED)
        elif self._state == BTState.CONNECTING:
            self._set_state(BTState.FAILED)
        else:
            self._set_state(BTState.IDLE)

        try:
            new_styles = [
                "connected" if getattr(self.device, "connected", False) else "",
                "paired" if getattr(self.device, "paired", False) else "",
            ]
            self.styles = new_styles
            self.dimage.set_property("style-classes", " ".join(self.styles))
        except Exception as e:
            logger.error(
                f"[Bluetooth] Failed to update styles for {self.device.name}: {e}"
            )

        if (
            hasattr(self.device, "battery_percentage")
            and self.device.battery_percentage > 0
        ):
            if self.battery_icon and self.battery_label:
                self.battery_icon.set_visible(True)
                self.battery_label.set_visible(True)
                self.battery_icon.dynamic_file(
                    get_battery_icon_file(
                        self.device.battery_percentage,
                        False,
                    )
                )
                self.battery_label.set_label(f"{self.device.battery_percentage:.0f}%")
            else:
                self.battery_icon = svg_file(
                    get_battery_icon_file(
                        self.device.battery_percentage,
                        False,
                    ),
                    size=12,
                )
                self.battery_label = Label(
                    label=f"{self.device.battery_percentage:.0f}%",
                    name="battery-label",
                )
                btn_box = self.device_button.get_child()
                if btn_box:
                    btn_box.children = [
                        *btn_box.children[:-1],
                        self.battery_icon,
                        self.battery_label,
                        btn_box.children[-1],
                    ]
        elif self.battery_icon or self.battery_label:
            if self.battery_icon:
                self.battery_icon.set_visible(False)
            if self.battery_label:
                self.battery_label.set_visible(False)

    def _refresh_state(self):
        self._set_state(
            BTState.CONNECTED
            if getattr(self.device, "connected", False)
            else BTState.IDLE
        )

    def _set_state(self, state: BTState):
        if self._destroyed:
            return
        self._state = state
        for cls in ["active", "connecting", "failed"]:
            self.remove_style_class(cls)

        if state == BTState.CONNECTED:
            self.add_style_class("active")
            self.status_icon.set_visible(False)
        elif state == BTState.CONNECTING:
            self.add_style_class("connecting")
            self.status_icon.set_visible(False)
        elif state == BTState.FAILED:
            self.add_style_class("failed")
            self.status_icon.set_visible(False)
            GLib.timeout_add(5000, self._reset_from_failed)
        else:
            self.status_icon.set_visible(False)

    def _reset_from_failed(self):
        if not self._destroyed:
            self._set_state(BTState.IDLE)
        return False

    def _on_button_press(self, widget, event):
        """Right-click opens a context menu with pair/trust/remove actions."""
        if self._destroyed or self.device is None:
            return False
        if event.button != 3:  # only right-click
            return False

        menu = Gtk.Menu()

        if not self.device.paired:
            item_pair = Gtk.MenuItem(label="Pair")
            item_pair.connect("activate", lambda *_: self.device.pair())
            menu.append(item_pair)
        else:
            if self.device.trusted:
                item_trust = Gtk.MenuItem(label="Untrust")
                item_trust.connect("activate", lambda *_: self.device.untrust())
            else:
                item_trust = Gtk.MenuItem(label="Trust")
                item_trust.connect("activate", lambda *_: self.device.trust())
            menu.append(item_trust)

            item_remove = Gtk.MenuItem(label="Remove / Forget")
            item_remove.connect(
                "activate",
                lambda *_: self._remove_device(),
            )
            menu.append(item_remove)

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _remove_device(self):
        """Ask the client to remove (unpair/forget) this device."""
        if self._destroyed or self.device is None:
            return
        try:
            # Walk up to find a BluetoothConnections parent that holds the client
            parent = self.get_parent()
            while parent is not None:
                if isinstance(parent, BluetoothConnections):
                    parent.client.remove_device(self.device)
                    return
                parent = parent.get_parent()
            # Fallback: use device.remove() which sets a flag
            self.device.remove()
        except Exception as e:
            logger.warning(f"[Bluetooth] Failed to remove device: {e}")


class BluetoothConnections(Box):
    def __init__(
        self, parent, show_hidden_devices: bool = False, show_back_button=True, **kwargs
    ):
        super().__init__(
            spacing=8,
            orientation="vertical",
            name="bluetooth-connections",
            **kwargs,
        )

        self.parent = parent
        self.show_hidden_devices = show_hidden_devices
        self.is_scanning = False  # Track scanning state
        self.refresh_timer = None  # Timer for periodic device refresh
        self._update_in_progress = False  # Prevent concurrent updates
        self._destroyed = False  # Track if widget is destroyed
        self._client_signal_ids = []  # Track BluetoothClient signal IDs

        self.client = BluetoothClient()

        # Create pull-to-refresh indicator
        self.refresh_indicator = Label(
            name="bluetooth-refresh-indicator",
            label="↓ Pull to scan for devices",
            h_align="center",
            visible=False,
            style="color: #fff; font-size: 12px; padding: 5px;",
        )

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

        self._switch_lock = False

        self.toggle_button = SmoothSwitch(
            name="toggle-button",
            active=self.client.enabled,
            on_user_toggle=self.handle_user_toggle,
        )

        self._client_signal_ids.append(
            self.client.connect(
                "notify::enabled",
                lambda *_: self.toggle_button.set_active(self.client.enabled),
            )
        )
        self._client_signal_ids.append(
            self.client.connect("notify::scanning", lambda *_: self.update_scan_label())
        )

        self._client_signal_ids.append(
            self.client.connect("device-added", self.update_devices)
        )
        self._client_signal_ids.append(
            self.client.connect("device-removed", self.update_devices)
        )
        self._client_signal_ids.append(
            self.client.connect("notify::connected-devices", self.update_devices)
        )

        self._client_signal_ids.append(
            self.client.connect("changed", self.on_client_changed)
        )

        # Create Devices section
        self.paired_devices_label = Label(
            label="Devices", h_align="start", name="networks-title"
        )
        self.paired_devices = Box(
            spacing=4, orientation="vertical", name="known-networks"
        )
        self.paired_devices_scrolled = AnimatedScrollable(
            min_content_size=(303, 0),
            max_content_size=(303, 200),
            child=self.paired_devices,
            overlay_scroll=True,
            animate=False,
        )

        self.no_devices_label = Label(
            label="No devices available",
            h_align="center",
            name="no-networks-label",
            visible=False,
        )

        self.other_devices_button = Button(
            child=CenterBox(
                start_children=Label("Other Devices", h_align="start"),
                end_children=self.refresh_indicator,
            ),
            name="wifi-other-button",
            on_clicked=self.toggle_other_devices,
        )
        self.other_devices = Box(spacing=4, orientation="vertical")

        self.other_devices_scrolled = AnimatedScrollable(
            min_content_size=(303, 0),
            max_content_size=(303, 300),
            child=self.other_devices,
            overlay_scroll=True,
            animate=False,
        )
        self.other_devices.set_visible(False)

        # Add pull-to-refresh functionality to scrolled window
        self.setup_pull_to_refresh()

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
            Separator(orientation="h", name="separator"),
            self.paired_devices_label,
            self.paired_devices_scrolled,
            self.no_devices_label,
            Separator(orientation="h", name="separator"),
            self.other_devices_button,
            self.other_devices_scrolled,
            Separator(orientation="h", name="separator"),
            self.more_settings_button,
        ]

        self.connect("destroy", self.on_destroy)
        self.connect("unmap", self.on_hide)
        self.connect("map", lambda *_: self.start_device_monitoring())

        self.client.notify("scanning")
        self.client.notify("enabled")
        self.update_devices()

    def handle_user_toggle(self, active: bool):
        self._switch_lock = True
        set_bluetooth_enabled_with_fallback(self.client, active)
        GLib.timeout_add(1500, self._unlock_switch)

    def _unlock_switch(self):
        self._switch_lock = False
        if not self._destroyed and getattr(self, "toggle_button", None):
            self.toggle_button.set_active(self.client.enabled)
        return False

    def on_hide(self, *_):
        """Called when the widget is hidden (popup closed)"""
        self.stop_device_monitoring()
        self._cancel_pending_refresh()
        if self.other_devices.get_visible():
            self.other_devices.set_visible(False)
            self.other_devices_scrolled.snap_to_size(0)
            if (
                self.client
                and self.client.scanning
                and hasattr(self.client, "stop_scan")
            ):
                self.client.stop_scan()

        self.update_scan_label()

    def toggle_other_devices(self, *_):
        """Toggle the visibility of other devices section"""
        current_state = self.other_devices.get_visible()
        self._cancel_pending_refresh()
        if current_state:
            self.other_devices.set_visible(False)
            self.other_devices_scrolled.snap_to_size(0)
            self.update_scan_label()
            if (
                self.client
                and self.client.scanning
                and hasattr(self.client, "stop_scan")
            ):
                self.client.stop_scan()
        else:
            self.other_devices.set_visible(True)
            self.update_scan_label()
            if (
                self.client
                and not self.client.scanning
                and hasattr(self.client, "scan")
            ):
                self.client.scan()
            # Defer refresh until after the height animation completes
            GLib.idle_add(self._refresh_after_animation)

    def _cancel_pending_refresh(self):
        if hasattr(self, "_anim_finished_handler") and self._anim_finished_handler:
            try:
                self.other_devices_scrolled.height_animator.disconnect(
                    self._anim_finished_handler
                )
            except Exception:
                pass
            self._anim_finished_handler = None

    def _refresh_after_animation(self):
        if self._destroyed:
            return False
        anim = self.other_devices_scrolled.height_animator
        if anim.playing:
            self._anim_finished_handler = anim.connect(
                "finished",
                lambda *_: self.force_device_refresh() if not self._destroyed else None,
            )
        else:
            self.force_device_refresh()
        return False

    def open_bluetooth_settings(self, *_):
        """Open Blueman bluetooth manager"""
        try:
            spawn_detached(["blueman-manager"])
            if self.parent and hasattr(self.parent, "hide_controlcenter"):
                self.parent.hide_controlcenter()
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"[Bluetooth] Failed to open bluetooth settings: {e}")

    def update_scan_label(self):
        """Update scanning state appearance"""
        if self.client and self.client.scanning and self.other_devices.get_visible():
            self.refresh_indicator.set_label("Scanning for devices...")
            self.refresh_indicator.set_visible(True)
            self.refresh_indicator.add_style_class("scanning")
        else:
            self.refresh_indicator.set_visible(False)
            self.refresh_indicator.remove_style_class("scanning")

    def update_devices(self, *_):
        """Update the list of available devices"""
        if self._update_in_progress or self._destroyed or not self.client:
            return

        self._update_in_progress = True

        try:
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

            devices = self.client.devices
            paired_devices = []
            other_devices = []
            new_paired_addresses = set()
            new_other_addresses = set()

            for device in devices:
                try:
                    if device.name and device.name != "Unknown":
                        if device.paired:
                            paired_devices.append(device)
                            new_paired_addresses.add(device.address)
                        else:
                            other_devices.append(device)
                            new_other_addresses.add(device.address)
                except Exception as e:
                    logger.warning(
                        f"[Bluetooth] Failed to process device {device}: {e}"
                    )
                    continue

            paired_changed = current_paired_addresses != new_paired_addresses
            other_changed = current_other_addresses != new_other_addresses

            if paired_changed or other_changed:
                existing_paired = {
                    child.device.address: child
                    for child in self.paired_devices.get_children()
                    if hasattr(child, "device")
                }
                existing_other = {
                    child.device.address: child
                    for child in self.other_devices.get_children()
                    if hasattr(child, "device")
                }

                for device in paired_devices:
                    if not self._destroyed:
                        if device.address in existing_paired:
                            slot = existing_paired.pop(device.address)
                            # update existing
                            slot.device = device
                        elif device.address in existing_other:
                            slot = existing_other.pop(device.address)
                            slot.device = device
                            self.other_devices.remove(slot)
                            self.paired_devices.add(slot)
                        else:
                            device_slot = BluetoothDeviceSlot(device)
                            self.paired_devices.add(device_slot)

                for device in other_devices:
                    if not self._destroyed:
                        if device.address in existing_other:
                            slot = existing_other.pop(device.address)
                            slot.device = device
                        elif device.address in existing_paired:
                            slot = existing_paired.pop(device.address)
                            slot.device = device
                            self.paired_devices.remove(slot)
                            self.other_devices.add(slot)
                        else:
                            device_slot = BluetoothDeviceSlot(device)
                            self.other_devices.add(device_slot)

            if not self._destroyed:
                has_paired_devices = len(paired_devices) > 0
                has_other_devices = len(other_devices) > 0
                has_any_devices = has_paired_devices or has_other_devices

                self.paired_devices_scrolled.set_visible(True)
                self.no_devices_label.set_visible(not has_any_devices)
                self.other_devices_button.set_visible(True)  # Always visible

        except Exception as e:
            logger.error(f"[Bluetooth] Error during update_devices: {e}")
        finally:
            self._update_in_progress = False

    def start_device_monitoring(self):
        """Start periodic monitoring for device changes"""
        self.stop_device_monitoring()
        self.refresh_timer = GLib.timeout_add_seconds(5, self.periodic_device_refresh)

    def stop_device_monitoring(self):
        """Stop periodic monitoring"""
        if self.refresh_timer:
            GLib.source_remove(self.refresh_timer)
            self.refresh_timer = None

    def periodic_device_refresh(self):
        """Periodically refresh device list to catch external connections"""
        if self._destroyed:
            self.refresh_timer = None
            return False

        # Skip if update in progress or client not available/enabled
        if self._update_in_progress or not self.client or not self.client.enabled:
            return True  # Continue monitoring

        try:
            self.update_devices()
        except Exception as e:
            logger.error(f"[Bluetooth] Error during periodic refresh: {e}")

        return True

    def force_device_refresh(self):
        """Force an immediate refresh of the device list"""
        if self._update_in_progress or self._destroyed:
            return

        try:
            self.update_devices()
        except Exception as e:
            logger.error(f"[Bluetooth] Error during forced device refresh: {e}")

    def on_client_changed(self, *_):
        """Handle when the bluetooth client state changes"""
        if getattr(self, "toggle_button", None) and not self._switch_lock:
            self.toggle_button.set_active(self.client.enabled)

        self.update_scan_label()
        self.update_devices()

    def on_destroy(self, widget):
        """Cleanup when widget is destroyed"""
        self._destroyed = True
        self.stop_device_monitoring()
        self._cancel_pending_refresh()
        for sig_id in self._client_signal_ids:
            try:
                self.client.disconnect(sig_id)
            except Exception as e:
                logger.error(
                    f"[Bluetooth] Failed to disconnect client signal {sig_id}: {e}"
                )
        self._client_signal_ids.clear()

    def close_bluetooth(self):
        """Called when Bluetooth panel is being closed"""
        if self.other_devices.get_visible():
            self.other_devices.set_visible(False)
            self.other_devices_scrolled.snap_to_size(0)

    def setup_pull_to_refresh(self):
        """Setup pull-to-refresh gesture for the scrolled window"""
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
        if self.vadjustment.get_value() <= 0:
            if event.direction == Gdk.ScrollDirection.UP:
                if not self.client.scanning and hasattr(self.client, "scan"):
                    self.client.scan()
                self.force_device_refresh()
                return True
        return False

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
                if not self.client.scanning and hasattr(self.client, "scan"):
                    self.client.scan()
                self.force_device_refresh()
            self.refresh_indicator.set_visible(False)
            self.refresh_indicator.remove_style_class("ready-to-refresh")
            self.is_pulling = False
        return False

    def on_motion_notify(self, widget, event):
        """Handle motion events for visual feedback during pull"""
        if self.is_pulling and self.vadjustment.get_value() <= 0:
            pull_distance = event.y - self.pull_start_y
            if pull_distance > 0:
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
        self.update_devices()
