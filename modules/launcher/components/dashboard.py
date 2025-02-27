from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from snippets import MaterialIcon


class Buttons(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="buttons",
            spacing=4,
            h_align="center",
            v_align="start",
            h_expand=True,
            v_expand=True,
            visible=True,
            all_visible=True,
        )

        self.network_status_button = Button(
            name="network-status-button",
            h_expand=True,
            child=Box(
                h_align="start",
                v_align="center",
                spacing=10,
                children=[
                    MaterialIcon("wifi"),
                    Box(
                        name="network-text",
                        orientation="v",
                        h_align="start",
                        v_align="center",
                        children=[
                            Box(
                                children=[
                                    Label(
                                        name="network-label",
                                        label="Wi-Fi",
                                        justification="left",
                                    ),
                                    Box(h_expand=True),
                                ]
                            ),
                            Box(
                                children=[
                                    Label(
                                        name="network-ssid",
                                        label="ARGOS_5GHz",
                                        justification="left",
                                    ),
                                    Box(h_expand=True),
                                ]
                            ),
                        ],
                    ),
                ],
            ),
        )

        self.network_menu_button = Button(
            name="network-menu-button",
            child=MaterialIcon("chevron_right"),
        )

        self.network_button = Box(
            name="network-button",
            orientation="h",
            h_align="fill",
            v_align="center",
            h_expand=True,
            v_expand=True,
            children=[
                self.network_status_button,
                self.network_menu_button,
            ],
        )

        self.bluetooth_status_button = Button(
            name="bluetooth-status-button",
            h_expand=True,
            child=Box(
                h_align="start",
                v_align="center",
                spacing=10,
                children=[
                    MaterialIcon("bluetooth"),
                    Box(
                        name="bluetooth-text",
                        orientation="v",
                        h_align="start",
                        v_align="center",
                        children=[
                            Box(
                                children=[
                                    Label(
                                        name="bluetooth-label",
                                        label="Bluetooth",
                                        justification="left",
                                    ),
                                    Box(h_expand=True),
                                ]
                            ),
                            Box(
                                children=[
                                    Label(
                                        name="bluetooth-status",
                                        label="Connected",
                                        justification="left",
                                    ),
                                    Box(h_expand=True),
                                ]
                            ),
                        ],
                    ),
                ],
            ),
        )

        self.bluetooth_menu_button = Button(
            name="bluetooth-menu-button",
            child=MaterialIcon("chevron_right"),
        )

        self.bluetooth_button = Box(
            name="bluetooth-button",
            orientation="h",
            h_align="fill",
            v_align="center",
            h_expand=True,
            v_expand=True,
            children=[
                self.bluetooth_status_button,
                self.bluetooth_menu_button,
            ],
        )

        self.night_mode_button = Button(
            name="night-mode-button",
            child=Box(
                h_align="start",
                v_align="center",
                spacing=10,
                children=[
                    MaterialIcon("nightlight"),
                    Box(
                        name="night-mode-text",
                        orientation="v",
                        h_align="start",
                        v_align="center",
                        children=[
                            Box(
                                children=[
                                    Label(
                                        name="night-mode-label",
                                        label="Night Mode",
                                        justification="left",
                                    ),
                                    Box(h_expand=True),
                                ]
                            ),
                            Box(
                                children=[
                                    Label(
                                        name="night-mode-status",
                                        label="Enabled",
                                        justification="left",
                                    ),
                                    Box(h_expand=True),
                                ]
                            ),
                        ],
                    ),
                ],
            ),
        )

        self.caffeine_button = Button(
            name="caffeine-button",
            child=Box(
                h_align="start",
                v_align="center",
                spacing=10,
                children=[
                    MaterialIcon("coffee"),
                    Box(
                        name="caffeine-text",
                        orientation="v",
                        h_align="start",
                        v_align="center",
                        children=[
                            Box(
                                children=[
                                    Label(
                                        name="caffeine-label",
                                        label="Caffeine",
                                        justification="left",
                                    ),
                                    Box(h_expand=True),
                                ]
                            ),
                            Box(
                                children=[
                                    Label(
                                        name="caffeine-status",
                                        label="Enabled",
                                        justification="left",
                                    ),
                                    Box(h_expand=True),
                                ]
                            ),
                        ],
                    ),
                ],
            ),
        )

        self.add(self.network_button)
        self.add(self.bluetooth_button)
        self.add(self.night_mode_button)
        self.add(self.caffeine_button)

        self.show_all()


class Dashboard(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="dashboard",
            h_align="center",
            v_align="start",
            h_expand=True,
            v_expand=True,
            visible=True,
            all_visible=True,
        )

        self.buttons = Buttons()

        self.add(self.buttons)

        self.show_all()
