from collections.abc import Iterator

from fabric.utils import Gdk, GLib, idle_add, logger, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin
from services import NetworkClient


class NetworkManagerPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "network"

    @property
    def icon(self) -> str:
        return "network-workgroup-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["net"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self.network_client = NetworkClient()

        self._items: list[dict] = []
        self._awaiting_password: bool = False
        self._pending_ssid: str | None = None
        self._current_search_text: str = ""
        self._signal_refresh_handler: int = 0
        self._is_active: bool = False
        self._signal_connections: list[int] = []

        self._wire_signals()

    def on_search(self, text: str) -> None:
        self.query_networks(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        if self._signal_refresh_handler:
            GLib.source_remove(self._signal_refresh_handler)
            self._signal_refresh_handler = 0

        if self.network_client and self._signal_connections:
            for connection_id in self._signal_connections:
                self.network_client.disconnect(connection_id)
            self._signal_connections.clear()

    def _wire_signals(self) -> None:
        self._signal_connections.append(
            self.network_client.connect("changed", self._on_network_changed)
        )
        wifi_device = self.network_client.wifi_device
        if wifi_device:
            self._signal_connections.append(
                wifi_device.connect("changed", self._on_network_changed)
            )
            self._signal_connections.append(
                wifi_device.connect("ap-added", self._on_network_changed)
            )
            self._signal_connections.append(
                wifi_device.connect("ap-removed", self._on_network_changed)
            )

    def _on_network_changed(self, *args, **kwargs):
        if self._awaiting_password or not self._is_active:
            return
        if self._signal_refresh_handler:
            return
        self._signal_refresh_handler = GLib.timeout_add(250, self._refresh_timeout)

    def _refresh_timeout(self) -> bool:
        self._signal_refresh_handler = 0
        if self._is_active or self._awaiting_password:
            self._refresh_query()
        return False

    def query_networks(self, text: str) -> None:
        self._is_active = True
        self.handler.start("networks")
        self._current_search_text = text

        if text.lower() == "scan":
            self._perform_scan()
            return

        self._items = self._get_network_items(text)
        if not self._items:
            self._show_no_connections()
            return

        self._query_handler = idle_add(
            self._bake_next_slot, iter(self._items), pin=True
        )

    def _get_network_items(self, search_text: str) -> list[dict]:
        items = []
        wifi_device = self.network_client.wifi_device

        if not wifi_device:
            return items

        for ap in wifi_device.access_points:
            if search_text and not ap.ssid.lower().startswith(search_text.lower()):
                continue
            if not ap.ssid or ap.ssid == "Unknown":
                continue
            items.append(
                {
                    "type": "ap",
                    "name": ap.ssid,
                    "ap": ap,
                    "device": wifi_device._device,
                    "active": ap.is_active,
                }
            )

        return items

    def _perform_scan(self) -> None:
        wifi_device = self.network_client.wifi_device
        if not wifi_device:
            self._show_no_wifi_device()
            return

        self._show_scanning_feedback()
        wifi_device.scan()
        GLib.timeout_add(2000, self._scan_complete_callback)

    def _show_scanning_feedback(self) -> None:
        """Show feedback that scanning is in progress."""
        self.handler.slot_ready(
            Button(
                style_classes="app-slot network-scanning",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Image(icon_name="network-wireless-acquiring-symbolic", size=32),
                        Label(
                            label="Scanning for networks...",
                            style_classes="network-scanning-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="Scanning for available WiFi networks",
            ),
            "networks",
        )
        self.handler.done()

    def _show_no_wifi_device(self) -> None:
        """Show message when no WiFi device is available."""
        self.handler.slot_ready(
            Button(
                style_classes="app-slot network-no-wifi",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Image(icon_name="network-wireless-offline-symbolic", size=32),
                        Label(
                            label="No WiFi device available",
                            style_classes="network-no-wifi-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="WiFi device not found or disabled",
            ),
            "networks",
        )
        self.handler.done()

    def _scan_complete_callback(self) -> bool:
        """Callback after scan completion to refresh the network list."""
        if self._is_active and self._current_search_text.lower() == "scan":
            # Clear the scanning feedback and show updated results
            if hasattr(self.handler, "clear_viewport"):
                self.handler.clear_viewport()
            # Show all available networks after scan (don't clear input to preserve /n prefix)
            self._current_search_text = ""
            self._items = self._get_network_items("")
            if not self._items:
                self._show_no_connections()
            else:
                self._query_handler = idle_add(
                    self._bake_next_slot, iter(self._items), pin=True
                )
        return False

    def _refresh_query(self) -> None:
        if self._awaiting_password or not self._is_active:
            return
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        self.query_networks(self._current_search_text)

    def _show_no_connections(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot network-no-connections",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Image(icon_name="network-offline-symbolic", size=32),
                        Label(
                            label="No connections found",
                            style_classes="network-no-connections-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="No NetworkManager connections available",
            ),
            "networks",
        )
        self.handler.done()

    def _bake_next_slot(self, iterator: Iterator[dict]) -> bool:
        item = next(iterator, None)
        if item is None:
            idle_add(self.handler.done)
            return False
        self._create_slot(item)
        return True

    def _create_slot(self, item: dict) -> None:
        ap = item["ap"]
        name = ap.ssid
        is_active = ap.is_active
        strength = ap.strength
        requires_password = ap.requires_password

        icon_name = self._get_wifi_icon(strength)
        subtitle = f"Signal: {strength}%"
        if requires_password:
            subtitle = f"Secured • {subtitle}"
        if is_active:
            subtitle = f"Connected • {subtitle}"

        slot_content = Box(
            orientation="h",
            spacing=12,
            children=[
                Image(icon_name=icon_name, h_align="start", size=32),
                Box(
                    orientation="v",
                    children=[
                        Label(
                            label=("* " + name) if is_active else name,
                            style_classes="network-name",
                            h_align="start",
                        ),
                        Label(
                            label=subtitle,
                            style_classes="network-subtitle",
                            h_align="start",
                        ),
                    ],
                ),
            ],
        )

        slot_widget = Button(
            style_classes="app-slot network-slot",
            child=slot_content,
            tooltip_text=self._get_tooltip_text(is_active, name),
            on_clicked=lambda *_: self._handle_slot_click(item),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, item=item: self._on_slot_key_press(
                widget, event, item
            ),
        )

        self.handler.slot_ready(slot_widget, "networks")

    def _get_tooltip_text(self, is_active: bool, ssid: str) -> str:
        if is_active:
            return (
                f"Enter: Disconnect\nShift+Enter: Remove saved connection\nSSID: {ssid}"
            )
        else:
            return f"Enter: Connect\nShift+Enter: Remove saved connection\nSSID: {ssid}"

    def _on_slot_key_press(self, widget, event, item: dict) -> bool:
        if not event:
            return False

        if (
            event.keyval == Gdk.KEY_Return or event.keyval == Gdk.KEY_KP_Enter
        ) and event.state & Gdk.ModifierType.SHIFT_MASK:
            self._remove_saved_connection(item)
            return True

        return False

    def _remove_saved_connection(self, item: dict) -> None:
        ap = item["ap"]
        ssid = ap.ssid

        wifi_device = self.network_client.wifi_device
        if not wifi_device:
            logger.error("No WiFi device available")
            return

        client = self.network_client._client
        connections = client.get_connections()

        for connection in connections:
            wifi_setting = connection.get_setting_wireless()
            if wifi_setting:
                connection_ssid = wifi_setting.get_ssid()
                if connection_ssid:
                    connection_ssid_str = connection_ssid.get_data().decode("utf-8")
                    if connection_ssid_str == ssid:
                        try:
                            connection.delete_async(
                                None, self._on_connection_deleted, ssid
                            )
                            logger.info(f"Removing saved connection for '{ssid}'")
                            return
                        except Exception as e:
                            logger.error(
                                f"Failed to remove connection for '{ssid}': {e}"
                            )
                            return

        logger.warning(f"No saved connection found for '{ssid}'")

    def _on_connection_deleted(self, connection, result, ssid: str) -> None:
        try:
            connection.delete_finish(result)
            logger.info(f"Successfully removed saved connection for '{ssid}'")
            if self._is_active:
                self._refresh_query()
        except Exception as e:
            logger.error(f"Failed to delete connection for '{ssid}': {e}")

    def _get_wifi_icon(self, strength: int) -> str:
        if strength >= 80:
            return "network-wireless-signal-excellent"
        elif strength >= 60:
            return "network-wireless-signal-good"
        elif strength >= 40:
            return "network-wireless-signal-ok"
        elif strength >= 20:
            return "network-wireless-signal-weak"
        else:
            return "network-wireless-signal-none"

    def _handle_slot_click(self, item: dict) -> None:
        if item.get("active"):
            wifi_device = self.network_client.wifi_device
            if wifi_device:
                wifi_device.disconnect_wifi()
            self.handler.launched()
        else:
            ap = item["ap"]
            if ap.requires_password:
                self._prompt_password(ap.ssid)
            else:
                self._connect_to_wifi(ap.ssid, "")
                self.handler.launched()

    def _prompt_password(self, ssid: str) -> None:
        self._awaiting_password = True
        self._pending_ssid = ssid
        self.handler.start("networks")
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()

        self.handler.slot_ready(
            Button(
                style_classes="app-slot network-help",
                child=Box(
                    orientation="v",
                    spacing=8,
                    children=[
                        Label(
                            label=f"Password for {ssid}",
                            style_classes="network-help-text",
                            h_align="center",
                        ),
                        Label(
                            label="Enter=Submit • Empty=Cancel",
                            style_classes="network-subtext",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "networks",
        )
        self.handler.done()

    @property
    def is_password_mode(self) -> bool:
        return self._awaiting_password and self._pending_ssid is not None

    def is_waiting_for_password(self) -> bool:
        return self._awaiting_password and self._pending_ssid

    def submit_password(self, password: str) -> None:
        if not self._pending_ssid:
            return

        ssid = self._pending_ssid
        self._awaiting_password = False
        self._pending_ssid = None

        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        self._connect_to_wifi(ssid, password)
        self._is_active = False
        self.handler.launched()

    def cancel_password(self) -> None:
        self._awaiting_password = False
        self._pending_ssid = None
        self._is_active = False

        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        self.query_networks(self._current_search_text)

    def _connect_to_wifi(self, ssid: str, password: str) -> None:
        wifi_device = self.network_client.wifi_device
        if not wifi_device:
            return

        target_ap = None
        for ap in wifi_device.access_points:
            if ap.ssid == ssid:
                target_ap = ap
                break

        if not target_ap:
            return

        def callback(success: bool, message: str):
            if success:
                logger.info(f"Connected to '{ssid}'")
            else:
                logger.error(f"Failed to connect to '{ssid}': {message}")

        wifi_device.connect_to_wifi(target_ap, password, callback)
