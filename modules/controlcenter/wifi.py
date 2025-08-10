from widgets.wifi_password_dialog import WiFiPasswordDialog
from services.network import NetworkClient
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.revealer import Revealer
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.box import Box
from loguru import logger
from gi.repository import Gdk, GLib, Gtk
from fabric.widgets.separator import Separator
import gi
import subprocess

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")


class WifiNetworkSlot(CenterBox):
    def __init__(self, access_point, wifi_service, parent=None, **kwargs):
        super().__init__(name="wifi-network-slot", **kwargs)
        self.access_point = access_point
        self.wifi_service = wifi_service
        self.parent = parent  # Reference to control center

        # Get network info from AccessPoint object
        self.ssid = access_point.ssid
        self.bssid = access_point.bssid
        self.strength = access_point.strength
        self.icon_name = access_point.icon

        # Check if this network is currently connected
        self.is_connected = access_point.is_active

        # Initialize styles based on connection state
        self.styles = [
            "connected" if self.is_connected else "",
        ]

        # Create connection status indicator using symbolic WiFi icon
        self.dimage = Image(
            icon_name="network-wireless-symbolic",
            size=16,
            name="device-icon",
            style_classes=" ".join(self.styles),
        )

        self.network_label = Label(
            label=self.ssid, name="wifi-network-name", h_align="start", h_expand=True
        )

        # Create lock icon for secured networks
        self.lock_icon = None
        if self.access_point.requires_password:
            self.lock_icon = Image(
                icon_name="changes-prevent-symbolic",
                size=12,
                name="wifi-lock-icon",
            )

        # Initialize password dialog
        self.password_dialog = None

        # Create the start section with WiFi icon and network name
        start_box = Box(
            orientation="h", spacing=8, children=[self.dimage, self.network_label]
        )

        # Create end section with lock icon if needed
        end_children = []
        if self.lock_icon:
            end_children.append(self.lock_icon)

        self.start_children = [
            Button(
                child=start_box,
                name="wifi-network-button",
                on_clicked=lambda *_: self.toggle_connecting(),
            )
        ]

        if end_children:
            self.end_children = end_children

        # Emit initial change to update display
        self.on_changed()

    def toggle_connecting(self):
        # Check if this network is currently connected
        is_currently_connected = self.access_point.is_active

        if is_currently_connected:
            # Show disconnecting state
            self.dimage.set_property("icon-name", "network-wireless-acquiring-symbolic")
            self.dimage.add_style_class("disconnecting")

            # Disconnect from network
            self.wifi_service.disconnect_wifi()
            self.is_connected = False
            # Remove disconnecting state after a short delay to show feedback
            GLib.timeout_add(500, lambda: self._reset_disconnect_state())
        else:
            # Try to connect - check if password is required
            if self.access_point.requires_password:
                # Show password dialog immediately
                self._show_password_dialog()
            else:
                # Try to connect without password (for open networks)
                self.dimage.set_property(
                    "icon-name", "network-wireless-acquiring-symbolic"
                )
                self.dimage.add_style_class("connecting")

                def on_open_connection_result(success, message):
                    """Handle the connection result for open networks"""
                    if success:
                        self.is_connected = True
                        # Remove connecting state after a short delay
                        GLib.timeout_add(500, lambda: self._reset_connect_state())
                    else:
                        # Connection failed
                        self._reset_connect_state()

                    # Update display after connection attempt
                    self.on_changed()

                try:
                    self.wifi_service.connect_to_wifi(
                        self.access_point, callback=on_open_connection_result
                    )
                except Exception:
                    # Handle any connection errors gracefully
                    self._reset_connect_state()
                    self.on_changed()

        # Update display after connection attempt
        self.on_changed()

    def _reset_disconnect_state(self):
        """Reset visual state after disconnect operation"""
        self.dimage.remove_style_class("disconnecting")
        self.dimage.set_property("icon-name", "network-wireless-symbolic")
        self.on_changed()
        return False  # Remove timeout

    def _reset_connect_state(self):
        """Reset visual state after connect operation"""
        self.dimage.remove_style_class("connecting")
        self.dimage.set_property("icon-name", "network-wireless-symbolic")
        self.on_changed()
        return False  # Remove timeout

    def on_changed(self, *_):
        # Check if this network is currently connected using the access point's is_active property
        self.is_connected = self.access_point.is_active
        self.styles = [
            "connected" if self.is_connected else "",
        ]
        self.dimage.set_property("style-classes", " ".join(self.styles))
        return

    def _show_password_dialog(self):
        """Show the WiFi password dialog"""
        # Close the control center first
        if self.parent and hasattr(self.parent, "hide_controlcenter"):
            self.parent.hide_controlcenter()

        # Create a new dialog each time to ensure clean state
        if self.password_dialog:
            self.password_dialog.destroy_dialog()

        self.password_dialog = WiFiPasswordDialog(
            ssid=self.ssid,
            on_connect_callback=self._on_password_connect,
            on_cancel_callback=self._on_password_cancel,
        )

        self.password_dialog.show_dialog()

    def _on_password_connect(self, ssid, password):
        """Handle password dialog connect action"""
        if password.strip():
            # Show connecting state
            self.dimage.set_property("icon-name", "network-wireless-acquiring-symbolic")
            self.dimage.add_style_class("connecting")

            # Try to connect with password using callback
            def on_connection_result(success, message):
                """Handle the connection result"""
                if success:
                    self.is_connected = True
                    # Remove connecting state after a short delay
                    from gi.repository import GLib

                    GLib.timeout_add(500, lambda: self._reset_connect_state())

                    # Clear any timeout in the password dialog
                    if (
                        self.password_dialog
                        and self.password_dialog.connection_timeout_id
                    ):
                        GLib.source_remove(self.password_dialog.connection_timeout_id)
                        self.password_dialog.connection_timeout_id = None
                        self.password_dialog.is_connecting = False
                else:
                    # Connection failed - show error in dialog
                    self._reset_connect_state()
                    if self.password_dialog:
                        self._show_connection_error(message)

                # Update display after connection attempt
                self.on_changed()

            try:
                self.wifi_service.connect_to_wifi(
                    self.access_point, password, callback=on_connection_result
                )
            except Exception as e:
                # Handle any connection errors gracefully
                self._reset_connect_state()
                if self.password_dialog:
                    self._show_connection_error("Connection failed. Please try again.")
                self.on_changed()

    def _show_connection_error(self, message="Incorrect password. Please try again."):
        """Show connection error in a separate thread to prevent UI blocking"""
        if self.password_dialog:
            self.password_dialog.show_error(message)
        return False  # Don't repeat if called from GLib.timeout_add

    def _on_password_cancel(self):
        """Handle password dialog cancel action"""
        # Reset any connecting state
        self._reset_connect_state()


