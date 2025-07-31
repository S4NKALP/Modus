from gi.repository import Gtk, Gdk, GLib

from services.network import NetworkService
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.eventbox import EventBox


class WifiNetworkSlot(CenterBox):
    def __init__(self, network_data: dict, wifi_service, **kwargs):
        super().__init__(**kwargs)
        self.network_data = network_data
        self.wifi_service = wifi_service

        # Get network info
        self.ssid = network_data.get("ssid", "Unknown")
        self.bssid = network_data.get("bssid", "")
        self.strength = network_data.get("strength", 0)
        self.icon_name = network_data.get("icon-name", "network-wireless-signal-none-symbolic")

        # The network service puts the same active-ap reference in all networks
        # We need to check if THIS specific network's BSSID matches the active AP's BSSID
        self.is_connected = False
        if self.wifi_service and self.wifi_service._ap:
            active_bssid = self.wifi_service._ap.get_bssid()
            self.is_connected = (active_bssid == self.bssid)

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
        # Check if this network is currently connected by comparing BSSIDs
        is_currently_connected = False
        if self.wifi_service and self.wifi_service._ap:
            active_bssid = self.wifi_service._ap.get_bssid()
            is_currently_connected = (active_bssid == self.bssid)

        if is_currently_connected:
            # Disconnect from network
            success = self.wifi_service.disconnect_network(self.ssid)
            if success:
                self.is_connected = False
        else:
            # Connect to network (try without password first, could be enhanced for password input)
            success = self.wifi_service.connect_network(self.ssid)
            if success:
                self.is_connected = True

        # Update display after connection attempt
        self.on_changed()

    def on_changed(self, *_):
        """Update display when connection state changes"""
        # Check if this network is currently connected by comparing BSSIDs
        is_currently_connected = False
        if self.wifi_service and self.wifi_service._ap:
            active_bssid = self.wifi_service._ap.get_bssid()
            is_currently_connected = (active_bssid == self.bssid)

        self.is_connected = is_currently_connected
        self.styles = [
            "connected" if self.is_connected else "",
        ]
        self.dimage.set_property("style-classes", " ".join(self.styles))
        return


