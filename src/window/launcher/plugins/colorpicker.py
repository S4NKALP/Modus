import os
import re
import subprocess
from typing import List

from fabric.utils import exec_shell_command, exec_shell_command_async, logger
from shared.data import APP_NAME
from window.launcher.plugin_base import PluginBase
from window.launcher.result import Result


class ColorPickerPlugin(PluginBase):
    """
    Plugin for picking colors from the screen using hyprpicker.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Color Picker"
        self.description = "Pick colors from the screen (HEX, RGB, HSV)"
        self.tmp_icon_path = "/tmp/color.png"

        self.options = [
            {"name": "Pick HEX", "arg": "hex", "icon": "color-select-symbolic"},
            {"name": "Pick RGB", "arg": "rgb", "icon": "color-select-symbolic"},
            {"name": "Pick HSV", "arg": "hsv", "icon": "color-select-symbolic"},
        ]

    def initialize(self):
        """Initialize the color picker plugin."""
        self.set_triggers(["color", "cp"])

    def cleanup(self):
        """Cleanup resources."""
        if os.path.exists(self.tmp_icon_path):
            try:
                os.remove(self.tmp_icon_path)
            except OSError:
                pass

    def query(self, query_string: str) -> List[Result]:
        """Process a search query and return results."""
        q = query_string.strip().lower()

        results = []

        # Filter options based on query
        filtered = (
            self.options
            if not q
            else [o for o in self.options if q in o["name"].lower() or q == o["arg"]]
        )

        for option in filtered:
            mode = option["arg"]
            results.append(
                Result(
                    title=f"Color Picker: {option['name']}",
                    subtitle=f"Pick and copy {mode.upper()} color to clipboard",
                    icon_name=option["icon"],
                    action=lambda m=mode: self._execute_pick(m),
                    relevance=1.0,
                    plugin_name=self.display_name,
                )
            )

        return results

    def _execute_pick(self, mode: str):
        """Run hyprpicker, process output, copy to clipboard and notify."""
        try:
            # Run hyprpicker
            # -n: do not print a newline
            # -f: format
            raw = exec_shell_command(f"hyprpicker -n -f {mode}")
            text = raw if isinstance(raw, str) else ""

            color = self._sanitize_color_output(mode, text)
            if not color:
                logger.warning(
                    f"[ColorPicker] Failed to parse color from output: {text}"
                )
                return

            # Copy to clipboard
            self._copy_to_clipboard(color)

            # Generate preview and notify
            self._send_notification(mode, color)

        except Exception as e:
            logger.error(f"[ColorPicker] Error during pick: {e}")

    def _sanitize_color_output(self, mode: str, text: str) -> str:
        """Extract color value from hyprpicker output."""
        joined = " ".join(ln.strip() for ln in text.splitlines() if ln.strip())

        if mode == "hex":
            matches = re.findall(r"#?[0-9A-Fa-f]{6,8}", joined)
            if not matches:
                return ""
            val = matches[-1]
            return val if val.startswith("#") else f"#{val}"

        if mode in ("rgb", "hsv"):
            # Matches "r, g, b" or "h, s, v"
            matches = re.findall(
                r"\d+(?:\.\d+)?\s*,\s*\d+(?:\.\d+)?\s*,\s*\d+(?:\.\d+)?", joined
            )
            return matches[-1] if matches else ""

        return ""

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard using wl-copy and cliphist."""
        try:
            subprocess.run(["wl-copy"], input=text.encode(), check=True)
            subprocess.run(["cliphist", "store"], input=text.encode(), check=True)
        except subprocess.CalledProcessError:
            pass

    def _send_notification(self, mode: str, color: str):
        """Create a color preview icon and send a notification."""
        # CSS-like color specification for ImageMagick
        color_spec = (
            color
            if mode == "hex"
            else (f"rgb({color})" if mode == "rgb" else f"hsv({color})")
        )

        # Cleanup existing tmp icon
        if os.path.exists(self.tmp_icon_path):
            try:
                os.remove(self.tmp_icon_path)
            except OSError:
                pass

        # Use magick to create a 64x64 color block
        # Then send notification and cleanup
        cmd = (
            f"magick -size 64x64 xc:'{color_spec}' {self.tmp_icon_path} >/dev/null 2>&1; "
            f"notify-send 'Color Picked' '{mode.upper()}: {color}' -i {self.tmp_icon_path} -a '{APP_NAME}' -e; "
            f"rm -f {self.tmp_icon_path}"
        )

        exec_shell_command_async(["bash", "-lc", cmd])
