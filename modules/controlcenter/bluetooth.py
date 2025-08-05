from gi.repository import Gdk, GLib, Gtk

from fabric.bluetooth import BluetoothClient, BluetoothDevice
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow


class BluetoothDeviceSlot(CenterBox):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(**kwargs)
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
                image=self.dimage,
                on_clicked=lambda *_: self.toggle_connecting(),
            ),
            Label(label=device.name),  # type: ignore
        ]

        self.device.emit("changed")  # to update display status

    def toggle_connecting(self):
        self.device.emit("changed")
        self.device.set_connecting(not self.device.connected)

    def on_changed(self, *_):
        self.styles = [
            "connected" if self.device.connected else "",
            "paired" if self.device.paired else "",
        ]
        self.dimage.set_property("style-classes", " ".join(self.styles))
        return


class BluetoothConnections(Box):
    def __init__(self, parent, show_hidden_devices: bool = False, show_back_button=True, **kwargs):
        super().__init__(
            spacing=4,
            orientation="vertical",
            style="margin: 8px",
            **kwargs,
        )

        self.parent = parent
        self.show_hidden_devices = show_hidden_devices

        self.client = BluetoothClient(on_device_added=self.on_device_added)

        # Create title with optional back button
        title_children = []
        if show_back_button:
            title_children.append(
                Button(
                    image=Image(icon_name="back", size=10),
                    on_clicked=lambda *_: self.parent.close_bluetooth(),
                )
            )
        title_children.append(Label("Bluetooth"))

        self.title = Box(
            orientation="h",
            children=title_children,
        )

        self.toggle_button = Gtk.Switch(visible=True, name="toggle-button")

        self.toggle_button.set_active(self.client.enabled)
        self.toggle_button.connect(
            "notify::active",
            lambda *_: self.client.set_enabled(self.toggle_button.get_active()),
        )

        self.client.connect(
            "notify::enabled",
            lambda *_: self.toggle_button.set_active(self.client.enabled),
        )

        # Connect scanning state changes to update scan button
        self.client.connect("notify::scanning", lambda *_: self.update_scan_label())

        self.not_paired = Box(spacing=2, orientation="vertical")
        self.paired = Box(spacing=2, orientation="vertical")

        # Create pull-to-refresh indicator
        self.refresh_indicator = Label(
            name="bluetooth-refresh-indicator",
            label="↓ Pull to scan for devices",
            h_align="center",
            visible=False,
        )

        self.device_box = Box(
            spacing=2,
            orientation="vertical",
            children=[self.refresh_indicator, self.paired, self.not_paired],
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
                name="bluetooth-widget-top",
            ),
            Label("Devices", h_align="start", name="devices-title"),
            self.scrolled_window,
        ]
        self.client.notify("scanning")
        self.client.notify("enabled")

        # Connect cleanup on destroy
        self.connect("destroy", self.on_destroy)

    def on_destroy(self, widget):
        """Cleanup animations when widget is destroyed"""
        self.stop_bounce_animation()

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
        self.bounce_amplitude = 15  # Maximum bounce height in pixels

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
                # Scrolling up at the top - toggle scan (start or stop)
                self.client.toggle_scan()
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
                # Toggle scan (start or stop)
                self.client.toggle_scan()
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
        self.bounce_amplitude = 20  # Higher amplitude
        self.bounce_timeout_id = GLib.timeout_add(16, self.animate_elastic)

    def animate_elastic(self):
        """Animate elastic bounce effect"""
        if self.bounce_frame >= self.bounce_duration:
            # Animation finished
            self.refresh_indicator.set_margin_top(0)
            self.bounce_timeout_id = None
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

    def update_scan_label(self):
        """Update scanning state appearance"""
        if self.client.scanning:
            # Show scanning feedback in refresh indicator
            self.refresh_indicator.set_label("Scanning for devices...")
            self.refresh_indicator.set_visible(True)
            self.refresh_indicator.add_style_class("scanning")
        else:
            # Hide scanning feedback
            if not self.is_pulling:
                self.refresh_indicator.set_visible(False)
            self.refresh_indicator.remove_style_class("scanning")

    def on_device_added(self, client: BluetoothClient, address: str):
        if not (device := client.get_device(address)):
            return

        if (device.name in ["", None]) and not self.show_hidden_devices:
            return

        slot = BluetoothDeviceSlot(device, paired=device.paired)

        if device.paired:
            return self.paired.add(slot)
        return self.not_paired.add(slot)