class WifiConnections(Box):
    def __init__(self, parent, show_back_button=True, **kwargs):
        super().__init__(
            spacing=8,
            orientation="vertical",
            style="margin: 8px",
            name="wifi-connections",
            **kwargs,
        )

        self.parent = parent
        self.network_service = NetworkClient()
        self.wifi_service = None
        self.is_scanning = False  # Track scanning state

        # Wait for network service to be ready
        self.network_service.connect("wifi-device-added", self.on_network_ready)

        # Create pull-to-refresh indicator
        self.refresh_indicator = Label(
            name="wifi-refresh-indicator",
            label="↓ Pull to scan for networks",
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
                    on_clicked=lambda *_: self.parent.close_wifi(),
                )
            )
        title_children.append(Label("Wi-Fi", name="wifi-title"))

        self.title = Box(
            orientation="h",
            children=title_children,
        )

        self.toggle_button = Gtk.Switch(visible=True, name="toggle-button")

        # Create Known Network section
        self.known_networks_label = Label(
            label="Known Network", h_align="start", name="networks-title"
        )
        self.known_networks = Box(
            spacing=4, orientation="vertical", name="known-networks"
        )

        # Create "No networks available" message
        self.no_networks_label = Label(
            label="No networks available",
            h_align="center",
            name="no-networks-label",
            visible=False,
        )

        # Create Other Networks section with clickable title
        self.other_networks_button = Button(
            child=Label("Other Networks", h_align="start"),
            name="wifi-other-button",
            on_clicked=self.toggle_other_networks,
        )
        self.other_networks = Box(spacing=4, orientation="vertical")

        # Create scrolled window for other networks
        self.other_networks_scrolled = ScrolledWindow(
            min_content_size=(303, 150),
            child=self.other_networks,
            overlay_scroll=True,
        )

        # Create revealer for Other Networks section
        self.other_networks_revealer = Revealer(
            child=self.other_networks_scrolled,
            transition_type="slide-down",
            transition_duration=100,
            child_revealed=False,
        )

        # Create More Settings button (same style as Other Networks button)
        self.more_settings_button = Button(
            child=Label("More Settings", h_align="start"),
            name="wifi-other-button",
            on_clicked=self.open_network_settings,
        )

        self.children = [
            CenterBox(
                start_children=self.title,
                end_children=self.toggle_button,
                name="wifi-widget-top",
            ),
            self.refresh_indicator,
            Separator(orientation="h", name="separator"),
            self.known_networks_label,
            self.known_networks,
            self.no_networks_label,
            Separator(orientation="h", name="separator"),
            self.other_networks_button,
            self.other_networks_revealer,
            Separator(orientation="h", name="separator"),
            self.more_settings_button,
        ]

        # Connect cleanup on destroy
        self.connect("destroy", self.on_destroy)

    def toggle_other_networks(self, *_):
        """Toggle the visibility of other networks section"""
        current_state = self.other_networks_revealer.child_revealed
        self.other_networks_revealer.child_revealed = not current_state

        # Update button text based on state
        if self.other_networks_revealer.child_revealed:
            # Trigger a scan when revealing other networks
            if self.wifi_service:
                self.wifi_service.scan()

    def on_network_ready(self, *_):
        """Called when network service is ready"""
        self.wifi_service = self.network_service.wifi_device
        if self.wifi_service:
            # Set up WiFi toggle
            self.toggle_button.set_active(self.wifi_service.wireless_enabled)
            self.toggle_button.connect("notify::active", self.on_toggle_changed)

            # Connect to WiFi service signals
            self.wifi_service.connect(
                "notify::wireless-enabled", self.on_wifi_enabled_changed
            )
            self.wifi_service.connect("changed", self.update_networks)
            self.wifi_service.connect("ap-added", self.update_networks)
            self.wifi_service.connect("ap-removed", self.update_networks)

            # Initial network update
            self.update_networks()

    def on_toggle_changed(self, toggle_button, *_):
        """Handle WiFi toggle button changes"""
        if self.wifi_service:
            new_state = toggle_button.get_active()
            self.wifi_service.wireless_enabled = new_state
            logger.info(f"[WiFi] Toggle changed to: {new_state}")

    def on_wifi_enabled_changed(self, *_):
        """Handle WiFi enabled state changes"""
        if self.wifi_service:
            self.toggle_button.set_active(self.wifi_service.wireless_enabled)

    def open_network_settings(self, *_):
        """Open NetworkManager connection editor"""
        try:
            subprocess.Popen(["nm-connection-editor"], start_new_session=True)
            if self.parent and hasattr(self.parent, "hide_controlcenter"):
                self.parent.hide_controlcenter()
        except FileNotFoundError:
            logger.error(
                "[WiFi] nm-connection-editor not found. Please install network-manager-gnome package."
            )
        except Exception as e:
            logger.error(f"[WiFi] Failed to open network settings: {e}")

    def update_networks(self, *_):
        """Update the list of available networks"""
        if not self.wifi_service:
            return

        # Clear existing networks
        for child in self.known_networks.get_children():
            child.destroy()
        for child in self.other_networks.get_children():
            child.destroy()

        # Get current networks
        access_points = self.wifi_service.access_points
        known_networks = []
        other_networks = []

        for access_point in access_points:
            if access_point.ssid and access_point.ssid != "Unknown":
                # Categorize networks: connected or saved networks go to "Known Network"
                # All others go to "Other Networks"
                if access_point.is_active or self._is_saved_network(access_point):
                    known_networks.append(access_point)
                else:
                    other_networks.append(access_point)

        # Add known networks
        for access_point in known_networks:
            network_slot = WifiNetworkSlot(
                access_point, self.wifi_service, parent=self.parent
            )
            self.known_networks.add(network_slot)

        # Add other networks
        for access_point in other_networks:
            network_slot = WifiNetworkSlot(
                access_point, self.wifi_service, parent=self.parent
            )
            self.other_networks.add(network_slot)

        # Show/hide sections based on available networks
        has_known_networks = len(known_networks) > 0
        has_other_networks = len(other_networks) > 0
        has_any_networks = has_known_networks or has_other_networks

        # Show known networks section only if there are known networks
        self.known_networks_label.set_visible(has_known_networks)
        self.known_networks.set_visible(has_known_networks)

        # Show "No networks available" message if no networks at all
        self.no_networks_label.set_visible(not has_any_networks)

        # Always show the other networks button, regardless of available networks
        self.other_networks_button.set_visible(True)  # Always visible

        # Update all network connection states
        self.refresh_network_states()

    def _is_saved_network(self, access_point):
        """Check if a network is saved/known (placeholder implementation)"""
        # TODO: Implement proper saved network detection
        # This would typically check against NetworkManager's saved connections
        # For now, we'll use a simple heuristic
        return False

    def refresh_network_states(self, *_):
        """Refresh connection states for all network slots"""
        # Refresh known networks
        for child in self.known_networks.get_children():
            if hasattr(child, "on_changed"):
                child.on_changed()

        # Refresh other networks
        for child in self.other_networks.get_children():
            if hasattr(child, "on_changed"):
                child.on_changed()

    def on_destroy(self, widget):
        """Cleanup when widget is destroyed"""
        # Make sure other networks revealer is collapsed when closing
        self.other_networks_revealer.child_revealed = False

    def close_wifi(self):
        """Called when WiFi panel is being closed"""
        # Collapse the other networks section when closing
        self.other_networks_revealer.child_revealed = False
