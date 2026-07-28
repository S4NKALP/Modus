from fabric.utils import Gdk, GLib, idle_add, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.separator import Separator

from services import dns as dns_service
from services.network import NetworkClient
from shared.dialogs.sysauth_dialog import run_auth_dialog
from shared.widgets.smooth_switch import SmoothSwitch
from shared.window.animated_scrollwindow import AnimatedScrollable
from utils.functions import (
    get_wifi_connecting_icon,
    get_wifi_icon_for_strength,
    spawn_detached,
)
from utils.gtk_utils import svg_file

DEFAULT_DNS_PROVIDERS = [
    {"label": "Cloudflare", "primary": "1.1.1.1", "secondary": "1.0.0.1"},
    {"label": "Google", "primary": "8.8.8.8", "secondary": "8.8.4.4"},
    {"label": "OpenDNS", "primary": "208.67.222.222", "secondary": "208.67.220.220"},
    {"label": "AdGuard", "primary": "94.140.14.14", "secondary": "94.140.15.15"},
    {"label": "Quad9", "primary": "9.9.9.9", "secondary": "149.112.112.112"},
]


class WifiNetworkSlot(Box):
    def __init__(
        self, access_point, wifi_service, network_service=None, parent=None, **kwargs
    ):
        super().__init__(name="wifi-network-slot", **kwargs)
        self.access_point = access_point
        self.wifi_service = wifi_service
        self.network_service = network_service
        self.parent = parent  # Reference to control center

        self.ssid = access_point.ssid
        self.bssid = access_point.bssid
        self.strength = access_point.strength
        self.icon_name = access_point.icon

        self.is_connected = access_point.is_active
        self._anim_state = None  # "connecting" | "disconnecting" | None

        if self.is_connected:
            self.add_style_class("connected")

        wifi_icon_path = get_wifi_icon_for_strength(self.strength)
        self.dimage = svg_file(wifi_icon_path, size=28)
        self.wifi_icon_box = Box(
            children=[self.dimage],
            style_classes=["wifi-icon-box"],
        )

        if self.is_connected:
            self.dimage.add_style_class("connected")

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

        start_box = Box(
            orientation="h",
            spacing=8,
        )
        start_box.children = [self.wifi_icon_box, self.network_label]
        if self.lock_icon:
            start_box.children.append(self.lock_icon)

        self.children = [
            Button(
                child=start_box,
                h_expand=True,
                name="wifi-network-button",
                on_clicked=lambda *_: self.toggle_connecting(),
            )
        ]

        self.on_changed()

    def update_ap(self, access_point):
        """Update existing slot with new AP data without recreating it"""
        self.access_point = access_point
        self.bssid = access_point.bssid
        self.strength = access_point.strength
        self.is_connected = access_point.is_active

        if access_point.is_active:
            self.dimage.remove_style_class("connecting")
            self.dimage.remove_style_class("disconnecting")
            self._anim_state = None

        if self._anim_state is None:
            wifi_icon_path = get_wifi_icon_for_strength(self.strength)
            self.dimage.set_from_file(wifi_icon_path)

        self.on_changed()

    def toggle_connecting(self):
        is_currently_connected = self.access_point.is_active

        if is_currently_connected:
            connecting_icon = get_wifi_connecting_icon()
            self.dimage.set_from_file(connecting_icon)
            self.dimage.add_style_class("disconnecting")
            self._anim_state = "disconnecting"

            if self.network_service:
                self.network_service.disconnect_wifi()
            self.is_connected = False
            GLib.timeout_add(500, lambda: self._reset_disconnect_state())
        else:
            is_saved = self.network_service and self.network_service.is_network_saved(
                self.ssid
            )

            if self.access_point.requires_password and not is_saved:
                self._show_password_dialog()
            else:
                connecting_icon = get_wifi_connecting_icon()
                self.dimage.set_from_file(connecting_icon)
                self.dimage.add_style_class("connecting")
                self._anim_state = "connecting"

                def on_open_connection_result(success, message):
                    if not self.get_parent():
                        return
                    if success:
                        GLib.timeout_add(500, lambda: self._reset_connect_state())
                    else:
                        self._reset_connect_state()
                        if message == "Wrong password":
                            self._show_password_dialog()

                try:
                    if self.network_service:
                        self.network_service.connect_wifi(
                            self.access_point, callback=on_open_connection_result
                        )
                except Exception as e:
                    logger.error(
                        f"[WiFi] Failed to connect to {self.access_point.ssid}: {e}"
                    )
                    self._reset_connect_state()

    def _reset_disconnect_state(self):
        """Reset visual state after disconnect operation"""
        self.dimage.remove_style_class("disconnecting")
        self._anim_state = None
        wifi_icon_path = get_wifi_icon_for_strength(self.strength)
        self.dimage.set_from_file(wifi_icon_path)
        self.on_changed()
        return False

    def _reset_connect_state(self):
        """Reset visual state after connect operation"""
        self.dimage.remove_style_class("connecting")
        self._anim_state = None
        wifi_icon_path = get_wifi_icon_for_strength(self.strength)
        self.dimage.set_from_file(wifi_icon_path)
        self.on_changed()
        return False

    def on_changed(self, *_):
        self.is_connected = self.access_point.is_active
        if self.is_connected:
            self.add_style_class("connected")
        else:
            self.remove_style_class("connected")

        if self.is_connected:
            self.wifi_icon_box.add_style_class("wifi-icon-box-connected")
        else:
            self.wifi_icon_box.remove_style_class("wifi-icon-box-connected")
        return

    def _show_password_dialog(self):
        """Show the WiFi password dialog"""
        if self.parent and hasattr(self.parent, "hide_controlcenter"):
            self.parent.hide_controlcenter()

        run_auth_dialog(
            action_id=self.ssid,
            message=f'Wi-Fi network "{self.ssid}" requires a password.',
            icon_name="network-wireless-symbolic",
            on_result=self._on_password_result,
        )

    def _on_password_result(self, password):
        """Handle password dialog result"""
        if password is None:
            self._reset_connect_state()
            return

        if password.strip():
            connecting_icon = get_wifi_connecting_icon()
            self.dimage.set_from_file(connecting_icon)
            self.dimage.add_style_class("connecting")
            self._anim_state = "connecting"

            def on_connection_result(success, message):
                """Handle the connection result"""
                if not self.get_parent():
                    return
                if success:
                    self.is_connected = True
                    GLib.timeout_add(500, lambda: self._reset_connect_state())
                else:
                    self._reset_connect_state()
                    self._show_connection_error(message)

                self.on_changed()

            try:
                if self.network_service:
                    self.network_service.connect_wifi_with_password(
                        self.access_point, password, callback=on_connection_result
                    )
            except Exception as e:
                logger.error(
                    f"[WiFi] Failed to initiate connection to {self.access_point.ssid}: {e}"
                )
                self._reset_connect_state()
                self._show_connection_error("Connection failed. Please try again.")
                self.on_changed()

    def _show_connection_error(self, message="Incorrect password. Please try again."):
        """Show connection error and re-prompt for password"""
        run_auth_dialog(
            action_id=self.ssid,
            message=f'Wi-Fi network "{self.ssid}" requires a password.',
            icon_name="network-wireless-symbolic",
            on_result=self._on_password_result,
            error_message=message,
        )
        return False  # Don't repeat if called from GLib.timeout_add


