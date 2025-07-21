import gi
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GLib, Gtk

from services.network import NetworkClient
from utils import icons
import subprocess

gi.require_version("Gtk", "3.0")


class WiFiTab:
    """WiFi network management tab for settings"""

    def __init__(self):
        self.network_client = NetworkClient()
        self.access_point_widgets = {}
        self.password_entries = {}
        self.connecting_to = None
        
        # Connect to network client signals
        self.network_client.connect("ready", self._on_network_ready)
        self.network_client.connect("changed", self._on_network_changed)
        
        if self.network_client.is_ready:
            self._setup_network_signals()

    def _on_network_ready(self, *args):
        """Called when network client is ready"""
        self._setup_network_signals()
        self._refresh_networks()

    def _setup_network_signals(self):
        """Setup signals for WiFi device"""
        if self.network_client.wifi_device:
            self.network_client.wifi_device.connect("changed", self._on_wifi_changed)
            self.network_client.wifi_device.connect("ap-added", self._on_ap_added)
            self.network_client.wifi_device.connect("ap-removed", self._on_ap_removed)

    def _on_network_changed(self, *args):
        """Called when network state changes"""
        self._refresh_networks()

    def _on_wifi_changed(self, *args):
        """Called when WiFi state changes"""
        self._refresh_networks()

    def _on_ap_added(self, device, ap):
        """Called when access point is added"""
        self._refresh_networks()

    def _on_ap_removed(self, device, ap):
        """Called when access point is removed"""
        self._refresh_networks()

    def create_wifi_tab(self):
        """Create the WiFi tab content"""
        main_vbox = Box(
            orientation="v",
            spacing=0,
            style="padding: 0; margin: 15px;"
        )

        # Set fixed size for the main container to match GUI window
        main_vbox.set_size_request(620, 580)  # Match GUI window content area

        # Header section with title and controls
        header_box = Box(
            orientation="h",
            spacing=12,
        )

        # WiFi section
        wifi_section = Box(orientation="v", spacing=4)

        # WiFi title
        wifi_title = Label(
            markup="<span size='large'><b>Wi-Fi</b></span>",
            h_align="start"
        )
        wifi_section.add(wifi_title)

        # WiFi subtitle
        self.wifi_subtitle = Label(
            markup="<span>Find and connect to Wi-Fi networks</span>",
            h_align="start"
        )
        wifi_section.add(self.wifi_subtitle)

        header_box.add(wifi_section)

        # Spacer to push controls to the right
        spacer = Box()
        spacer.set_hexpand(True)
        header_box.add(spacer)

        # Controls section
        controls_box = Box(orientation="h", spacing=12)

        # WiFi toggle switch
        self.wifi_switch = Gtk.Switch()
        self.wifi_switch.set_valign(Gtk.Align.CENTER)
        self.wifi_switch.connect("notify::active", self._on_wifi_switch_toggled)
        controls_box.add(self.wifi_switch)

        # Refresh button
        self.refresh_button = Button()
        self.refresh_icon = Label(name="wifi-tab-icon", markup=icons.reload, style="font-size: 18px;")
        self.refresh_button.add(self.refresh_icon)
        self.refresh_button.set_size_request(40, 40)
        self.refresh_button.set_tooltip_text("Refresh networks")
        self.refresh_button.set_style("margin:10px;")
        self.refresh_button.connect("clicked", self._on_refresh_clicked)
        controls_box.add(self.refresh_button)

        header_box.add(controls_box)
        main_vbox.add(header_box)

        # Networks list in scrolled window
        self.networks_scrolled = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False,
        )

        # Set size to match available space (580 - header space ≈ 500)
        self.networks_scrolled.set_size_request(-1, 500)

        self.networks_container = Box(
            orientation="v",
            spacing=0,
        )
        self.networks_scrolled.add(self.networks_container)
        main_vbox.add(self.networks_scrolled)

        # Initialize the display
        GLib.timeout_add(100, self._refresh_networks)

        return main_vbox

    def _refresh_networks(self):
        """Refresh the networks display"""
        # Clear existing widgets
        for child in self.networks_container.get_children():
            self.networks_container.remove(child)
        self.access_point_widgets.clear()
        self.password_entries.clear()

        # Update WiFi status
        self._update_wifi_status()

        # Show available networks if WiFi is enabled
        if (self.network_client.wifi_device and
            self.network_client.wifi_device.wireless_enabled):
            self._populate_networks()

        self.networks_container.show_all()
        return False

    def _update_wifi_status(self):
        """Update WiFi status display"""
        if not self.network_client.wifi_device:
            self.wifi_subtitle.set_markup(
                "<span>No WiFi device available</span>"
            )
            self.wifi_switch.set_sensitive(False)
            return

        if self.network_client.wifi_device.wireless_enabled:
            self.wifi_switch.set_active(True)
            self.wifi_subtitle.set_markup(
                "<span>Find and connect to Wi-Fi networks</span>"
            )
            self.refresh_button.set_sensitive(True)
        else:
            self.wifi_switch.set_active(False)
            self.wifi_subtitle.set_markup(
                "<span>Wi-Fi is turned off</span>"
            )
            self.refresh_button.set_sensitive(False)

    def _populate_networks(self):
        """Populate the networks list"""
        if not self.network_client.wifi_device:
            self._show_status_message("No WiFi device available", "error")
            return

        access_points = self.network_client.wifi_device.access_points
        if not access_points:
            self._show_status_message(
                "No networks found\nClick 'Scan for Networks' to refresh",
                "info"
            )
            return

        # Sort access points by signal strength (connected first, then by strength)
        sorted_aps = sorted(
            access_points,
            key=lambda ap: (not ap.is_active, -ap.strength)
        )

        for ap in sorted_aps:
            self._create_network_widget(ap)

    def _show_status_message(self, message, message_type="info"):
        """Show a status message in the networks container"""
        status_box = Box(
            orientation="v",
            spacing=16,
            style="padding: 60px;"
        )
        status_box.set_halign(Gtk.Align.CENTER)
        status_box.set_valign(Gtk.Align.CENTER)

        # Icon based on message type
        if message_type == "error":
            icon_markup = icons.cloud_off
            message_label = Label(
                markup=f"<span size='medium'>{message}</span>",
                h_align="center",
                style="color: var(--error);"
            )
        elif message_type == "scanning":
            icon_markup = icons.loader
            message_label = Label(
                markup=f"<span size='medium'>{message}</span>",
                h_align="center",
                style="color: var(--blue);"
            )
        else:  # info
            icon_markup = icons.wifi_off
            message_label = Label(
                markup=f"<span size='medium'>{message}</span>",
                h_align="center",
                style="color: var(--outline);"
            )

        icon_label = Label(name="wifi-tab-icon", markup=icon_markup, style="font-size: 18px;")
        icon_label.set_halign(Gtk.Align.CENTER)
        status_box.add(icon_label)
        message_label.set_line_wrap(True)
        message_label.set_justify(Gtk.Justification.CENTER)
        message_label.set_halign(Gtk.Align.CENTER)
        status_box.add(message_label)

        self.networks_container.add(status_box)

    def _create_network_widget(self, ap):
        """Create widget for a single network"""
        # Main container for this network (Box to allow adding password entry)
        network_container = Box(orientation="v", spacing=0)

        # Clickable network button
        network_button = Button(
            style="background-color: transparent; border: none; padding: 0; margin: 0;"
        )
        network_button.connect("clicked", lambda btn, access_point=ap: self._on_network_clicked(access_point))

        # Network info row
        info_box = Box(orientation="h", spacing=12)
        info_box.set_margin_left(16)
        info_box.set_margin_right(16)
        info_box.set_margin_top(12)
        info_box.set_margin_bottom(12)

        # WiFi signal icon
        strength = ap.strength
        if strength >= 75:
            icon_markup = icons.wifi_3
        elif strength >= 50:
            icon_markup = icons.wifi_2
        elif strength >= 25:
            icon_markup = icons.wifi_1
        else:
            icon_markup = icons.wifi_0

        signal_label = Label(name="wifi-tab-icon", markup=icon_markup, style="font-size: 24px;")
        signal_label.set_size_request(30, -1)
        info_box.add(signal_label)

        # Network name
        network_name = ap.ssid
        if ap.is_active:
            network_markup = f"<b>{network_name}</b>\nConnected"
            network_label = Label(markup=network_markup, h_align="start", style="color: var(--foreground);")
        else:
            network_markup = f"{network_name}"
            network_label = Label(markup=network_markup, h_align="start", style="color: var(--foreground);")
        network_label.set_line_wrap(True)
        info_box.add(network_label)

        # Spacer to push lock icon to the right
        spacer = Box()
        spacer.set_hexpand(True)
        info_box.add(spacer)

        # Lock icon for secured networks
        if ap.requires_password:
            lock_label = Label(name="wifi-tab-icon", markup=icons.lock, style="font-size: 22px;")
            info_box.add(lock_label)

        network_button.add(info_box)
        network_container.add(network_button)

        # Store reference
        self.access_point_widgets[ap.ssid] = {
            'container': network_container,
            'button': network_button,
            'info_box': info_box,
            'network_label': network_label,
            'ap': ap
        }

        self.networks_container.add(network_container)

    def _on_network_clicked(self, ap):
        """Handle network item click"""
        if ap.is_active:
            # If connected, disconnect from this network
            self._disconnect_network(ap)
        else:
            # If not connected, check if password is needed
            if ap.requires_password and ap.ssid not in self.password_entries:
                # Show password entry interface
                self._show_password_entry(ap)
            else:
                # Connect directly (either no password needed or password already entered)
                self._connect_network(ap)

    def _on_wifi_switch_toggled(self, switch, gparam):
        """Handle WiFi switch toggle"""
        if self.network_client.wifi_device:
            is_active = switch.get_active()
            self.network_client.wifi_device.wireless_enabled = is_active
            GLib.timeout_add(500, self._refresh_networks)

    def _on_refresh_clicked(self, button):
        """Handle refresh button click"""
        if self.network_client.wifi_device and self.network_client.wifi_device.wireless_enabled:
            self.refresh_icon.set_markup(icons.loader)
            button.set_sensitive(False)

            # Clear current networks and show scanning message
            for child in self.networks_container.get_children():
                self.networks_container.remove(child)
            self._show_status_message("Scanning for networks...", "scanning")
            self.networks_container.show_all()

            self.network_client.wifi_device.scan()

            # Re-enable button after scan
            GLib.timeout_add(3000, lambda: [
                self.refresh_icon.set_markup(icons.reload),
                button.set_sensitive(True),
                self._refresh_networks()
            ])

    def _connect_network(self, ap):
        """Connect to a network"""
        # Get password if available (either from entry or stored)
        password = ""
        if ap.requires_password:
            if ap.ssid in self.password_entries:
                # Get password from stored entry widget
                password_widget = self.password_entries[ap.ssid]
                if hasattr(password_widget, 'get_text'):
                    password = password_widget.get_text()
                else:
                    password = str(password_widget)  # If it's stored as string
            else:
                # No password available, this shouldn't happen if called correctly
                print(f"Warning: No password available for {ap.ssid}")
                return

        self.connecting_to = ap.ssid

        # Hide password entry if shown
        if ap.ssid in self.password_entries:
            self._hide_password_entry(ap)

        # Update network widget to show connecting state
        if ap.ssid in self.access_point_widgets:
            network_label = self.access_point_widgets[ap.ssid]['network_label']
            network_label.set_markup(f"{ap.ssid}\nConnecting...")
            network_label.set_style("color: var(--blue);")

        try:
            # Connect to network
            result = self.network_client.wifi_device.connect_to_wifi(ap, password)
            if result is False:
                # Connection failed immediately
                self._show_connection_error(ap.ssid, "Failed to connect")
                self._reset_connection_state(ap.ssid)
            else:
                # Reset button after timeout if still connecting
                GLib.timeout_add(15000, lambda: self._reset_connection_state(ap.ssid))
        except Exception as e:
            self._show_connection_error(ap.ssid, f"Connection error: {str(e)}")
            self._reset_connection_state(ap.ssid)

    def _show_connection_error(self, ssid, error_message):

        try:
            
            subprocess.run([
                "notify-send",
                "WiFi Connection Failed",
                f"Failed to connect to {ssid}\n{error_message}",
                "--icon=network-wireless-offline",
                "--urgency=normal",
                "--app-name=WiFi"
            ], check=False)
        except Exception as e:
            print(f"Failed to send connection error notification: {e}")

    def _show_password_entry(self, ap):
        """Show password entry for a network"""
        if ap.ssid in self.access_point_widgets:
            container = self.access_point_widgets[ap.ssid]['container']

            # Check if password entry is already shown
            if len(container.get_children()) > 1:
                return  # Already showing password entry

            # Password entry row with theme styling
            password_box = Box(
                orientation="h",
                spacing=8,
                style="padding: 8px; margin: 4px 16px 8px 16px; border-radius: 8px;"
            )

            password_entry = Entry(
                placeholder_text="Enter network password",
                style="background-color: var(--surface-bright); border: 1px solid var(--outline); border-radius: 8px;"
            )
            password_entry.set_visibility(False)  # Hide password characters
            password_entry.set_hexpand(True)
            password_entry.connect("activate", lambda entry, access_point=ap: self._on_password_entered(access_point, entry))
            password_box.add(password_entry)

            # Show/Hide password toggle
            show_password_btn = Button(
                style="border-radius: 8px;"
            )
            self.show_password_icon = Label(name="wifi-tab-icon", markup=icons.spy,style="font-size: 18px;")
            show_password_btn.add(self.show_password_icon)
            show_password_btn.set_tooltip_text("Show/Hide password")
            show_password_btn.connect("clicked", lambda btn, entry=password_entry: self._toggle_password_visibility(entry, btn))
            password_box.add(show_password_btn)

            connect_btn = Button(
                style="border-radius: 8px;"
            )
            connect_icon = Label(name="wifi-tab-icon", markup=icons.connect,style="font-size: 18px;")
            connect_btn.add(connect_icon)
            connect_btn.connect("clicked", lambda btn, access_point=ap, entry=password_entry: self._on_password_entered(access_point, entry))
            password_box.add(connect_btn)

            cancel_btn = Button(
                style="border-radius: 8px;"
            )
            cancel_icon = Label(name="wifi-tab-icon", markup=icons.cancel,style="font-size: 18px;")
            cancel_btn.add(cancel_icon)
            cancel_btn.connect("clicked", lambda btn, access_point=ap: self._hide_password_entry(access_point))
            password_box.add(cancel_btn)

            container.add(password_box)
            container.show_all()

            # Store reference and focus
            self.password_entries[ap.ssid] = password_entry
            GLib.timeout_add(100, lambda: password_entry.grab_focus())

    def _toggle_password_visibility(self, entry, button):
        """Toggle password visibility"""
        current_visibility = entry.get_visibility()
        entry.set_visibility(not current_visibility)
        # Use spy icon for hidden, key icon for visible
        self.show_password_icon.set_markup(icons.key if not current_visibility else icons.spy)

    def _on_password_entered(self, ap, entry):
        """Handle password entry"""
        password = entry.get_text()
        self.password_entries[ap.ssid] = password
        self._hide_password_entry(ap)
        self._connect_network(ap)

    def _hide_password_entry(self, ap):
        """Hide password entry for a network"""
        if ap.ssid in self.access_point_widgets:
            container = self.access_point_widgets[ap.ssid]['container']
            children = container.get_children()
            if len(children) > 1:  # Remove password entry box
                container.remove(children[-1])

    def _disconnect_network(self, ap):
        """Disconnect from a network"""
        if self.network_client.wifi_device:
            self.network_client.wifi_device.disconnect_wifi()
            GLib.timeout_add(1000, self._refresh_networks)

    def _reset_connection_state(self, ssid):
        """Reset connection state for a network"""
        if ssid in self.access_point_widgets:
            # Reset the network label to normal state
            ap = self.access_point_widgets[ssid]['ap']
            network_label = self.access_point_widgets[ssid]['network_label']
            if ap.is_active:
                network_markup = f"<b>{ap.ssid}</b>\nConnected"
                network_label.set_style("color: var(--foreground);")
            else:
                network_markup = f"{ap.ssid}"
                network_label.set_style("color: var(--foreground);")
            network_label.set_markup(network_markup)

        self.connecting_to = None
        self._refresh_networks()
        return False
