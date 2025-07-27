from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from fabric.core.service import Property

from modules.dashboard.bluetooth import Bluetooth
from modules.dashboard.network import Network
from modules.dashboard.tile import TileSpecial
from modules.dashboard.player_mini import PlayerContainerMini
from modules.dashboard.notifications import DashboardNotifications

from utils.wayland import WaylandWindow as Window


class Dashboard(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="dashboard",
            visible=True,
            orientation="v",
            spacing=8,
            all_visible=True,
            **kwargs,
        )
        self.wifi = Network(name="wifi-tile")
        self.bluetooth = Bluetooth(name="bluetooth-tile")
        self.mini_player = PlayerContainerMini()
        self.mini_player_tile = TileSpecial(
            props=self.mini_player, mini_props=self.mini_player.get_mini_view()
        )

        # Set dashboard instance reference for tiles that need it
        self.wifi.dashboard_instance = self
        self.bluetooth.dashboard_instance = self

        # Create real notifications component
        self.dashboard_notifications = DashboardNotifications()

        # Track currently active tile
        self.active_tile = None

        self.tiles = Box(
            children=[
                self.wifi,
                self.bluetooth,
                self.mini_player_tile,
            ],
        )

        # Create content containers for each tile
        self.wifi_content = self.wifi.create_content()
        self.bluetooth_content = self.bluetooth.create_content()

        # Default content (notifications)
        self.default_content = Box(
            name="notification-history-popup-content",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=True,
            children=[self.dashboard_notifications],
            style_classes=["notification-history-popup"],
        )

        # Content stack to switch between different tile contents
        self.content_stack = Stack(
            transition_type="crossfade",
            transition_duration=200,
            h_expand=True,
            v_expand=True,
            h_align="fill",
            children=[
                self.default_content,
                self.wifi_content,
                self.bluetooth_content,
            ],
        )

        # Set default visible child
        self.content_stack.set_visible_child(self.default_content)

        self.children = [
            Box(name="inner", children=self.tiles),
            Box(
                children=[
                    self.content_stack,
                ]
            ),
        ]

    def handle_tile_menu_expand(self, tile: str, toggle: bool):
        print(
            f"Tile menu expand: {tile}, toggle: {toggle}, active_tile: {
                self.active_tile
            }"
        )

        # If clicking the same tile that's already active, deactivate it
        if self.active_tile == tile and toggle:
            toggle = False
            # Update the tile's toggle state
            for i in self.tiles:
                if i.get_name() == tile:
                    i.toggle = False
                    break

        if toggle:
            # Show the specific tile's content in the content area
            self.active_tile = tile
            if tile == "wifi-tile":
                self.content_stack.set_visible_child(self.wifi_content)
                print("Showing WiFi content")
            elif tile == "bluetooth-tile":
                self.content_stack.set_visible_child(self.bluetooth_content)
                print("Showing Bluetooth content")
        else:
            # Show default content (notifications)
            self.active_tile = None
            self.content_stack.set_visible_child(self.default_content)
            print("Showing default content")

        # Don't change tile visual states - keep all tiles unchanged
        print("Tile handling complete")

    def reset_to_default(self):
        """Reset dashboard to default state (notifications visible, no active tile)"""
        print("Resetting dashboard to default state")
        self.active_tile = None
        self.content_stack.set_visible_child(self.default_content)

        # Reset all tile toggle states
        for tile in self.tiles:
            if hasattr(tile, "toggle"):
                tile.toggle = False


class DashboardWindow(Window):
    visible = Property(bool, flags="read-write", default_value=False)

    def __init__(self, **kwargs):
        # Create dashboard instance and store reference
        self.dashboard = Dashboard()

        super().__init__(
            name="dashboard-window",
            layer="top",
            anchor="bottom",
            exclusivity="none",
            keyboard_mode="on-demand",
            child=self.dashboard,
            visible=False,
            all_visible=False,
            **kwargs,
        )

        # Add escape key binding to close dashboard
        self.add_keybinding("Escape", lambda *_: self.close_dashboard())
        self.hide()

    def show_dashboard(self):
        self.show_all()
        self.visible = True

    def close_dashboard(self):
        # Reset dashboard to default state when closing
        self.dashboard.reset_to_default()
        self.hide()
        self.visible = False

    def toggle_dashboard(self):
        if self.visible:
            self.close_dashboard()
        else:
            self.show_dashboard()
