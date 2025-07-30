import math
from fabric.core.service import Service, Signal
from gi.repository import Gtk, Gdk, GLib
import gi

gi.require_version("Gtk", "3.0")


class WigglyWidget(Gtk.DrawingArea, Service):
    @Signal
    def on_seek(self, ratio: float) -> None: ...

    def __init__(self):
        super().__init__(name="wiggle-bar")
        self.phase = 0
        self.set_size_request(-1, 20)
        self.connect("draw", self.on_draw)

        # mouse events
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )

        self.connect("button-press-event", self.on_button_press)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("button-release-event", self.on_button_release)

        GLib.timeout_add(16, self.update)  # 60 FPS
        self.value = 0.0
        self.amplitude = 2
        self.dragging = False
        self.pause = False

        self.show_all()

    def animate_amplitude_to(self):
        if abs(self.amplitude - self.amplitude_target) < 0.01:
            self.amplitude = self.amplitude_target
            self.queue_draw()
            return False
        else:
            self.amplitude += self.amplitude_step
            self.queue_draw()
            return True

    def update_amplitude(self, decrease):
        if decrease:
            self.amplitude_target = 0
            self.amplitude_step = (0 - self.amplitude) / 10.0
        else:
            self.amplitude_target = 2
            self.amplitude_step = (2 - self.amplitude) / 10.0

        # animation stops when False is returned btw
        GLib.timeout_add(16, self.animate_amplitude_to)

    def update_value_from_x(self, x):
        width = self.get_allocated_width()
        self.value = max(0.0, min(1.0, x / width))
        self.on_seek(self.value)
        self.queue_draw()

    def on_button_press(self, widget, event):
        self.dragging = True
        self.update_amplitude(True)
        self.update_value_from_x(event.x)
        return True

    # def animate_progress_to(self):
    #     print("frame")
    #     if self.value < self.value_target:
    #         self.value = self.value_target
    #         print(self.value)
    #         self.queue_draw()
    #         return False
    #     else:
    #         self.value += self.value_step
    #         self.queue_draw()
    #         return True

    # def update_value_from_signal(self, new_value):
    #     self.value_target = min(1.0, new_value)
    #     steps = 60  # 1s / 16ms ≈ 60 frames
    #     self.value_step = (self.value_target - self.value) / steps
    #     GLib.timeout_add(16, self.animate_progress_to)

    def update_value_from_signal(self, new_value):
        self.value = min(1.0, new_value)

    def on_motion(self, widget, event):
        if self.dragging and not self.pause:
            self.update_value_from_x(event.x)

        cursor = Gdk.Cursor.new(Gdk.CursorType.HAND1)
        widget.get_window().set_cursor(cursor)

        return True

    def on_button_release(self, widget, event):
        if self.pause == False:
            self.dragging = False
            self.update_amplitude(False)
        return True

    def update(self):
        if self.dragging == False:
            self.phase += 0.1
            # if (self.value<1):
            #     self.value += 0.001
            self.queue_draw()
        return True

    def on_draw(self, widget, cr):
        alloc_width = self.get_allocated_width()
        height = self.get_allocated_height()
        center_y = height / 2
        # self.amplitude = 2
        frequency = 0.3
        slider_diameter = 6

        width = int(alloc_width * self.value) - slider_diameter + 1

        cr.set_source_rgb(1, 1, 1)  # color here btw
        cr.set_line_width(2)

        last_x = 0  # fallback values in case the slider gets dragged out of range
        last_y = 0

        cr.move_to(0, center_y)
        for x in range(width):
            y = center_y + self.amplitude * math.sin((x * frequency) + self.phase)
            cr.line_to(x, y)
            last_x, last_y = x, y

        cr.stroke()

        # Set the color using CSS - the widget should have CSS styling applied
        # that sets the color to var(--primary). For now, use a fallback approach.
        style_context = self.get_style_context()

        try:
            # Get the foreground color which should be styled with CSS
            color = style_context.get_color(Gtk.StateFlags.NORMAL)
            cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        except:
            # Fallback to a nice blue color that matches the primary theme
            cr.set_source_rgb(0.2, 0.6, 1.0)

        rect_width = 6
        arc_radius = slider_diameter / 2
        self.draw_rounded_rect(cr, last_x, height, rect_width, rect_width, arc_radius)
        cr.fill()

        cr.stroke()

        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(1)

        # This is for anti aliasing. When line width becomes 1px and the position is not an integer, two lines of opacity 50% is drawn on two pixel rows.
        # This moves the line to make it pixel perfect hence not needing anti aliasing
        cr.translate(0, 0.5)

        cr.move_to(last_x + 2 * arc_radius, height / 2)
        cr.line_to(alloc_width, height / 2)

        cr.stroke()

    def draw_rounded_rect(self, cr, x, y, width, _height, radius):
        cr.new_sub_path()
        cr.arc(x + width - radius, radius, radius, -math.pi, 0)
        cr.arc(x + width - radius, y - radius, radius, 0, -math.pi)
        cr.close_path()
