import math
from functools import partial
from typing import Iterable, Literal

from fabric.utils import Gdk, GObject, Gtk, cairo
from fabric.widgets.widget import Widget

from shared.widgets.animator import Animator, cubic_bezier


def _draw_rounded_rect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    if r <= 0:
        cr.rectangle(x, y, w, h)
        return
    cr.new_sub_path()
    cr.move_to(x + r, y)
    cr.line_to(x + w - r, y)
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.line_to(x + w, y + h - r)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.line_to(x + r, y + h)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.line_to(x, y + r)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class BlockProgressBar(Gtk.DrawingArea, Widget):
    __gsignals__ = {
        "value-changed": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
    }

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 100.0,
        block_count: int = 20,
        block_spacing: float = 2.0,
        block_height: float = 10.0,
        block_radius: float = 3.0,
        animation_duration: float = 0.8,
        orientation: Literal["horizontal", "vertical"]
        | Gtk.Orientation = Gtk.Orientation.HORIZONTAL,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        size: Iterable[int] | int | None = None,
        **kwargs,
    ):
        Gtk.DrawingArea.__init__(self)
        Widget.__init__(
            self,
            name=name,
            visible=visible,
            all_visible=all_visible,
            style=style,
            style_classes=style_classes,
            h_align=h_align,
            v_align=v_align,
            h_expand=h_expand,
            v_expand=v_expand,
            size=size,
            **kwargs,
        )

        self._value = max(min_value, min(value, max_value))
        self._min_value = min_value
        self._max_value = max_value
        self._block_count = block_count
        self._block_spacing = block_spacing
        self._block_height = block_height
        self._block_radius = block_radius
        self._animation_duration = animation_duration

        if isinstance(orientation, str):
            self._orientation = (
                Gtk.Orientation.HORIZONTAL
                if orientation == "horizontal"
                else Gtk.Orientation.VERTICAL
            )
        else:
            self._orientation = orientation

        self._bg_ctx = self._create_gadget_context("block-bg")
        self._fg_ctx = self._create_gadget_context("block-fg")

        self.get_style_context().add_class("block-progress-bar")

        self._animator = Animator(
            duration=self._animation_duration,
            timing_function=partial(cubic_bezier, 0.34, 1.56, 0.64, 1.0),
            min_value=self._min_value,
            max_value=self._value,
            tick_widget=self,
            notify_value=lambda anim: self._on_animator_tick(anim),
        )
        self._animator.build().play().unwrap()

        self.connect("realize", self._on_realize)
        self.show_all()

    def _create_gadget_context(self, node_name: str) -> Gtk.StyleContext:
        ctx = Gtk.StyleContext()
        ctx.set_parent(self.get_style_context())
        ctx.set_screen(self.get_screen())
        self._update_gadget_path(ctx, node_name)
        ctx.connect("changed", lambda *_: self._update_gadget_path(ctx, node_name))
        return ctx

    def _update_gadget_path(self, context: Gtk.StyleContext, node_name: str) -> None:
        parent_ctx = self.get_style_context()
        new_path = parent_ctx.get_path().copy()
        for cls in list(new_path.iter_list_classes(-1)):
            new_path.iter_remove_class(-1, cls)
        for cls in parent_ctx.list_classes():
            if not new_path.iter_has_class(-1, cls):
                new_path.iter_add_class(-1, cls)
        new_path.append_type(GObject.TYPE_NONE)
        new_path.iter_set_object_name(-1, node_name)
        context.set_path(new_path)
        context.set_state(self.get_state_flags())

    def _on_realize(self, _widget):
        self.queue_draw()

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, v: float):
        self.set_value(v)

    def set_value(self, value: float) -> None:
        new = max(self._min_value, min(value, self._max_value))
        if new != self._value:
            self._value = new
            self.emit("value-changed", self._value)
            self.queue_draw()

    def get_value(self) -> float:
        return self._value

    def animate_value(self, value: float) -> None:
        target = max(self._min_value, min(value, self._max_value))
        if target == self._value:
            return
        if self._animator:
            self._animator.pause()
            self._animator.min_value = self._value
            self._animator.max_value = target
            self._animator.play()

    def _on_animator_tick(self, anim):
        self._value = anim.value
        self.queue_draw()

    def _is_horizontal(self) -> bool:
        return self._orientation == Gtk.Orientation.HORIZONTAL

    def _normalize_value(self) -> float:
        value_range = self._max_value - self._min_value
        if value_range == 0:
            return 0.0
        return max(0.0, min(1.0, (self._value - self._min_value) / value_range))

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_get_preferred_width(self):
        if self._is_horizontal():
            min_w = self._block_height
            return (min_w, min_w)
        else:
            return (self._block_height, self._block_height)

    def do_get_preferred_height_for_width(self, width):
        return self.do_get_preferred_height()

    def do_get_preferred_height(self):
        if self._is_horizontal():
            return (self._block_height, self._block_height)
        else:
            block_count = self._block_count
            total_gaps = max(0, block_count - 1) * self._block_spacing
            min_h = block_count * self._block_height + total_gaps
            return (min_h, min_h)

    def do_draw(self, cr: cairo.Context) -> bool:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        if width <= 0 or height <= 0:
            return False

        normalized = self._normalize_value()
        filled_count = int(normalized * self._block_count)
        fractional = (normalized * self._block_count) - filled_count

        state = self.get_state_flags()
        bg_color = self._bg_ctx.get_background_color(state)
        fg_color = self._fg_ctx.get_background_color(state)

        if self._is_horizontal():
            total_gaps = max(0, self._block_count - 1) * self._block_spacing
            block_w = self._block_height
            total_bar_w = self._block_count * block_w + total_gaps
            x_offset = max(0.0, (width - total_bar_w) / 2.0)
            y = (height - self._block_height) / 2.0

            for i in range(self._block_count):
                bx = x_offset + i * (block_w + self._block_spacing)

                if i < filled_count:
                    Gdk.cairo_set_source_rgba(cr, fg_color)
                elif i == filled_count and fractional > 0:
                    r = fg_color.red + (bg_color.red - fg_color.red) * (
                        1.0 - fractional
                    )
                    g = fg_color.green + (bg_color.green - fg_color.green) * (
                        1.0 - fractional
                    )
                    b = fg_color.blue + (bg_color.blue - fg_color.blue) * (
                        1.0 - fractional
                    )
                    a = fg_color.alpha + (bg_color.alpha - fg_color.alpha) * (
                        1.0 - fractional
                    )
                    cr.set_source_rgba(r, g, b, a)
                else:
                    Gdk.cairo_set_source_rgba(cr, bg_color)

                _draw_rounded_rect(
                    cr, bx, y, block_w, self._block_height, self._block_radius
                )
                cr.fill()
        else:
            total_gaps = max(0, self._block_count - 1) * self._block_spacing
            block_h = max(1.0, (height - total_gaps) / self._block_count)
            x = (width - self._block_height) / 2.0
            y = 0.0

            for i in range(self._block_count):
                by = y + i * (block_h + self._block_spacing)
                reversed_i = self._block_count - 1 - i
                is_filled = reversed_i < filled_count
                is_fractional = reversed_i == filled_count and fractional > 0

                if is_filled:
                    Gdk.cairo_set_source_rgba(cr, fg_color)
                elif is_fractional:
                    r = fg_color.red + (bg_color.red - fg_color.red) * (
                        1.0 - fractional
                    )
                    g = fg_color.green + (bg_color.green - fg_color.green) * (
                        1.0 - fractional
                    )
                    b = fg_color.blue + (bg_color.blue - fg_color.blue) * (
                        1.0 - fractional
                    )
                    a = fg_color.alpha + (bg_color.alpha - fg_color.alpha) * (
                        1.0 - fractional
                    )
                    cr.set_source_rgba(r, g, b, a)
                else:
                    Gdk.cairo_set_source_rgba(cr, bg_color)

                _draw_rounded_rect(
                    cr, x, by, self._block_height, block_h, self._block_radius
                )
                cr.fill()

        return False
