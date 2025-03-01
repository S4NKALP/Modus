from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.scrolledwindow import ScrolledWindow
from services import NetworkClient
import utils.icons as icons


class WifiNetworkSlot(CenterBox):
    def __init__(self, network, client: NetworkClient, **kwargs):
        super().__init__(name="wifi-device", **kwargs)
        self.network = network
        self.client = client
        self.connecting = False  # Tracks if we are connecting/disconnecting

        self.connection_icon = Label(name="wifi-connection", markup=icons.wifi_off)
        self.connect_button = Button(
            name="wifi-connect",
            label="Connect",
            on_clicked=self.on_connect_clicked,
        )

        self.start_children = [
            Box(
                spacing=8,
                children=[
                    Image(icon_name=network.get("icon-name"), size=32),
                    Label(label=network.get("ssid")),
                    self.connection_icon,
                ],
            )
        ]
        self.end_children = self.connect_button

        self.visible = True
        self.show_all()

        # Listen to WiFi state changes
        self.client.wifi_device.connect("changed", lambda *_: self.update_status())

        self.update_status()

    def on_connect_clicked(self, *_):
        connected = self.network.get("ssid") == self.client.wifi_device.ssid
        if connected:
            self.connect_button.set_label("Disconnecting...")
            self.client.wifi_device.enabled = False  # Disables WiFi to disconnect
        else:
            self.connect_button.set_label("Connecting...")
            self.client.connect_wifi_bssid(self.network.get("bssid"))

        self.connecting = True
        self.connect_button.sensitive = False

    def update_status(self):
        state = self.client.wifi_device.state
        connected = self.network.get("ssid") == self.client.wifi_device.ssid

        if self.connecting:
            if state in ["activating"]:
                self.connect_button.set_label("Connecting...")
            elif state in ["deactivating"]:
                self.connect_button.set_label("Disconnecting...")
            else:
                self.connecting = False
                self.connect_button.sensitive = True

        if not self.connecting:
            self.connection_icon.set_markup(icons.wifi if connected else icons.wifi_off)
            self.connect_button.set_label("Disconnect" if connected else "Connect")


class WifiManager(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="wifi",
            spacing=8,
            orientation="vertical",
            **kwargs,
        )

        self.client = NetworkClient()
        self.scan_icon = Label(name="wifi-scan-icon", markup=icons.scan)
        self.toggle_icon = Label(name="wifi-toggle-icon", markup=icons.wifi_off)

        self.scan_button = Button(
            name="wifi-scan",
            child=self.scan_icon,
            tooltip_text="Scan",
            on_clicked=lambda *_: self.client.wifi_device
            and self.client.wifi_device.scan(),
        )

        self.toggle_button = Button(
            name="wifi-toggle",
            tooltip_text="Toggle WiFi",
            child=self.toggle_icon,
            on_clicked=lambda *_: self.client.wifi_device
            and self.client.wifi_device.toggle_wifi(),
        )

        self.available_box = Box(spacing=2, orientation="vertical")

        self.children = [
            CenterBox(
                name="wifi-header",
                start_children=self.scan_button,
                center_children=Label(name="wifi-text", label="WiFi Networks"),
                end_children=self.toggle_button,
            ),
            ScrolledWindow(
                name="wifi-available",
                v_expand=True,
                h_scrollbar_policy="never",
                min_content_size=(-1, -1),
                child=self.available_box,
            ),
        ]

        self.client.connect("device-ready", lambda *_: self.on_device_ready())

    def on_device_ready(self):
        if not self.client.wifi_device:
            return

        self.update_toggle_icon()

        self.client.wifi_device.connect(
            "notify::enabled",
            lambda *_: self.update_toggle_icon(),
        )

        self.build_wifi_options()

    def update_toggle_icon(self):
        self.toggle_icon.set_markup(
            icons.wifi if self.client.wifi_device.enabled else icons.wifi_off
        )

    def build_wifi_options(self):
        self.available_box.children = []
        if not self.client.wifi_device:
            return

        aps = self.client.wifi_device.access_points
        seen_ssids = set()
        for ap in aps:
            ssid = ap.get("ssid")
            if ap.get("ssid") != "Unknown" and ssid not in seen_ssids:
                seen_ssids.add(ssid)
                self.available_box.add(WifiNetworkSlot(ap, self.client))
