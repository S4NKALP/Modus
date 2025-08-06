from gi.repository import Gdk, GLib

from fabric.utils import idle_add
from fabric.utils.helpers import (
    get_relative_path,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.svg import Svg
from modules.controlcenter.bluetooth import BluetoothConnections
from modules.controlcenter.wifi import WifiConnections
from services.brightness import Brightness
from utils.roam import audio_service, modus_service
from widgets.wayland import WaylandWindow as Window
from modules.controlcenter.player import PlayerBoxStack
from services.mpris import MprisPlayerManager

brightness_service = Brightness.get_initial()

# FIX: Icon not showing up in control center
# TODO: Add Player


class ModusControlCenter(Window):
    def __init__(self, **kwargs):
        super().__init__(
            layer="top",
            title="modus",
            anchor="top right",
            margin="2px 10px 0px 0px",
            exclusivity="auto",
            keyboard_mode="on-demand",
            name="control-center-menu",
            visible=False,
            **kwargs,
        )
        self.focus_mode = modus_service.dont_disturb
        self._updating_brightness = False
        self._updating_volume = False

        self.add_keybinding("Escape", self.hide_controlcenter)

        volume = 100
        wlan = modus_service.sc("wlan-changed", self.wlan_changed)
        bluetooth = modus_service.sc("bluetooth-changed", self.bluetooth_changed)
        music = modus_service.sc("music-changed", self.audio_changed)

        audio_service.connect("changed", self.audio_changed)
        audio_service.connect("changed", self.volume_changed)
        modus_service.connect("dont-disturb-changed", self.dnd_changed)

        self.wlan_label = Label(wlan, name="wifi-widget-label", h_align="start")
        if bluetooth != "disabled":
            if bluetooth.startswith("connected:"):
                parts = bluetooth.split(":")
                bluetooth_display = parts[1] if len(parts) >= 2 else "Connected"
            else:
                bluetooth_display = "On"
        else:
            bluetooth_display = "Off"

        self.bluetooth_label = Label(
            bluetooth_display, name="bluetooth-widget-label", h_align="start"
        )
        self.volume_scale = Scale(
            value=volume,
            min_value=0,
            max_value=100,
            increments=(5, 5),
            name="volume-widget-slider",
            size=30,
            h_expand=True,
        )
        self.volume_scale.connect("change-value", self.set_volume)
        self.volume_scale.connect("scroll-event", self.on_volume_scroll)

        current_brightness = brightness_service.screen_brightness
        brightness_percentage = (
            int((current_brightness / brightness_service.max_screen) * 100)
            if brightness_service.max_screen > 0
            else 50
        )

        self.brightness_scale = Scale(
            value=brightness_percentage,
            min_value=0,
            max_value=100,
            increments=(5, 5),
            name="brightness-widget-slider",
            size=30,
            h_expand=True,
        )

        # Only connect brightness controls if brightness service is available
        if brightness_service.max_screen > 0:
            self.brightness_scale.connect("change-value", self.set_brightness)
            self.brightness_scale.connect("scroll-event", self.on_brightness_scroll)
            brightness_service.connect("screen", self.brightness_changed)
        else:
            # Disable brightness scale if no backlight device available
            self.brightness_scale.set_sensitive(False)

        # Create music widget with ultra-lazy player container
        self.music_widget = Box(
            name="music-widget",
            h_align="start",
            # on_clicked=lambda *_: (
            #     self.hide_controlcenter(),
            #     self.expanded_player.set_visible(True),
            #     self.ex_mousecapture.toggle_mousecapture(),
            # ),
            children=PlayerBoxStack(MprisPlayerManager(), control_center=self),
        )

        self.wifi_man = WifiConnections(self)
        self.bluetooth_man = BluetoothConnections(self)

        self.has_bluetooth_open = False
        self.has_wifi_open = False

        self.bluetooth_svg = Svg(
            name="bluetooth-icon",
            svg_file=get_relative_path(
                "../../config/assets/icons/applets/bluetooth.svg"
                if bluetooth != "disabled"
                else "../../config/assets/icons/applets/bluetooth-off.svg"
            ),
            size=42,
        )
        self.wifi_svg = Svg(
            name="wifi-icon",
            svg_file=get_relative_path(
                "../../config/assets/icons/applets/wifi.svg"
                if wlan != "No Connection"
                else "../../config/assets/icons/applets/wifi-off.svg"
            ),
            size=46,
        )

        self.bluetooth_widget = Button(
            name="bluetooth-widget",
            child=Box(
                orientation="h",
                children=[
                    self.bluetooth_svg,
                    Box(
                        name="bluetooth-widget-info",
                        orientation="vertical",
                        children=[
                            Label(
                                name="bluetooth-widget-name",
                                label="Bluetooth",
                                style_classes="ct",
                                h_align="start",
                            ),
                            self.bluetooth_label,
                        ],
                    ),
                ],
            ),
            on_clicked=self.open_bluetooth,
        )

        self.wlan_widget = Button(
            name="wifi-widget",
            child=Box(
                orientation="h",
                children=[
                    self.wifi_svg,
                    Box(
                        name="wifi-widget-info",
                        orientation="vertical",
                        children=[
                            Label(
                                name="wifi-widget-name",
                                label="Wi-Fi",
                                style_classes="ct",
                                h_align="start",
                            ),
                            self.wlan_label,
                        ],
                    ),
                ],
            ),
            on_clicked=self.open_wifi,
        )

        self.focus_icon = Svg(
            name="focus-icon",
            svg_file=get_relative_path(
                "../../config/assets/icons/applets/dnd.svg"
                if self.focus_mode
                else "../../config/assets/icons/applets/dnd-off.svg"
            ),
            size=46,
        )

        self.focus_widget = Button(
            name="focus-widget",
            child=Box(
                orientation="h",
                children=[
                    self.focus_icon,
                    Label(label="Focus", style_classes="title ct", h_align="start"),
                ],
            ),
            on_clicked=self.set_dont_disturb,
        )

        # Create main widgets directly without XML
        self.widgets = Box(
            orientation="vertical",
            h_expand=True,
            name="control-center-widgets",
            children=[
                Box(
                    orientation="horizontal",
                    name="top-widget",
                    h_expand=True,
                    children=[
                        Box(
                            orientation="vertical",
                            name="wb-widget",
                            style_classes="menu",
                            spacing=5,
                            children=[
                                self.wlan_widget,
                                self.bluetooth_widget,
                            ],
                        ),
                        Box(
                            orientation="horizontal",
                            name="dnd-widget",
                            style_classes="menu",
                            h_expand=True,
                            children=[
                                self.focus_widget,
                            ],
                        ),
                    ],
                ),
                Box(
                    orientation="vertical",
                    name="brightness-widget",
                    style_classes="menu",
                    h_expand=True,
                    children=[
                        Label(
                            label="Display",
                            style_classes="title",
                            h_align="start"
                        ),
                        self.brightness_scale,
                        Label(
                            label="󰖨 ",
                            name="brightness-widget-icon",
                            h_align="start"
                        ),
                    ],
                ),
                Box(
                    orientation="vertical",
                    name="volume-widget",
                    style_classes="menu",
                    h_expand=True,
                    children=[
                        Label(
                            label="Sound",
                            style_classes="title",
                            h_align="start"
                        ),
                        self.volume_scale,
                        Label(
                            label=" ",
                            name="brightness-widget-icon",
                            h_align="start"
                        ),
                    ],
                ),
                Box(
                    orientation="vertical",
                    children=[
                        self.music_widget,
                    ],
                ),
            ],
        )

        # Create bluetooth widgets directly without XML
        self.bluetooth_widgets = Box(
            orientation="vertical",
            h_expand=True,
            name="control-center-widgets",
            children=[
                Box(
                    orientation="horizontal",
                    name="top-widget",
                    h_expand=True,
                    children=[
                        Box(
                            orientation="vertical",
                            name="wb-widget",
                            style_classes="menu",
                            spacing=5,
                            children=[
                                self.bluetooth_man,
                            ],
                        ),
                    ],
                ),
            ],
        )

        # Create wifi widgets directly without XML
        self.wifi_widgets = Box(
            orientation="vertical",
            h_expand=True,
            name="control-center-widgets",
            children=[
                Box(
                    orientation="horizontal",
                    name="top-widget",
                    h_expand=True,
                    children=[
                        Box(
                            orientation="vertical",
                            name="wb-widget",
                            style_classes="menu",
                            spacing=5,
                            children=[
                                self.wifi_man,
                            ],
                        ),
                    ],
                ),
            ],
        )

        self.center_box = CenterBox(start_children=[self.widgets])

        self.bluetooth_center_box = CenterBox(start_children=[self.bluetooth_widgets])

        self.wifi_center_box = CenterBox(start_children=[self.wifi_widgets])

        self.widgets.set_size_request(300, -1)
        self.bluetooth_center_box.set_size_request(300, -1)
        self.wifi_center_box.set_size_request(300, -1)

        self.children = self.center_box

    def set_dont_disturb(self, *_):
        self.focus_mode = not self.focus_mode
        modus_service.dont_disturb = self.focus_mode
        self.focus_icon.set_from_file(
            get_relative_path(
                "../../config/assets/icons/applets/dnd.svg"
                if self.focus_mode
                else "../../config/assets/icons/applets/dnd-off.svg"
            )
        )

    def set_volume(self, _, __, volume):
        self._updating_volume = True
        audio_service.speaker.volume = round(volume)
        self._updating_volume = False

    def set_brightness(self, _, __, brightness):
        self._updating_brightness = True
        brightness_value = int((brightness / 100) * brightness_service.max_screen)
        brightness_service.screen_brightness = brightness_value
        self._updating_brightness = False

    def brightness_changed(self, _, brightness_value):
        if self._updating_brightness:
            return

        if brightness_service.max_screen > 0:
            brightness_percentage = int(
                (brightness_value / brightness_service.max_screen) * 100
            )

            GLib.idle_add(
                lambda: self.brightness_scale.set_value(brightness_percentage)
            )

    def on_volume_scroll(self, widget, event):
        current_value = self.volume_scale.get_value()
        scroll_step = 5
        if event.direction == Gdk.ScrollDirection.UP:
            new_value = min(100, current_value + scroll_step)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            new_value = max(0, current_value - scroll_step)
        else:
            return False

        self.volume_scale.set_value(new_value)
        return True

    def on_brightness_scroll(self, widget, event):
        current_value = self.brightness_scale.get_value()
        scroll_step = 5
        if event.direction == Gdk.ScrollDirection.UP:
            new_value = min(100, current_value + scroll_step)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            new_value = max(0, current_value - scroll_step)
        else:
            return False

        self.brightness_scale.set_value(new_value)
        return True

    def set_children(self, children):
        self.children = children

    def open_bluetooth(self, *_):
        idle_add(lambda *_: self.set_children(self.bluetooth_center_box))
        self.has_bluetooth_open = True

    def open_wifi(self, *_):
        idle_add(lambda *_: self.set_children(self.wifi_center_box))
        self.has_wifi_open = True

    def close_bluetooth(self, *_):
        idle_add(lambda *_: self.set_children(self.center_box))
        self.has_bluetooth_open = False

    def close_wifi(self, *_):
        idle_add(lambda *_: self.set_children(self.center_box))
        self.has_wifi_open = False

    def _set_mousecapture(self, visible: bool):
        self.set_visible(visible)
        if not visible:
            self.close_bluetooth()
            self.close_wifi()

    def volume_changed(
        self,
        _,
    ):
        if self._updating_volume:
            return

        GLib.idle_add(
            lambda: self.volume_scale.set_value(int(audio_service.speaker.volume))
        )

    def wlan_changed(self, _, wlan):
        self.wifi_svg.set_from_file(
            get_relative_path(
                "../../config/assets/icons/applets/wifi.svg"
                if wlan != "No Connection"
                else "../../config/assets/icons/applets/wifi-off.svg"
            )
        )
        if wlan != "No Connection":
            if wlan.startswith("connected:"):
                parts = wlan.split(":")
                if len(parts) >= 2:
                    wifi_name = parts[1]
                    GLib.idle_add(
                        lambda: self.wlan_label.set_property("label", wifi_name)
                    )
                else:
                    GLib.idle_add(
                        lambda: self.wlan_label.set_property("label", "Connected")
                    )
            else:
                GLib.idle_add(lambda: self.wlan_label.set_property("label", wlan))
        else:
            GLib.idle_add(lambda: self.wlan_label.set_property("label", wlan))

    def bluetooth_changed(self, _, bluetooth):
        self.bluetooth_svg.set_from_file(
            get_relative_path(
                "../../config/assets/icons/applets/bluetooth.svg"
                if bluetooth != "disabled"
                else "../../config/assets/icons/applets/bluetooth-off.svg"
            )
        )
        if bluetooth != "disabled":
            if bluetooth.startswith("connected:"):
                parts = bluetooth.split(":")
                if len(parts) >= 2:
                    device_name = parts[1]
                    GLib.idle_add(
                        lambda: self.bluetooth_label.set_property("label", device_name)
                    )
                else:
                    GLib.idle_add(
                        lambda: self.bluetooth_label.set_property("label", "Connected")
                    )
            elif bluetooth == "enabled":
                GLib.idle_add(lambda: self.bluetooth_label.set_property("label", "On"))
            else:
                GLib.idle_add(lambda: self.bluetooth_label.set_property("label", "On"))
        else:
            GLib.idle_add(lambda: self.bluetooth_label.set_property("label", "Off"))

    def audio_changed(self, *_):
        pass

    def dnd_changed(self, _, dnd_state):
        self.focus_mode = dnd_state
        self.focus_icon.set_from_file(
            get_relative_path(
                "../../config/assets/icons/applets/dnd.svg"
                if self.focus_mode
                else "../../config/assets/icons/applets/dnd-off.svg"
            )
        )

    def _init_mousecapture(self, mousecapture):
        self._mousecapture_parent = mousecapture

    def hide_controlcenter(self, *_):
        self._mousecapture_parent.toggle_mousecapture()
        self.set_visible(False)