class DnsSwitcher:
    """DNS provider switcher with predefined and manual options.

    Builds two widgets: ``button`` (the header row) and ``content_box``
    (the expandable panel).  Both should be added as separate children
    of the parent container, matching how Other Networks is structured.
    """

    def __init__(self):
        self._current_dns = []
        self._provider_buttons = {}
        self._is_expanded = False

        self._dns_label = Label(
            label="Automatic",
            name="dns-current-label",
            h_align="end",
        )

        self.button = Button(
            child=CenterBox(
                start_children=Label("DNS", h_align="start"),
                end_children=self._dns_label,
            ),
            name="wifi-other-button",
            on_clicked=self._toggle_expanded,
        )

        self.content_box = Box(
            orientation="vertical",
            spacing=4,
            name="dns-content",
        )
        self.content_box.set_visible(False)

        auto_row = self._make_provider_row("Automatic (DHCP)", "", is_auto=True)
        self.content_box.pack_start(auto_row, False, False, 0)

        for provider in DEFAULT_DNS_PROVIDERS:
            row = self._make_provider_row(
                provider["label"],
                f"{provider['primary']}, {provider['secondary']}",
                is_auto=False,
                primary=provider["primary"],
                secondary=provider["secondary"],
            )
            self.content_box.pack_start(row, False, False, 0)

        self._load_current_dns()

    def _make_provider_row(
        self,
        label,
        subtitle,
        is_auto=False,
        primary=None,
        secondary=None,
    ):
        check_icon = Image(
            icon_name="object-select-symbolic",
            size=14,
            name="dns-check-icon",
        )
        check_icon.set_no_show_all(True)
        check_icon.hide()

        title_label = Label(
            label=label, h_align="start", h_expand=True, name="dns-provider-name"
        )

        children = [title_label]
        if subtitle:
            children.append(
                Label(
                    label=subtitle,
                    h_align="end",
                    name="dns-provider-address",
                )
            )
        children.append(check_icon)

        row_button = Button(
            child=Box(orientation="h", spacing=8, children=children),
            name="dns-provider-button",
        )

        if is_auto:
            row_button.connect("clicked", lambda *_: self._on_auto_selected())
        else:
            row_button.connect(
                "clicked",
                lambda *_: self._on_provider_selected(primary, secondary),
            )

        row_button._dns_check = check_icon
        row_button._dns_primary = primary
        self._provider_buttons[primary or "auto"] = row_button
        return row_button

    def _toggle_expanded(self, *_):
        self._is_expanded = not self._is_expanded
        self.content_box.set_visible(self._is_expanded)

    def _load_current_dns(self):
        dns_service.get_dns(callback=self._on_dns_loaded)

    def _on_dns_loaded(self, dns_servers):
        self._current_dns = dns_servers or []
        self._update_checkmarks()
        self._update_dns_label()

    def _update_checkmarks(self):
        key = self._current_dns[0] if self._current_dns else "auto"
        for btn_key, btn in self._provider_buttons.items():
            check = getattr(btn, "_dns_check", None)
            if check:
                if btn_key == key:
                    check.show()
                else:
                    check.hide()

    def _update_dns_label(self):
        if not self._current_dns:
            self._dns_label.set_label("Automatic")
        elif len(self._current_dns) == 1:
            self._dns_label.set_label(self._current_dns[0])
        else:
            self._dns_label.set_label(
                f"{self._current_dns[0]} +{len(self._current_dns) - 1}"
            )

    def _on_auto_selected(self):
        self._current_dns = []
        self._update_checkmarks()
        self._update_dns_label()
        dns_service.set_dns([], callback=self._on_dns_applied)

    def _on_provider_selected(self, primary, secondary):
        dns = [primary]
        if secondary:
            dns.append(secondary)
        self._current_dns = dns
        self._update_checkmarks()
        self._update_dns_label()
        dns_service.set_dns(dns, callback=self._on_dns_applied)

    def _on_dns_applied(self, success):
        if not success:
            self._load_current_dns()

    def refresh_dns(self):
        self._load_current_dns()


