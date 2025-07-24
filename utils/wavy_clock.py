from gi.repository import Gtk, GLib, Gdk
import cairo
import datetime
import math
import os
import re
import gi

gi.require_version("Gtk", "3.0")


class WavyCircle(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.connect("draw", self.on_draw)
        self.set_size_request(-1, 153)

        GLib.timeout_add_seconds(1, self.on_tick)

        self.show()

    def _hex_to_rgba(self, hex_color: str) -> Gdk.RGBA:
        """Convert hex color string to Gdk.RGBA object."""
        # Remove # if present
        hex_color = hex_color.lstrip("#")

        # Convert hex to RGB values (0-255)
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0

        return Gdk.RGBA(r, g, b, 1.0)

    def _read_css_colors(self) -> dict:
        """Read color values from styles/colors.css file."""
        colors = {}

        # Get the path to colors.css relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        colors_css_path = os.path.join(current_dir, "..", "styles", "colors.css")
        colors_css_path = os.path.normpath(colors_css_path)

        try:
            with open(colors_css_path, "r") as f:
                content = f.read()

            # Parse CSS variables using regex
            # Match patterns like: --primary: #ffb598;
            pattern = r"--([a-zA-Z0-9-]+):\s*(#[0-9a-fA-F]{6});"
            matches = re.findall(pattern, content)

            for var_name, hex_value in matches:
                colors[var_name] = self._hex_to_rgba(hex_value)

        except (FileNotFoundError, IOError) as e:
            print(f"Error reading colors.css: {e}")
            # Return empty dict, fallback colors will be used

        return colors

    def on_tick(self):
        self.queue_draw()
        return True

    def on_draw(self, widget, ctx):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        cx, cy = width / 2, height / 2

        base_radius = min(width, height) * 0.4
        amplitude = base_radius * 0.05
        frequency = 10

        # Get colors from CSS file
        css_colors = self._read_css_colors()

        # Use colors from CSS with fallbacks
        primary_color = css_colors.get(
            "primary", Gdk.RGBA(0.29, 0.56, 0.89, 1.0)
        )  # Blue fallback
        secondary_color = css_colors.get(
            "foreground", Gdk.RGBA(0.17, 0.24, 0.31, 1.0)
        )  # Dark fallback
        accent_color = css_colors.get(
            "foreground", Gdk.RGBA(0.91, 0.3, 0.24, 1.0)
        )  # Use foreground color

        # wavy outer circle
        ctx.set_line_width(4)
        angle_step = 2 * math.pi / 500
        ctx.move_to(
            cx + (base_radius + amplitude * math.sin(frequency * 0)) * math.cos(0),
            cy + (base_radius + amplitude * math.sin(frequency * 0)) * math.sin(0),
        )

        angle = 0
        while angle <= math.tau:
            r = base_radius + amplitude * math.sin(frequency * angle)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            ctx.line_to(x, y)
            angle += angle_step

        ctx.set_source_rgba(
            primary_color.red,
            primary_color.green,
            primary_color.blue,
            primary_color.alpha,
        )
        ctx.close_path()
        ctx.fill_preserve()
        ctx.set_source_rgba(
            primary_color.red,
            primary_color.green,
            primary_color.blue,
            primary_color.alpha,
        )
        ctx.stroke()

        ANGLE_OFFSET = 0.25
        now = datetime.datetime.now()
        seconds = now.second + now.microsecond / 1e6
        hour = now.hour % 12 + now.minute / 60.0
        minute = now.minute + now.second / 60.0

        second_angle = (seconds / 60.0 - ANGLE_OFFSET) * math.tau
        hour_angle = (hour / 12.0 - ANGLE_OFFSET) * math.tau
        minute_angle = (minute / 60.0 - ANGLE_OFFSET) * math.tau

        hour_orbit = base_radius * 0.8 - 28
        minute_orbit = base_radius * 0.8 - 14
        second_orbit = base_radius * 0.8
        dot_radius = 9

        ctx.set_line_cap(cairo.LINE_CAP_ROUND)

        # hour hand
        ctx.set_line_width(6)  # Reduced width for better visibility
        ctx.set_source_rgba(
            secondary_color.red, secondary_color.green, secondary_color.blue, 1.0
        )
        ctx.move_to(cx, cy)
        ctx.line_to(
            cx + hour_orbit * math.cos(hour_angle),
            cy + hour_orbit * math.sin(hour_angle),
        )
        ctx.stroke()

        # minute hand
        ctx.set_line_width(4)  # Reduced width for better visibility
        ctx.set_source_rgba(
            secondary_color.red, secondary_color.green, secondary_color.blue, 1.0
        )
        ctx.move_to(cx, cy)
        ctx.line_to(
            cx + minute_orbit * math.cos(minute_angle),
            cy + minute_orbit * math.sin(minute_angle),
        )
        ctx.stroke()

        # second dot
        x = cx + second_orbit * math.cos(second_angle)
        y = cy + second_orbit * math.sin(second_angle)

        ctx.arc(x, y, dot_radius, 0, math.tau)
        ctx.set_source_rgba(
            accent_color.red, accent_color.green, accent_color.blue, 1.0
        )
        ctx.fill()

        # center dot to anchor the hands
        ctx.arc(cx, cy, 4, 0, math.tau)
        ctx.set_source_rgba(
            secondary_color.red, secondary_color.green, secondary_color.blue, 1.0
        )
        ctx.fill()
