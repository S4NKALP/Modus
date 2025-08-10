from widgets.wifi_password_dialog import WiFiPasswordDialog
from services.network import NetworkClient
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.revealer import Revealer
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.box import Box
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
            except Exception:
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
        self.refresh_timer = None  # Timer for periodic network refresh
        self._update_in_progress = False  # Prevent concurrent updates
        self._destroyed = False  # Track if widget is destroyed

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

        # Add pull-to-refresh functionality to scrolled window
        self.setup_pull_to_refresh()

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

        # Start periodic network monitoring for real-time updates
        self.start_network_monitoring()

    def toggle_other_networks(self, *_):
        """Toggle the visibility of other networks section"""
        current_state = self.other_networks_revealer.child_revealed
        self.other_networks_revealer.child_revealed = not current_state

        # Update button text based on state
        if self.other_networks_revealer.child_revealed:
            # Trigger a scan when revealing other networks and force refresh
            if self.wifi_service:
                self.wifi_service.scan()
                # Also force an immediate network refresh to catch any missed connections
                self.force_network_refresh()

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
            pass
        except Exception:
            pass

    def update_networks(self, *_):
        """Update the list of available networks"""
        # Prevent concurrent updates and check if destroyed
        if self._update_in_progress or self._destroyed or not self.wifi_service:
            return

        self._update_in_progress = True

        try:
            # Store current network SSIDs to detect changes
            current_known_ssids = {
                child.ssid
                for child in self.known_networks.get_children()
                if hasattr(child, "ssid")
            }
            current_other_ssids = {
                child.ssid
                for child in self.other_networks.get_children()
                if hasattr(child, "ssid")
            }

            # Get current networks
            access_points = self.wifi_service.access_points
            known_networks = []
            other_networks = []
            new_known_ssids = set()
            new_other_ssids = set()

            for access_point in access_points:
                try:
                    if access_point.ssid and access_point.ssid != "Unknown":
                        # Categorize networks: connected or saved networks go to "Known Network"
                        # All others go to "Other Networks"
                        if access_point.is_active or self._is_saved_network(
                            access_point
                        ):
                            known_networks.append(access_point)
                            new_known_ssids.add(access_point.ssid)
                        else:
                            other_networks.append(access_point)
                            new_other_ssids.add(access_point.ssid)
                except Exception:
                    continue

            # Check if we need to update (networks added/removed)
            known_changed = current_known_ssids != new_known_ssids
            other_changed = current_other_ssids != new_other_ssids

            # Only rebuild if something actually changed
            if known_changed or other_changed:
                # Clear existing networks safely
                for child in list(self.known_networks.get_children()):
                    if not self._destroyed:
                        child.destroy()
                for child in list(self.other_networks.get_children()):
                    if not self._destroyed:
                        child.destroy()

                # Add known networks
                for access_point in known_networks:
                    if not self._destroyed:
                        network_slot = WifiNetworkSlot(
                            access_point, self.wifi_service, parent=self.parent
                        )
                        self.known_networks.add(network_slot)

                # Add other networks
                for access_point in other_networks:
                    if not self._destroyed:
                        network_slot = WifiNetworkSlot(
                            access_point, self.wifi_service, parent=self.parent
                        )
                        self.other_networks.add(network_slot)

            # Show/hide sections based on available networks
            if not self._destroyed:
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

        except Exception:
            pass
        finally:
            self._update_in_progress = False

    def _is_saved_network(self, access_point):
        """Check if a network is saved/known using NetworkManager connections"""
        if not self.network_service or not self.network_service._client:
            return False

        try:
            ssid = access_point.ssid
            if not ssid or ssid == "Unknown":
                return False

            # Get all saved connections from NetworkManager
            connections = self.network_service._client.get_connections()

            for connection in connections:
                # Check if this is a WiFi connection
                if connection.get_connection_type() != "802-11-wireless":
                    continue

                # Get the wireless setting
                wifi_setting = connection.get_setting_wireless()
                if not wifi_setting:
                    continue

                # Compare SSIDs
                connection_ssid_bytes = wifi_setting.get_ssid()
                if connection_ssid_bytes:
                    from gi.repository import NM

                    connection_ssid = NM.utils_ssid_to_utf8(
                        connection_ssid_bytes.get_data()
                    )
                    if connection_ssid == ssid:
                        return True

        except Exception:
            pass

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

    def start_network_monitoring(self):
        """Start periodic monitoring for network changes"""
        # Monitor for network changes every 5 seconds
        # This helps catch networks that connect from external sources
        self.refresh_timer = GLib.timeout_add_seconds(5, self.periodic_network_refresh)

    def stop_network_monitoring(self):
        """Stop periodic monitoring"""
        if self.refresh_timer:
            GLib.source_remove(self.refresh_timer)
            self.refresh_timer = None

    def periodic_network_refresh(self):
        """Periodically refresh network list to catch external connections"""
        # Skip if update in progress, destroyed, or wifi service not available
        if (
            self._update_in_progress
            or self._destroyed
            or not self.wifi_service
            or not self.wifi_service.wireless_enabled
        ):
            return True  # Continue monitoring

        try:
            # Simple check - just trigger update_networks which has its own safety checks
            self.update_networks()
        except Exception:
            pass

        return True  # Continue monitoring

    def force_network_refresh(self):
        """Force an immediate refresh of the network list"""
        if self._update_in_progress or self._destroyed:
            return

        try:
            # Simply trigger update_networks which has its own safety checks
            self.update_networks()
        except Exception:
            pass

    def setup_pull_to_refresh(self):
        """Setup pull-to-refresh gesture for the scrolled window"""
        # Get the scrolled window's vertical adjustment
        self.vadjustment = self.other_networks_scrolled.get_vadjustment()

        # Track gesture state
        self.pull_start_y = 0
        self.is_pulling = False
        self.pull_threshold = 50  # pixels to trigger refresh

        # Connect to scroll events
        self.other_networks_scrolled.connect("scroll-event", self.on_scroll_event)
        self.other_networks_scrolled.connect("button-press-event", self.on_button_press)
        self.other_networks_scrolled.connect(
            "button-release-event", self.on_button_release
        )
        self.other_networks_scrolled.connect(
            "motion-notify-event", self.on_motion_notify
        )

        # Enable events
        self.other_networks_scrolled.set_events(
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
                # Scrolling up at the top - trigger scan and force refresh
                if self.wifi_service:
                    self.wifi_service.scan()
                    self.force_network_refresh()
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
                # Trigger scan and force refresh
                if self.wifi_service:
                    self.wifi_service.scan()
                    self.force_network_refresh()
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
                    self.refresh_indicator.set_label("↑ Release to scan")
                    self.refresh_indicator.add_style_class("ready-to-refresh")
                else:
                    self.refresh_indicator.set_label("↓ Pull to scan for networks")
                    self.refresh_indicator.remove_style_class("ready-to-refresh")
            else:
                self.refresh_indicator.set_visible(False)
        return False

    def on_destroy(self, widget):
        """Cleanup when widget is destroyed"""
        # Mark as destroyed to prevent further updates
        self._destroyed = True
        # Stop monitoring
        self.stop_network_monitoring()
        # Make sure other networks revealer is collapsed when closing
        try:
            self.other_networks_revealer.child_revealed = False
        except:
            pass  # Widget might already be destroyed

    def close_wifi(self):
        """Called when WiFi panel is being closed"""
        # Collapse the other networks section when closing
        self.other_networks_revealer.child_revealed = False
