from pathlib import Path

from fabric.utils import (
    GLib,
    exec_shell_command,
    exec_shell_command_async,
    idle_add,
    re,
    remove_handler,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

import config.data as data
from modules.launcher.base import LauncherPlugin
from utils.functions import copy_text


class ColorPickerPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "color_picker"

    @property
    def icon(self) -> str:
        return "color-select-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["color"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self.tmp_icon_path = Path("/tmp/color.png")

        self.options = [
            {"name": "Pick HEX", "arg": "hex", "icon": "color-select"},
            {"name": "Pick RGB", "arg": "rgb", "icon": "color-select"},
            {"name": "Pick HSV", "arg": "hsv", "icon": "color-select"},
        ]

    def on_search(self, text: str) -> None:
        self.query_color(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
        self._query_handler = 0

    def query_color(self, text: str) -> None:
        self.handler.start("color")

        q = text.strip().lower()
        if q in ("hex", "rgb", "hsv"):
            self._defer_execute(q)
            return

        filtered = (
            self.options
            if not q
            else [o for o in self.options if q in o["name"].lower() or q == o["arg"]]
        )
        if not filtered:
            return self.handler.done()
        self._query_handler = idle_add(self._bake_next_slot, iter(filtered), pin=True)

    def _bake_next_slot(self, iterator) -> bool:
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
                            label=f"Color Picker: {option['name']}",
                            style_classes="colorpicker-name",
                            h_align="start",
                            v_align="start",
                        ),
                        Label(
                            label=f"Copy {option['arg'].upper()} to clipboard and show preview",
                            style_classes="colorpicker-description",
                            h_align="start",
                            v_align="start",
                        ),
                    ],
                ),
            ],
        )

        slot_widget = Button(
            style_classes="app-slot colorpicker-slot",
            child=slot_content,
            tooltip_text=f"Click to pick {option['arg'].upper()} color",
            on_clicked=lambda *_: self._defer_execute(option["arg"]),
        )

        self.handler.slot_ready(slot_widget, "color")

    def _defer_execute(self, mode: str) -> None:
        self.handler.launched()
        GLib.timeout_add(200, lambda: (self._execute_pick(mode), False)[1])

    def _execute_pick(self, mode: str) -> None:
        fmt = mode.lower()
        if fmt not in ("hex", "rgb", "hsv"):
            fmt = "hex"

        raw = exec_shell_command(f"hyprpicker -n -f {fmt}")
        text = raw if isinstance(raw, str) else ""
        color = self._sanitize_color_output(fmt, text)
        if not color:
            return

        copy_text(color)

        color_spec = (
            color
            if fmt == "hex"
            else (f"rgb({color})" if fmt == "rgb" else f"hsv({color})")
        )
        self.tmp_icon_path.unlink(missing_ok=True)  # type: ignore[attr-defined]

        cmd = (
            f"magick -size 64x64 xc:'{color_spec}' {self.tmp_icon_path} >/dev/null 2>&1; "
            f"notify-send 'Color picked' '{fmt.upper()}: {color}' -i {self.tmp_icon_path} -a '{data.APP_NAME}' -e; "
            f"rm -f {self.tmp_icon_path}"
        )
        exec_shell_command_async(["bash", "-lc", cmd])

    def _sanitize_color_output(self, fmt: str, text: str) -> str:
        joined = " ".join(ln.strip() for ln in text.splitlines() if ln.strip())
        if fmt == "hex":
            matches = re.findall(r"#?[0-9A-Fa-f]{6,8}", joined)
            if not matches:
                return ""
            val = matches[-1]
            return val if val.startswith("#") else f"#{val}"
        if fmt in ("rgb", "hsv"):
            matches = re.findall(
                r"\d+(?:\.\d+)?\s*,\s*\d+(?:\.\d+)?\s*,\s*\d+(?:\.\d+)?", joined
            )
            return matches[-1] if matches else ""
        return ""

    def handle_external(self, command: str, args: str) -> None:
        # Map external commands if needed
        pass
