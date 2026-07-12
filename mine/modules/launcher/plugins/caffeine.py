from fabric.utils import (
    Gdk,
    exec_shell_command_async,
    idle_add,
    remove_handler,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

import config.data as data
from modules.launcher.base import LauncherPlugin
from services import InhibitService


class CaffeinePlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "caffeine"

    @property
    def icon(self) -> str:
        return "caffeine"

    @property
    def keywords(self) -> list[str]:
        return ["caffeine", "caff"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self.inhibit_service = InhibitService.get_initial()

        self.presets = [
            {"name": "On (indefinite)", "arg": "on", "icon": "caffeine"},
            {"name": "30 minutes", "arg": "30m", "icon": "caffeine"},
            {"name": "1 hour", "arg": "1h", "icon": "caffeine"},
            {"name": "2 hours", "arg": "2h", "icon": "caffeine"},
        ]

    def on_search(self, text: str) -> None:
        self.query_caffeine(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
        self._query_handler = 0

    def _is_inhibiting(self) -> bool:
        return self.inhibit_service.is_running

    def query_caffeine(self, text: str) -> None:
        self.handler.start("caffeine")

        text_stripped = text.strip()
        inhibiting = self._is_inhibiting()
        options = []

        if inhibiting:
            options.append({"name": "Off", "arg": "off", "icon": "caffeine-plus-off"})
            options.extend([preset for preset in self.presets if preset["arg"] != "on"])
        else:
            options.extend(self.presets)

        if (
            text_stripped
            and text_stripped not in {o["arg"] for o in options}
            and not (text_stripped.lower() == "off" and not inhibiting)
        ):
            options.insert(
                0,
                {
                    "name": f"Custom: {text_stripped}",
                    "arg": text_stripped,
                    "icon": "document-send-symbolic",
                },
            )

        filtered_options = self._filter_options(text, options)
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
                or text.lower() in option["arg"].lower()
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
                            label=f"Caffeine: {option['name']}",
                            style_classes="caffeine-name",
                            h_align="start",
                            v_align="start",
                        ),
                        Label(
                            label=f"Set idle inhibitor to '{option['arg']}'",
                            style_classes="caffeine-description",
                            h_align="start",
                            v_align="start",
                        ),
                    ],
                ),
            ],
        )

        slot_widget = Button(
            style_classes="app-slot caffeine-slot",
            child=slot_content,
            tooltip_text=f"Click to set caffeine: {option['arg']}",
            on_clicked=lambda *_: (
                self.handler.launched(),
                self._execute_caffeine(option["arg"]),
            ),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, opt=option: self._on_slot_key_press(
                widget, event, opt
            ),
        )

        self.handler.slot_ready(slot_widget, "caffeine")

    def _execute_caffeine(self, arg: str) -> None:
        arg_lower = arg.lower()
        if arg_lower == "off":
            self.inhibit_service.disable()
            self._notify("☕ Caffeine", "Deactivated")
            return
        self.inhibit_service.enable(arg_lower)
        duration_text = self._duration_to_text(arg_lower)
        self._notify("☕ Caffeine", f"Activated for {duration_text}")

    def _on_slot_key_press(self, widget, event, option) -> bool:
        if not event or event.keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        self.handler.launched()
        self._execute_caffeine(option["arg"])
        return True

    def _notify(self, title: str, body: str) -> None:
        exec_shell_command_async(
            f"notify-send '{title}' '{body}' -a '{data.APP_NAME}' -e"
        )

    def _duration_to_text(self, duration: str) -> str:
        mapping = {
            "30m": "30 minutes",
            "1h": "1 hour",
            "2h": "2 hours",
            "on": "On",
            "off": "Off",
        }
        return mapping.get(duration, duration)

    def handle_external(self, command: str, args: str) -> None:
        if args:
            self._execute_caffeine(args)