class WifiConnections(Box):
    def __init__(self, parent, **kwargs):
        super().__init__(
            spacing=4,
            orientation="vertical",
            style="margin: 8px",
            **kwargs,
        )

        self.parent = parent
        self.network_service = NetworkService()
        self.wifi_service = None
        self.is_scanning = False  # Track scanning state

        # Wait for network service to be ready
        self.network_service.connect("device-ready", self.on_network_ready)

        # Create pull-to-refresh indicator
        self.refresh_indicator = Label(
            name="wifi-refresh-indicator",
            label="↓ Pull to scan for networks",
            h_align="center",
            visible=False,
            style="color: #fff; font-size: 12px; padding: 5px;"
        )

        self.title = Box(
            orientation="h",
            children=[
                Button(
                    image=Image(icon_name="back", size=10),
                    on_clicked=lambda *_: self.parent.close_wifi(),
                ),
                Label("WiFi"),
            ],
        )

        self.toggle_button = Gtk.Switch(visible=True, name="toggle-button")

        self.available_networks = Box(spacing=2, orientation="vertical")

        self.device_box = Box(
            spacing=2,
            orientation="vertical",
            children=[self.refresh_indicator, self.available_networks]
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
            self.toggle_button.set_active(self.wifi_service.enabled)
            self.toggle_button.connect(
                "notify::active",
                lambda *_: setattr(self.wifi_service, 'enabled', self.toggle_button.get_active()),
            )

            # Connect to WiFi service signals
            self.wifi_service.connect("notify::enabled", self.on_wifi_enabled_changed)
            self.wifi_service.connect("notify::scanning", self.on_scanning_changed)
            self.wifi_service.connect("changed", self.update_networks)
            # Also connect to access point changes to update connection states
            self.wifi_service.connect("notify::access-points", self.refresh_network_states)

            # Initial network update
            self.update_networks()

            # Initialize scanning state
            self.wifi_service.notify("scanning")

    def on_wifi_enabled_changed(self, *_):
        """Handle WiFi enabled state changes"""
        if self.wifi_service:
            self.toggle_button.set_active(self.wifi_service.enabled)

    def on_scanning_changed(self, *_):
        """Handle scanning state changes"""
        if self.wifi_service:
            is_scanning = self.wifi_service.scanning
            self.is_scanning = is_scanning  # Update our tracking state
            self.update_scan_label()

    def update_networks(self, *_):
        """Update the list of available networks"""
        if not self.wifi_service:
            return

        # Clear existing networks
        for child in self.available_networks.get_children():
            child.destroy()

        # Add current networks
        access_points = self.wifi_service.access_points
        for ap_data in access_points:
            if ap_data.get("ssid") and ap_data.get("ssid") != "Unknown":
                network_slot = WifiNetworkSlot(ap_data, self.wifi_service)
                self.available_networks.add(network_slot)

        # Update all network connection states
        self.refresh_network_states()

    def refresh_network_states(self, *_):
        """Refresh connection states for all network slots"""
        for child in self.available_networks.get_children():
            if hasattr(child, 'on_changed'):
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
        self.bounce_amplitude = 30  # Maximum bounce height in pixels (increased for visibility)

        # Connect to scroll events
        self.scrolled_window.connect("scroll-event", self.on_scroll_event)
        self.scrolled_window.connect("button-press-event", self.on_button_press)
        self.scrolled_window.connect("button-release-event", self.on_button_release)
        self.scrolled_window.connect("motion-notify-event", self.on_motion_notify)

        # Enable events
        self.scrolled_window.set_events(
            Gdk.EventMask.SCROLL_MASK |
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )

    def on_scroll_event(self, widget, event):
        """Handle scroll events for pull-to-refresh"""
        # Only handle pull-to-refresh when at the top
        if self.vadjustment.get_value() <= 0:
            if event.direction == Gdk.ScrollDirection.UP:
                # Scrolling up at the top - start scan (only if not already scanning)
                if self.wifi_service and not self.is_scanning:
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
                # Start scan (only if not already scanning)
                if self.wifi_service and not self.is_scanning:
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
                    if self.is_scanning:
                        self.refresh_indicator.set_label("↑ Already scanning...")
                    else:
                        self.refresh_indicator.set_label("↑ Release to scan")
                    self.refresh_indicator.add_style_class("ready-to-refresh")
                else:
                    if self.is_scanning:
                        self.refresh_indicator.set_label("↓ Scanning in progress...")
                    else:
                        self.refresh_indicator.set_label("↓ Pull to scan for networks")
                    self.refresh_indicator.remove_style_class("ready-to-refresh")
            else:
                self.refresh_indicator.set_visible(False)
        return False

    def update_scan_label(self):
        """Update scanning state appearance"""
        if self.wifi_service and self.wifi_service.scanning:
            # Show scanning feedback in refresh indicator

            self.refresh_indicator.set_label("Scanning for networks...")
            self.refresh_indicator.set_visible(True)
            self.refresh_indicator.add_style_class("scanning")
            self.refresh_indicator.show_all()
        else:
            # Hide scanning feedback only if not animating and not pulling
            if not self.is_pulling and not self.bounce_timeout_id:
                self.refresh_indicator.set_visible(False)
            self.refresh_indicator.remove_style_class("scanning")

    def ease_out_bounce(self, t):
        """Smooth bounce easing function (0 to 1)"""
        import math
        if t < 1/2.75:
            return 7.5625 * t * t
        elif t < 2/2.75:
            t -= 1.5/2.75
            return 7.5625 * t * t + 0.75
        elif t < 2.5/2.75:
            t -= 2.25/2.75
            return 7.5625 * t * t + 0.9375
        else:
            t -= 2.625/2.75
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
            # Hide indicator after animation if not scanning and not pulling
            if not (self.wifi_service and self.wifi_service.scanning) and not self.is_pulling:
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
        self.bounce_amplitude = 40  # Higher amplitude (increased for visibility)
        self.bounce_timeout_id = GLib.timeout_add(16, self.animate_elastic)

    def animate_elastic(self):
        """Animate elastic bounce effect"""
        if self.bounce_frame >= self.bounce_duration:
            # Animation finished
            self.refresh_indicator.set_margin_top(0)
            self.bounce_timeout_id = None
            # Hide indicator after animation if not scanning and not pulling
            if not (self.wifi_service and self.wifi_service.scanning) and not self.is_pulling:
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