class WifiConnections(Box):
    def __init__(self, parent, show_back_button=True, network_service=None, **kwargs):
        super().__init__(
            spacing=8,
            orientation="vertical",
            name="wifi-connections",
            **kwargs,
        )

        self.parent = parent
        self.network_service = network_service or NetworkClient()
        self.wifi_service = None
        self.is_scanning = False  # Track scanning state
        self._update_in_progress = False  # Prevent concurrent updates
        self._destroyed = False  # Track if widget is destroyed
        self._signal_ids = []  # Track all service signal IDs for cleanup
        self._network_ready_fired = False  # Guard against duplicate device-ready
        self._pending_toggle = None  # Force toggle to target after stale revert

        if self.network_service and self.network_service.wifi_device:
            idle_add(self.on_network_ready)
        else:
            self._signal_ids.append(
                (
                    self.network_service,
                    self.network_service.connect("device-ready", self.on_network_ready),
                )
            )

        # Create pull-to-refresh indicator
        self.refresh_indicator = Label(
            name="wifi-refresh-indicator",
            label="↓ Pull to scan for networks",
            h_align="center",
            visible=False,
            style="color: #fff; font-size: 12px; padding: 5px;",
        )

        title_children = []
        if show_back_button:
            title_children.append(
                Button(
                    image=svg_file("misc/chevron-left.svg", size=10),
                    on_clicked=lambda *_: self.parent.close_wifi(),
                )
            )
        title_children.append(Label("Wi-Fi", name="wifi-title"))

        self.title = Box(
            orientation="h",
            children=title_children,
        )

        self.toggle_button = SmoothSwitch(
            name="toggle-button",
            on_user_toggle=lambda active: self.on_toggle_changed(
                self.toggle_button, active
            ),
        )

        # Create Known Network section
        self.known_networks_label = Label(
            label="Known Network", h_align="start", name="networks-title"
        )
        self.known_networks = Box(
            spacing=4, orientation="vertical", name="known-networks"
        )
        self.known_networks_scrolled = AnimatedScrollable(
            min_content_size=(303, 0),
            max_content_size=(303, 200),
            child=self.known_networks,
            overlay_scroll=True,
            animate=False,
        )

        # Create "No networks available" message
        self.no_networks_label = Label(
            label="No networks available",
            h_align="center",
            name="no-networks-label",
            visible=False,
        )

        self.other_networks_button = Button(
            child=CenterBox(
                start_children=Label("Other Networks", h_align="start"),
                end_children=self.refresh_indicator,
            ),
            name="wifi-other-button",
            on_clicked=self.toggle_other_networks,
        )
        self.other_networks = Box(spacing=4, orientation="vertical")

        # Create scrolled window for other networks
        self.other_networks_scrolled = AnimatedScrollable(
            min_content_size=(303, 0),
            max_content_size=(303, 300),
            child=self.other_networks,
            overlay_scroll=True,
            animate=False,
        )
        self.other_networks.set_visible(False)

        # Add pull-to-refresh functionality to scrolled window
        self.setup_pull_to_refresh()

        # Create More Settings button (same style as Other Networks button)
        self.more_settings_button = Button(
            child=Label("More Settings", h_align="start"),
            name="wifi-other-button",
            on_clicked=self.open_network_settings,
        )

        # DNS Switcher
        self.dns_switcher = DnsSwitcher()

        self.children = [
            CenterBox(
                start_children=self.title,
                end_children=self.toggle_button,
                name="wifi-widget-top",
            ),
            Separator(orientation="h", name="separator"),
            self.known_networks_label,
            self.known_networks_scrolled,
            self.no_networks_label,
            Separator(orientation="h", name="separator"),
            self.other_networks_button,
            self.other_networks_scrolled,
            Separator(orientation="h", name="separator"),
            self.dns_switcher.button,
            self.dns_switcher.content_box,
            Separator(orientation="h", name="separator"),
            self.more_settings_button,
        ]

        self.connect("destroy", self.on_destroy)
        self.connect("unmap", self.on_hide)
        self.connect("map", self.on_show)

    def on_show(self, *_):
        """Called when the widget is mapped (popup opened)"""
        if self.wifi_service:
            self.wifi_service.scan()
            self.force_network_refresh()
        if self.dns_switcher:
            self.dns_switcher.refresh_dns()

    def on_hide(self, *_):
        """Called when the widget is hidden (popup closed)"""
        self._cancel_pending_refresh()
        if self.other_networks.get_visible():
            self.other_networks.set_visible(False)
            self.other_networks_scrolled.snap_to_size(0)
        if self.dns_switcher and self.dns_switcher._is_expanded:
            self.dns_switcher._is_expanded = False
            self.dns_switcher.content_box.set_visible(False)

    def toggle_other_networks(self, *_):
        """Toggle the visibility of other networks section"""
        current_state = self.other_networks.get_visible()
        self._cancel_pending_refresh()
        if current_state:
            self.other_networks.set_visible(False)
            self.other_networks_scrolled.snap_to_size(0)
        else:
            self.other_networks.set_visible(True)
            if self.wifi_service:
                self.wifi_service.scan()
            # Defer refresh until after the height animation completes
            idle_add(self._refresh_after_animation)

    def _cancel_pending_refresh(self):
        if hasattr(self, "_anim_finished_handler") and self._anim_finished_handler:
            try:
                self.other_networks_scrolled.height_animator.disconnect(
                    self._anim_finished_handler
                )
            except Exception as e:
                logger.warning(
                    f"[wifi] self.other_networks_scrolled.height_animator.disconnect( ... failed: {e}"
                )
            self._anim_finished_handler = None

    def _refresh_after_animation(self):
        if self._destroyed:
            return False
        anim = self.other_networks_scrolled.height_animator
        if anim.playing:
            self._anim_finished_handler = anim.connect(
                "finished",
                lambda *_: (
                    self.force_network_refresh() if not self._destroyed else None
                ),
            )
        else:
            self.force_network_refresh()
        return False

    def on_network_ready(self, *_):
        """Called when network service is ready"""
        if self._network_ready_fired and self.wifi_service:
            return
        wifi = self.network_service.wifi_device
        if not wifi:
            return
        self._network_ready_fired = True
        self.wifi_service = wifi
        # Defer the initial sync: the D-Bus cached property may not yet be
        # populated when device-ready fires inside _init_devices, causing
        # enabled to read as False even when WiFi is on.
        idle_add(
            lambda: (
                self.toggle_button.set_active(self.wifi_service.enabled)
                if self.wifi_service
                else False
            )
        )

        self._signal_ids.append(
            (
                self.wifi_service,
                self.wifi_service.connect(
                    "notify::enabled", self.on_wifi_enabled_changed
                ),
            )
        )
        self._signal_ids.append(
            (
                self.wifi_service,
                self.wifi_service.connect("changed", self.update_networks),
            )
        )

        # Initial network update
        self.update_networks()

        # Trigger initial scan so AP list is populated
        self.wifi_service.scan()

    def on_toggle_changed(self, toggle_button, *_):
        """Handle WiFi toggle button changes"""
        if self.wifi_service:
            target = toggle_button.get_active()
            self._pending_toggle = target
            self.wifi_service.enabled = target
            self.toggle_button.set_active(target)

    def on_wifi_enabled_changed(self, *_):
        """Handle WiFi enabled state changes"""
        if self.wifi_service:
            if self._pending_toggle is not None:
                self.toggle_button.set_active(self._pending_toggle)
                self._pending_toggle = None
            else:
                self.toggle_button.set_active(self.wifi_service.enabled)

    def open_network_settings(self, *_):
        """Open NetworkManager connection editor"""
        try:
            spawn_detached(["nm-connection-editor"])
            if self.parent and hasattr(self.parent, "hide_controlcenter"):
                self.parent.hide_controlcenter()
        except FileNotFoundError as e:
            logger.warning(
                f"[wifi] spawn_detached(['nm-connection-editor']) failed: {e}"
            )
        except Exception as e:
            logger.error(f"[WiFi] Failed to open network settings: {e}")

    def update_networks(self, *_):
        """Update the list of available networks"""
        # Prevent concurrent updates and check if destroyed
        if self._update_in_progress or self._destroyed or not self.wifi_service:
            return

        self._update_in_progress = True

        try:
            # When WiFi is disabled, clear all network slots
            if not self.wifi_service.enabled:
                for child in self.known_networks.get_children():
                    self.known_networks.remove(child)
                for child in self.other_networks.get_children():
                    self.other_networks.remove(child)
                self.known_networks_scrolled.set_visible(True)
                self.no_networks_label.set_visible(True)
                self.other_networks_button.set_visible(True)
                return

            access_points = self.wifi_service.access_points
            known_networks = []
            other_networks = []

            for access_point in access_points:
                if access_point.ssid and access_point.ssid != "Unknown":
                    if access_point.is_active or self._is_saved_network(access_point):
                        known_networks.append(access_point)
                    else:
                        other_networks.append(access_point)

            # Get existing networks
            existing_known = {
                child.ssid: child for child in self.known_networks.get_children()
            }
            existing_other = {
                child.ssid: child for child in self.other_networks.get_children()
            }

            for access_point in known_networks:
                if not self._destroyed:
                    if access_point.ssid in existing_known:
                        slot = existing_known.pop(access_point.ssid)
                        slot.update_ap(access_point)
                    elif access_point.ssid in existing_other:
                        slot = existing_other.pop(access_point.ssid)
                        slot.update_ap(access_point)
                        self.other_networks.remove(slot)
                        self.known_networks.add(slot)
                    else:
                        network_slot = WifiNetworkSlot(
                            access_point,
                            self.wifi_service,
                            network_service=self.network_service,
                            parent=self.parent,
                        )
                        self.known_networks.add(network_slot)

            for access_point in other_networks:
                if not self._destroyed:
                    if access_point.ssid in existing_other:
                        slot = existing_other.pop(access_point.ssid)
                        slot.update_ap(access_point)
                    elif access_point.ssid in existing_known:
                        slot = existing_known.pop(access_point.ssid)
                        slot.update_ap(access_point)
                        self.known_networks.remove(slot)
                        self.other_networks.add(slot)
                    else:
                        network_slot = WifiNetworkSlot(
                            access_point,
                            self.wifi_service,
                            network_service=self.network_service,
                            parent=self.parent,
                        )
                        self.other_networks.add(network_slot)

            for slot in existing_known.values():
                if hasattr(slot, "access_point"):
                    slot.strength = 0
                    if slot._anim_state is None:
                        slot.dimage.set_from_file(get_wifi_icon_for_strength(0))

            for slot in existing_other.values():
                if hasattr(slot, "access_point"):
                    slot.strength = 0
                    if slot._anim_state is None:
                        slot.dimage.set_from_file(get_wifi_icon_for_strength(0))

            if not self._destroyed:
                has_known_networks = len(known_networks) > 0
                has_other_networks = len(other_networks) > 0
                has_any_networks = has_known_networks or has_other_networks

                self.known_networks_scrolled.set_visible(True)
                self.no_networks_label.set_visible(not has_any_networks)
                self.other_networks_button.set_visible(True)  # Always visible
                self.refresh_network_states()

                if self.other_networks.get_visible():
                    other_children = self.other_networks.get_children()
                    if other_children:
                        nat_h = self.other_networks.get_preferred_height()[1]
                        if nat_h > 0:
                            self.other_networks_scrolled.snap_to_size(min(nat_h, 300))

        except Exception as e:
            logger.error(f"[WiFi] Error during update_networks: {e}")
        finally:
            self._update_in_progress = False

    def _is_saved_network(self, access_point):
        """Check if a network is saved/known using NetworkManager connections"""
        if not self.network_service:
            return False
        ssid = access_point.ssid
        if not ssid or ssid == "Unknown":
            return False
        return self.network_service.is_network_saved(ssid)

    def refresh_network_states(self, *_):
        """Refresh connection states for all network slots"""
        for child in self.known_networks.get_children():
            if hasattr(child, "on_changed"):
                child.on_changed()

        for child in self.other_networks.get_children():
            if hasattr(child, "on_changed"):
                child.on_changed()

    def force_network_refresh(self):
        """Force an immediate refresh of the network list"""
        if self._update_in_progress or self._destroyed:
            return

        try:
            self.update_networks()
        except Exception as e:
            logger.error(f"[WiFi] Error during forced network refresh: {e}")

    def setup_pull_to_refresh(self):
        """Setup pull-to-refresh gesture for the scrolled window"""
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
        if self.vadjustment.get_value() <= 0:
            if event.direction == Gdk.ScrollDirection.UP:
                if self.wifi_service:
                    self.wifi_service.scan()
                    self.force_network_refresh()
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
                if self.wifi_service:
                    self.wifi_service.scan()
                    self.force_network_refresh()
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
        self._destroyed = True
        self._cancel_pending_refresh()
        for obj, sig_id in self._signal_ids:
            try:
                obj.disconnect(sig_id)
            except Exception as e:
                logger.error(f"[WiFi] Failed to disconnect signal {sig_id}: {e}")
        self._signal_ids.clear()
        self.wifi_service = None
        self.network_service = None

    def close_wifi(self):
        """Called when WiFi panel is being closed"""
        if self.other_networks.get_visible():
            self.other_networks.set_visible(False)
            self.other_networks_scrolled.snap_to_size(0)
        if self.dns_switcher and self.dns_switcher._is_expanded:
            self.dns_switcher._is_expanded = False
            self.dns_switcher.content_box.set_visible(False)
