import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk
from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from services.network import NetworkClient
from widgets.wifi_password_dialog import WiFiPasswordDialog


class WifiNetworkSlot(CenterBox):
    def __init__(self, access_point, wifi_service, parent=None, **kwargs):
        super().__init__(**kwargs)
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
            size=5,
            name="device-icon",
            style_classes=" ".join(self.styles),
        )

        # Initialize password dialog
        self.password_dialog = None

        self.start_children = [
            Button(
                image=self.dimage,
                on_clicked=lambda *_: self.toggle_connecting(),
            ),
            Label(label=self.ssid),
        ]

        # Emit initial change to update display
        self.on_changed()

    def toggle_connecting(self):
        """Toggle WiFi network connection"""
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
            from gi.repository import GLib

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
                        from gi.repository import GLib

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
        """Update display when connection state changes"""
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
            spacing=4,
            orientation="vertical",
            style="margin: 8px",
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
        title_children.append(Label("WiFi"))

        self.title = Box(
            orientation="h",
            children=title_children,
        )

        self.toggle_button = Gtk.Switch(visible=True, name="toggle-button")

        self.available_networks = Box(spacing=2, orientation="vertical")

        self.device_box = Box(
            spacing=2,
            orientation="vertical",
            children=[self.refresh_indicator, self.available_networks],
        )

        # Create scrolled window with pull-to-refresh
        self.scrolled_window = ScrolledWindow(
            min_content_size=(303, 400),
            max_content_size=(303, 800),
            child=self.device_box,
            overlay_scroll=True,
        )

        # Add pull-to-refresh functionality
        self.setup_pull_to_refresh()

        self.children = [
            CenterBox(
                start_children=self.title,
                end_children=self.toggle_button,
                name="wifi-widget-top",
            ),
            Label("Networks", h_align="start", name="networks-title"),
            self.scrolled_window,
        ]

        # Connect cleanup on destroy
        self.connect("destroy", self.on_destroy)

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

    def update_networks(self, *_):
        """Update the list of available networks"""
        if not self.wifi_service:
            return

        # Clear existing networks
        for child in self.available_networks.get_children():
            child.destroy()

        # Add current networks
        access_points = self.wifi_service.access_points
        for access_point in access_points:
            if access_point.ssid and access_point.ssid != "Unknown":
                network_slot = WifiNetworkSlot(
                    access_point, self.wifi_service, parent=self.parent
                )
                self.available_networks.add(network_slot)

        # Update all network connection states
        self.refresh_network_states()

    def refresh_network_states(self, *_):
        """Refresh connection states for all network slots"""
        for child in self.available_networks.get_children():
            if hasattr(child, "on_changed"):
                child.on_changed()

    def setup_pull_to_refresh(self):
        """Setup pull-to-refresh gesture for the scrolled window"""
        # Get the scrolled window's vertical adjustment
        self.vadjustment = self.scrolled_window.get_vadjustment()

        # Track gesture state
        self.pull_start_y = 0
        self.is_pulling = False
        self.pull_threshold = 50  # pixels to trigger refresh

        # Animation state
        self.bounce_timeout_id = None
        self.bounce_frame = 0
        self.bounce_duration = 60  # Total frames for animation
        # Maximum bounce height in pixels (increased for visibility)
        self.bounce_amplitude = 30

        # Connect to scroll events
        self.scrolled_window.connect("scroll-event", self.on_scroll_event)
        self.scrolled_window.connect("button-press-event", self.on_button_press)
        self.scrolled_window.connect("button-release-event", self.on_button_release)
        self.scrolled_window.connect("motion-notify-event", self.on_motion_notify)

        # Enable events
        self.scrolled_window.set_events(
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
                # Scrolling up at the top - start scan
                if self.wifi_service:
                    self.wifi_service.scan()
                    # Trigger smooth bounce animation for scroll
                    self.start_bounce_animation()
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
                # Start scan
                if self.wifi_service:
                    self.wifi_service.scan()
                    # Trigger elastic animation for pull gesture (most satisfying)
                    self.start_elastic_animation()
            else:
                # Stop any ongoing animation
                self.stop_bounce_animation()
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

    def ease_out_bounce(self, t):
        """Smooth bounce easing function (0 to 1)"""
        if t < 1 / 2.75:
            return 7.5625 * t * t
        elif t < 2 / 2.75:
            t -= 1.5 / 2.75
            return 7.5625 * t * t + 0.75
        elif t < 2.5 / 2.75:
            t -= 2.25 / 2.75
            return 7.5625 * t * t + 0.9375
        else:
            t -= 2.625 / 2.75
            return 7.5625 * t * t + 0.984375

    def ease_out_elastic(self, t):
        """Elastic easing function for smoother bounce"""
        import math

        if t == 0 or t == 1:
            return t

        p = 0.3
        s = p / 4
        return math.pow(2, -10 * t) * math.sin((t - s) * (2 * math.pi) / p) + 1

    def start_bounce_animation(self):
        """Start smooth bounce animation for the refresh indicator"""
        if self.bounce_timeout_id:
            GLib.source_remove(self.bounce_timeout_id)

        self.bounce_frame = 0
        # Higher frame rate for smoother animation (16ms = ~60fps)
        self.bounce_timeout_id = GLib.timeout_add(16, self.animate_bounce)

    def animate_bounce(self):
        """Animate smooth bounce effect with easing"""
        if self.bounce_frame >= self.bounce_duration:
            # Animation finished
            self.refresh_indicator.set_margin_top(0)
            self.bounce_timeout_id = None
            # Hide indicator after animation if not pulling
            if not self.is_pulling:
                self.refresh_indicator.set_visible(False)
            return False

        # Calculate progress (0 to 1)
        progress = self.bounce_frame / self.bounce_duration

        # Apply easing function for smooth bounce
        eased_progress = self.ease_out_bounce(progress)

        # Calculate bounce offset (starts high, bounces down to 0)
        bounce_offset = int(self.bounce_amplitude * (1 - eased_progress))
        self.refresh_indicator.set_margin_top(max(0, bounce_offset))

        self.bounce_frame += 1
        return True

    def start_elastic_animation(self):
        """Start elastic animation for more dramatic effect"""
        if self.bounce_timeout_id:
            GLib.source_remove(self.bounce_timeout_id)

        self.bounce_frame = 0
        self.bounce_duration = 80  # Longer for elastic effect
        # Higher amplitude (increased for visibility)
        self.bounce_amplitude = 40
        self.bounce_timeout_id = GLib.timeout_add(16, self.animate_elastic)

    def animate_elastic(self):
        """Animate elastic bounce effect"""
        if self.bounce_frame >= self.bounce_duration:
            # Animation finished
            self.refresh_indicator.set_margin_top(0)
            self.bounce_timeout_id = None
            # Hide indicator after animation if not pulling
            if not self.is_pulling:
                self.refresh_indicator.set_visible(False)
            return False

        # Calculate progress (0 to 1)
        progress = self.bounce_frame / self.bounce_duration

        # Apply elastic easing
        eased_progress = self.ease_out_elastic(progress)

        # Calculate bounce offset
        bounce_offset = int(self.bounce_amplitude * (1 - eased_progress))
        self.refresh_indicator.set_margin_top(max(0, bounce_offset))

        self.bounce_frame += 1
        return True

    def stop_bounce_animation(self):
        """Stop any ongoing animations"""
        if self.bounce_timeout_id:
            GLib.source_remove(self.bounce_timeout_id)
            self.bounce_timeout_id = None
        self.refresh_indicator.set_margin_top(0)

    def on_destroy(self, widget):
        """Cleanup animations when widget is destroyed"""
        self.stop_bounce_animation()
