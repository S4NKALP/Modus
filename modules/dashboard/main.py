from fabric.widgets.box import Box
from fabric.widgets.revealer import Revealer
from fabric.widgets.scrolledwindow import ScrolledWindow
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
        self.wifi = Network()
        self.bluetooth = Bluetooth()
        self.mini_player = PlayerContainerMini()
        self.mini_player_tile = TileSpecial(
            props=self.mini_player, mini_props=self.mini_player.get_mini_view()
        )

        # Create real notifications component
        self.dashboard_notifications = DashboardNotifications()

        # Create scrolled window for notifications (matching dock notifications style)
        self.notifications_scrolled = ScrolledWindow(
            name="notification-history-scrolled-window",
            child=self.dashboard_notifications,
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            min_content_size=(400, 200),
            max_content_size=(450, 300),
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            propagate_width=False,
            propagate_height=False,
        )

        self.tiles = Box(
            children=[
                self.wifi,
                self.bluetooth,
                self.mini_player_tile,
            ],
        )

        self.notification_container = Revealer(
            transition_duration=250,
            transition_type="slide-down",
            h_expand=True,
            child=Box(
                name="notification-history-popup-content",
                orientation="v",
                spacing=8,
                h_expand=True,
                v_expand=True,
                children=[self.notifications_scrolled],
                style_classes=["notification-history-popup"],
            ),
            child_revealed=True,
        )
        self.children = [
            Box(name="inner", children=self.tiles),
            Box(
                children=[
                    self.notification_container,
                ]
            ),
        ]

    def handle_tile_menu_expand(self, tile: str, toggle: bool):
        if toggle:
            self.notification_container.set_reveal_child(False)
        else:
            self.notification_container.set_reveal_child(True)
        for i in self.tiles:
            if i.get_name() == tile:
                print("found")
            else:
                if toggle:
                    i.mini_view()
                    i.icon.add_style_class("mini")
                    i.icon.remove_style_class("maxi")
                else:
                    i.maxi_view()
                    i.icon.add_style_class("maxi")
                    i.icon.remove_style_class("mini")
        print("search complete")


class DashboardWindow(Window):

    visible = Property(bool, flags="read-write", default_value=False)
    def __init__(self, **kwargs):
        super().__init__(
            name="dashboard-window",
            layer="top",
            anchor="bottom",
            exclusivity="none",
            keyboard_mode="on-demand",
            child=Dashboard(),
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
        self.hide()
        self.visible = False

    def toggle_dashboard(self):
        if self.visible:
            self.close_dashboard()
        else:
            self.show_dashboard()


