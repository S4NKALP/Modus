import threading

from fabric.utils import (
    Gdk,
    exec_shell_command_async,
    idle_add,
    remove_handler,
    time,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin


class PowerMenuPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "power_menu"

    @property
    def icon(self) -> str:
        return "system-shutdown-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["powermenu", "pm"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0

        self.power_options = [
            {
                "name": "Shutdown",
                "icon": "system-shutdown",
                "command": ["shutdown", "now"],
                "description": "Shutdown the system immediately",
            },
            {
                "name": "Restart",
                "icon": "system-reboot",
                "command": ["shutdown", "-r", "now"],
                "description": "Restart the system immediately",
            },
            {
                "name": "Suspend",
                "icon": "system-suspend",
                "command": ["systemctl", "suspend"],
                "description": "Suspend the system to RAM",
            },
            {
                "name": "Hibernate",
                "icon": "system-hibernate",
                "command": ["systemctl", "hibernate"],
                "description": "Hibernate the system to disk",
            },
            {
                "name": "Logout",
                "icon": "system-log-out",
                "command": ["pkill", "-SIGTERM", "Hyprland"],
                "description": "Logout from the current session",
            },
            {
                "name": "Lock Screen",
                "icon": "system-lock-screen",
                "command": ["hyprlock"],
                "description": "Lock the screen",
            },
        ]

    def on_search(self, text: str) -> None:
        self.query_power_menu(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
        self._query_handler = 0

    def query_power_menu(self, text: str) -> None:
        self.handler.start("power-menu")

        filtered_options = self._filter_options(text, self.power_options)
        if not filtered_options:
            return

        self._query_handler = idle_add(
            self._bake_next_option_slot, iter(filtered_options), pin=True
        )

    def _filter_options(self, text: str, options) -> list:
        return (
            options
            if not text.strip()
            else [
                option
                for option in options
                if text.lower() in option["name"].lower()
                or text.lower() in option["description"].lower()
            ]
        )

    def _bake_next_option_slot(self, iterator) -> bool:
        option = next(iterator, None)
        if option is None:
            idle_add(self.handler.done)
            return False
        self._create_option_slot(option)
        return True

    def _create_option_slot(self, option) -> None:
        slot_content = Box(
            orientation="h",
            spacing=12,
            children=[
                Image(icon_name=option["icon"], h_align="start", size=32),
                Box(
                    orientation="v",
                    children=[
                        Label(
                            label=option["name"],
                            style_classes="power-menu-name",
                            h_align="start",
                            v_align="start",
                        ),
                        Label(
                            label=option["description"],
                            style_classes="power-menu-description",
                            h_align="start",
                            v_align="start",
                        ),
                    ],
                ),
            ],
        )

        slot_widget = Button(
            style_classes="app-slot power-menu-slot",
            child=slot_content,
            tooltip_text=f"Click to {option['name'].lower()} the system",
            on_clicked=lambda *_: (
                self.handler.launched(),
                self._execute_power_command(option),
            ),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, opt=option: self._on_slot_key_press(
                widget, event, opt
            ),
        )

        self.handler.slot_ready(slot_widget, "power-menu")

    def _execute_power_command(self, option) -> None:
        def delayed_execute():
            time.sleep(0.2)
            exec_shell_command_async(" ".join(option["command"]))

        threading.Thread(target=delayed_execute, daemon=True).start()

    def _on_slot_key_press(self, widget, event, option) -> bool:
        if not event or event.keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        self.handler.launched()
        self._execute_power_command(option)
        return True

    def handle_external(self, command: str, args: str) -> None:
        if not args:
            return

        for option in self.power_options:
            if args.lower() == option["name"].lower():
                self._execute_power_command(option)
                return
