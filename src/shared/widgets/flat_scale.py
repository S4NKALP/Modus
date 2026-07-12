import math
from typing import Callable, Iterable, Literal, TypedDict

from fabric.utils import Gdk, GObject, Gtk, cairo
from fabric.utils.helpers import clamp
from fabric.widgets.widget import Widget
from gi.repository import Pango, PangoCairo

from shared.widgets.animator import Animator, ease_in, ease_in_out, ease_out


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


class FlatScaleStyle(TypedDict):
    slider_color: Gdk.RGBA
    slider_height: float
    slider_thickness: float
    top_gap: float
    bottom_gap: float
    left_gap: float
    right_gap: float
    corner_radius: float
    progress_color: Gdk.RGBA
    progress_thickness: float
    trough_color: Gdk.RGBA
    trough_thickness: float
    background_color: Gdk.RGBA


class FlatScale(Gtk.DrawingArea, Widget):
    """
    A Cairo-drawn linear scale widget for Fabric.

    Styled via CSS sub-nodes (slider, trough, highlight), mirroring
    CircularScale's gadget context approach. Use margin-top/margin-bottom
    on the slider node to create a gap between the slider and the arcs.

    While dragging, a compact percentage pill animates above (or beside, for
    vertical) the slider handle. The pill is small enough that only a few
    pixels of headroom are needed above the widget.

    Example CSS:
        .flat-scale slider {
            background-color: var(--primary);
            min-height: 16px;
            min-width: 16px;
            border-radius: 8px;
            margin-top: 4px;
            margin-bottom: 4px;
        }
        .flat-scale trough {
            background-color: alpha(var(--primary), 0.3);
            border-width: 6px;
        }
        .flat-scale trough highlight {
            background-color: var(--primary);
            border-width: 6px;
        }
    """

    __gsignals__ = {
        "value-changed": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
    }

    # Mini bubble constants — kept deliberately compact
    _BUBBLE_GAP = -5  # px between top of handle and bottom of pill
    _BUBBLE_FONT_SIZE = 8  # pt — smaller than body text
    _BUBBLE_PAD_X = 4  # horizontal padding inside pill
    _BUBBLE_PAD_Y = -1  # vertical padding inside pill
    _BUBBLE_RADIUS = 10  # corner radius of pill
    _BUBBLE_SCALE_FROM = 0.55  # scale at start of open animation

    def __init__(
        self,
        value: float = 0.5,
        min_value: float = 0.0,
        max_value: float = 1.0,
        step: float = 0.05,
        draw_value: bool = False,
        orientation: Literal["horizontal", "vertical"]
        | Gtk.Orientation = Gtk.Orientation.HORIZONTAL,
        on_value_changed: Callable[["FlatScale", float], None] | None = None,
        value_formatter: Callable[[float], str] | None = None,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
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
            tooltip_text=tooltip_text,
            tooltip_markup=tooltip_markup,
            h_align=h_align,
            v_align=v_align,
            h_expand=h_expand,
            v_expand=v_expand,
            size=size,
            **kwargs,
        )

        self._value = clamp(value, min_value, max_value)
        self._min_value = min_value
        self._max_value = max_value
        self._step = step
        self._draw_value = draw_value
        self._dragging = False
        self._hovering = False
        self._cached_style: FlatScaleStyle | None = None
        self._gadget_classes: dict[Gtk.StyleContext, frozenset[str] | None] = {}
        self._anim_initialized = False
        self._scroll_accumulator = 0.0
        self._value_formatter = value_formatter or (
            lambda val: f"{round(self.do_normalize_value() * 100)}%"
        )

        # Slider press/hover size animator
        self._anim_press = Animator(
            timing_function=ease_in_out,
            duration=0.1,
            min_value=16.0,
            max_value=16.0,
            tick_widget=self,
        )
        self._anim_press.connect("notify::value", lambda *_: self.queue_draw())

        # Bubble open animator (0 → 1)
        self._anim_bubble_open = Animator(
            timing_function=ease_out,
            duration=0.18,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self,
        )
        self._anim_bubble_open.connect("notify::value", lambda *_: self.queue_draw())

        # Bubble close animator (0 → 1, mapped as 1 - value)
        self._anim_bubble_close = Animator(
            timing_function=ease_in,
            duration=0.12,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self,
        )
        self._anim_bubble_close.connect("notify::value", lambda *_: self.queue_draw())

        self._bubble_progress = 0.0  # 0.0 = hidden, 1.0 = fully visible
        self._bubble_closing = False

        if isinstance(orientation, str):
            self._orientation = (
                Gtk.Orientation.HORIZONTAL
                if orientation == "horizontal"
                else Gtk.Orientation.VERTICAL
            )
        else:
            self._orientation = orientation

        self._highlight_ctx = self.do_create_gadget_context("highlight")
        self._trough_ctx = self.do_create_gadget_context("trough")
        self._slider_ctx = self.do_create_gadget_context("slider")

        self.get_style_context().add_class("flat-scale")

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )

        self.connect("button-press-event", self._on_button_press)
        self.connect("button-release-event", self._on_button_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("scroll-event", self._on_scroll)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        self.connect("realize", self._on_realize)

        self.show_all()
        if on_value_changed:
            self.connect("value-changed", on_value_changed)

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, v: float) -> None:
        self.set_value(v)

    def set_value(self, value: float) -> None:
        new = clamp(value, self._min_value, self._max_value)
        if new != self._value:
            self._value = new
            self.emit("value-changed", self._value)
            self.queue_draw()

    def get_value(self) -> float:
        return self._value

    def _on_realize(self, _widget) -> None:
        state = self.get_state_flags()
        self._gadget_classes[self._slider_ctx] = None
        self.do_update_gadget_path(self._slider_ctx, "slider")
        default_size = self._slider_ctx.get_property("min-height", state)
        self._anim_press.min_value = default_size
        self._anim_press.max_value = default_size
        self._anim_press.value = default_size
        self._anim_initialized = True

    def do_create_gadget_context(self, node_name: str) -> Gtk.StyleContext:
        ctx = Gtk.StyleContext()
        ctx.set_parent(self.get_style_context())
        ctx.set_screen(self.get_screen())
        self._gadget_classes[ctx] = None
        ctx.connect("changed", lambda *_: self.do_update_gadget_path(ctx, node_name))
        self.do_update_gadget_path(ctx, node_name)
        return ctx

    def do_update_gadget_path(self, context: Gtk.StyleContext, node_name: str) -> None:
        parent_ctx = self.get_style_context()
        current_classes = frozenset(parent_ctx.list_classes())

        if current_classes != self._gadget_classes[context]:
            self._gadget_classes[context] = current_classes
            new_path = parent_ctx.get_path().copy()
            for cls in list(new_path.iter_list_classes(-1)):
                if cls not in current_classes:
                    new_path.iter_remove_class(-1, cls)
            for cls in current_classes:
                if not new_path.iter_has_class(-1, cls):
                    new_path.iter_add_class(-1, cls)
            new_path.append_type(GObject.TYPE_NONE)
            new_path.iter_set_object_name(-1, node_name)
            context.set_path(new_path)

        context.set_state(self.get_state_flags())
        self._cached_style = None
        self.queue_draw()

    def do_get_border_width(
        self, context: Gtk.StyleContext, state: Gtk.StateFlags
    ) -> float:
        border = context.get_border(state)
        return max(
            border.top,
            border.bottom,
            border.left,
            border.right,
            context.get_property("min-width", state),
            context.get_property("min-height", state),
        )

    def do_resolve_style(self) -> FlatScaleStyle:
        if self._cached_style is not None:
            return self._cached_style

        state = self.get_state_flags()
        self._cached_style = FlatScaleStyle(
            slider_color=self._slider_ctx.get_background_color(state),
            slider_height=self._slider_ctx.get_property("min-height", state),
            slider_thickness=self._slider_ctx.get_property("min-width", state),
            top_gap=self._slider_ctx.get_property("margin-top", state),
            bottom_gap=self._slider_ctx.get_property("margin-bottom", state),
            left_gap=self._slider_ctx.get_property("margin-left", state),
            right_gap=self._slider_ctx.get_property("margin-right", state),
            corner_radius=self._slider_ctx.get_property("border-radius", state),
            progress_color=self._highlight_ctx.get_background_color(state),
            progress_thickness=self.do_get_border_width(self._highlight_ctx, state),
            trough_color=self._trough_ctx.get_background_color(state),
            trough_thickness=self.do_get_border_width(self._trough_ctx, state),
            background_color=self.get_style_context().get_background_color(state),
        )
        return self._cached_style

    def do_normalize_value(self) -> float:
        value_range = self._max_value - self._min_value
        if value_range == 0:
            return 0.0
        return clamp((self._value - self._min_value) / value_range, 0.0, 1.0)

    def _is_horizontal(self) -> bool:
        return self._orientation == Gtk.Orientation.HORIZONTAL

    def _value_from_coords(self, x: float, y: float) -> float:
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        slider_size = self._anim_press.value
        slider_half = slider_size / 2.0

        if self._is_horizontal():
            track_length = max(float(width) - slider_size, 0.001)
            ratio = clamp((x - slider_half) / track_length, 0.0, 1.0)
        else:
            track_length = max(float(height) - slider_size, 0.001)
            ratio = clamp(1.0 - ((y - slider_half) / track_length), 0.0, 1.0)

        return self._min_value + ratio * (self._max_value - self._min_value)

    def _bubble_open(self):
        self._bubble_closing = False
        self._anim_bubble_close.pause()

        p = self._bubble_progress
        self._anim_bubble_open.pause()
        self._anim_bubble_open.min_value = p
        self._anim_bubble_open.max_value = 1.0
        self._anim_bubble_open.value = p
        self._anim_bubble_open._start_time = None
        self._anim_bubble_open.play()

    def _bubble_close(self):
        self._bubble_closing = True
        self._anim_bubble_open.pause()

        start = 1.0 - self._bubble_progress
        self._anim_bubble_close.pause()
        self._anim_bubble_close.min_value = start
        self._anim_bubble_close.max_value = 1.0
        self._anim_bubble_close.value = start
        self._anim_bubble_close._start_time = None
        self._anim_bubble_close.play()

    def _sync_bubble_progress(self):
        """Pull latest progress from whichever animator is active."""
        if self._bubble_closing:
            self._bubble_progress = max(0.0, 1.0 - self._anim_bubble_close.value)
        else:
            self._bubble_progress = min(1.0, self._anim_bubble_open.value)

    def do_draw_rounded_rect(self, cr, x, y, width, height, radius):
        _draw_rounded_rect(cr, x, y, width, height, radius)

    def _draw_bubble(
        self,
        cr: cairo.Context,
        slider_cx: float,
        slider_cy: float,
        max_slider_thickness: float,
        styles: FlatScaleStyle,
    ):
        """
        Draws the percentage pill scaling elegantly out from its anchor point
        (bottom-center for horizontal, right-center for vertical).
        """
        if not self._draw_value:
            return

        self._sync_bubble_progress()
        p = self._bubble_progress
        if p <= 0.0:
            return

        text = self._value_formatter(self._value)
        state = self.get_state_flags()

        widget_w = self.get_allocated_width()
        widget_h = self.get_allocated_height()

        # Font setup (Keep native sizes static; Cairo will handle the scaling matrix)
        font_desc = self.get_style_context().get_font(state).copy()
        font_desc.set_size(self._BUBBLE_FONT_SIZE * Pango.SCALE)
        font_desc.set_weight(Pango.Weight.SEMIBOLD)

        layout = self.create_pango_layout(text)
        layout.set_font_description(font_desc)
        text_w, text_h = layout.get_pixel_size()

        # Target full dimensions at 100% scale
        pill_w = text_w + self._BUBBLE_PAD_X * 2
        pill_h = text_h + self._BUBBLE_PAD_Y * 2

        edge_margin = 2.0

        # Calculate scale factor (maps smoothly from start scale to 1.0)
        current_scale = self._BUBBLE_SCALE_FROM + (1.0 - self._BUBBLE_SCALE_FROM) * p
        cr.save()

        static_slider_half = max_slider_thickness / 2

        if self._is_horizontal():
            ideal_x = slider_cx - pill_w / 2
            pill_x = clamp(ideal_x, edge_margin, widget_w - pill_w - edge_margin)

            fixed_top_edge = slider_cy - static_slider_half
            pill_y = fixed_top_edge - self._BUBBLE_GAP - pill_h

            # Anchor point for scaling: Bottom-Center of the pill
            anchor_x = pill_x + (pill_w / 2)
            anchor_y = pill_y + pill_h

        else:
            # Vertical layout
            fixed_left_edge = slider_cy - static_slider_half
            pill_x = fixed_left_edge - self._BUBBLE_GAP - pill_w

            ideal_y = slider_cx - pill_h / 2
            pill_y = clamp(ideal_y, edge_margin, widget_h - pill_h - edge_margin)

            # Anchor point for scaling: Right-Center of the pill
            anchor_x = pill_x + pill_w
            anchor_y = pill_y + (pill_h / 2)

        # Apply Matrix Transformations for Scaling from the Anchor
        cr.translate(anchor_x, anchor_y)
        cr.scale(current_scale, current_scale)
        cr.translate(-anchor_x, -anchor_y)

        # Draw the pill background using full alpha or a subtle fade
        fg = self._slider_ctx.get_color(state)
        bg = styles["slider_color"]

        cr.set_source_rgba(bg.red, bg.green, bg.blue, bg.alpha * min(1.0, p * 1.5))
        _draw_rounded_rect(cr, pill_x, pill_y, pill_w, pill_h, self._BUBBLE_RADIUS)
        cr.fill()

        # Render Text
        # Because the matrix scales everything, text won't warp or clip layout boundaries
        cr.set_source_rgba(fg.red, fg.green, fg.blue, fg.alpha * min(1.0, p * 2.0))
        text_offset_y = (pill_h - text_h) / 2
        cr.move_to(pill_x + self._BUBBLE_PAD_X, pill_y + text_offset_y)
        PangoCairo.show_layout(cr, layout)

        cr.restore()

    def do_draw(self, cr: cairo.Context) -> bool:
        styles = self.do_resolve_style()

        width = self.get_allocated_width()
        height = self.get_allocated_height()

        trough_thickness = styles["trough_thickness"]
        progress_thickness = styles["progress_thickness"]
        slider_height = self._anim_press.value
        slider_thickness = self._anim_press.value
        corner_radius = styles["corner_radius"]

        normalized = self.do_normalize_value()

        if self._is_horizontal():
            track_y = height / 2
            track_start = 0.0
            track_end = float(width)
            track_length = track_end - track_start

            slider_half = slider_height / 2
            slider_cx = (
                track_start + slider_half + normalized * (track_length - slider_height)
            )
            slider_cy = track_y

            # Full Trough
            Gdk.cairo_set_source_rgba(cr, styles["trough_color"])
            self.do_draw_rounded_rect(
                cr,
                track_start,
                track_y - trough_thickness / 2,
                track_length,
                trough_thickness,
                trough_thickness / 2,
            )
            cr.fill()

            # Progress (drawn up to right edge of thumb, thumb covers the end)
            progress_w = max(slider_cx + slider_half - track_start, 0.0)
            if progress_w > 0:
                Gdk.cairo_set_source_rgba(cr, styles["progress_color"])
                self.do_draw_rounded_rect(
                    cr,
                    track_start,
                    track_y - progress_thickness / 2,
                    progress_w,
                    progress_thickness,
                    progress_thickness / 2,
                )
                cr.fill()

            # Slider handle
            Gdk.cairo_set_source_rgba(cr, styles["slider_color"])
            self.do_draw_rounded_rect(
                cr,
                slider_cx - slider_half,
                slider_cy - slider_thickness / 2,
                slider_height,
                slider_thickness,
                corner_radius,
            )
            cr.fill()
            max_thickness = max(self._anim_press.min_value, self._anim_press.max_value)
            self._draw_bubble(cr, slider_cx, slider_cy, max_thickness, styles)

        else:
            track_x = width / 2
            track_start = 0.0
            track_end = float(height)
            track_length = track_end - track_start

            slider_half = slider_height / 2
            slider_cy = (
                track_end - slider_half - normalized * (track_length - slider_height)
            )
            slider_cx = track_x

            trough_y = track_start
            trough_h = max(slider_cy - track_start, 0.0)
            if trough_h > 0:
                Gdk.cairo_set_source_rgba(cr, styles["trough_color"])
                self.do_draw_rounded_rect(
                    cr,
                    track_x - trough_thickness / 2,
                    trough_y,
                    trough_thickness,
                    trough_h,
                    trough_thickness / 2,
                )
                cr.fill()

            progress_y = slider_cy
            progress_h = max(track_end - progress_y, 0.0)
            if progress_h > 0:
                Gdk.cairo_set_source_rgba(cr, styles["progress_color"])
                self.do_draw_rounded_rect(
                    cr,
                    track_x - progress_thickness / 2,
                    progress_y,
                    progress_thickness,
                    progress_h,
                    progress_thickness / 2,
                )
                cr.fill()

            Gdk.cairo_set_source_rgba(cr, styles["slider_color"])
            self.do_draw_rounded_rect(
                cr,
                slider_cx - slider_thickness / 2,
                slider_cy - slider_half,
                slider_thickness,
                slider_height,
                corner_radius,
            )
            cr.fill()

            # Percentage bubble (drag only) — pass slider_left_x as "slider_top_y"
            slider_left_x = slider_cx - slider_thickness / 2
            self._draw_bubble(cr, slider_cy, slider_left_x, styles)

        return False

    def _on_button_press(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button == 1:
            self._dragging = True
            self._update_state_flags()
            self.set_value(self._value_from_coords(event.x, event.y))
            self._bubble_open()
        return True

    def _on_button_release(self, _widget, event: Gdk.EventButton) -> bool:
        if event.button == 1:
            self._dragging = False
            self._update_state_flags()
            self._bubble_close()
        return False

    def _on_motion(self, _widget, event: Gdk.EventMotion) -> bool:
        if self._dragging:
            self.set_value(self._value_from_coords(event.x, event.y))
        return True

    def _on_scroll(self, _widget, event: Gdk.EventScroll) -> bool:
        if event.direction == Gdk.ScrollDirection.UP:
            self.set_value(self._value + self._step)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.set_value(self._value - self._step)
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            self._scroll_accumulator += event.delta_y * -10
            if abs(self._scroll_accumulator) >= 1.0:
                steps = int(self._scroll_accumulator)
                self.set_value(self._value + steps * self._step)
                self._scroll_accumulator -= steps
        return True

    def _on_enter(self, _widget, _event) -> bool:
        self._hovering = True
        self._update_state_flags()
        return False

    def _on_leave(self, _widget, _event) -> bool:
        self._hovering = False
        self._dragging = False
        self._update_state_flags()
        # Close bubble if pointer leaves mid-drag
        if self._bubble_progress > 0.0:
            self._bubble_close()
        return False

    def _update_state_flags(self) -> None:
        ctx = self.get_style_context()

        if self._hovering:
            ctx.add_class("hover")
        else:
            ctx.remove_class("hover")

        if self._dragging:
            ctx.add_class("active")
        else:
            ctx.remove_class("active")

        self._gadget_classes[self._slider_ctx] = None
        self.do_update_gadget_path(self._slider_ctx, "slider")
        self._cached_style = None

        state = self.get_state_flags()
        target = self._slider_ctx.get_property("min-height", state)

        if self._anim_initialized:
            self._anim_press.min_value = self._anim_press.value
            self._anim_press.max_value = target
            self._anim_press.play()

        self.queue_draw()
