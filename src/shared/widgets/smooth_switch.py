from fabric.utils import Gdk, Gtk, cairo

from shared.widgets.animator import Animator, ease_in_out


class SmoothSwitch(Gtk.DrawingArea):
    """
    Cairo-drawn switch with animated thumb, drop-in replacement for Switch.
    Emits 'user-toggled' (bool) only on actual user clicks.
    """

    def __init__(
        self,
        active: bool = False,
        width: int = 44,
        height: int = 24,
        on_user_toggle=None,
        style_classes: list | None = None,
        v_align=None,
        v_expand: bool = False,
        h_expand: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._active = active
        self._width = width
        self._height = height
        self._on_user_toggle = on_user_toggle
        self._anim_value = 1.0 if active else 0.0

        self.set_size_request(width, height)
        self.set_hexpand(h_expand)
        self.set_vexpand(v_expand)
        if v_align is not None:
            if isinstance(v_align, str):
                v_align = {
                    "fill": Gtk.Align.FILL,
                    "start": Gtk.Align.START,
                    "end": Gtk.Align.END,
                    "center": Gtk.Align.CENTER,
                    "baseline": Gtk.Align.BASELINE,
                }[v_align]
            self.set_valign(v_align)

        if style_classes:
            ctx = self.get_style_context()
            for cls in style_classes:
                ctx.add_class(cls)

        self._animator = Animator(
            timing_function=ease_in_out,
            duration=0.2,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self,
        )
        if active:
            self._animator.value = 1.0

        self._animator.connect("notify::value", lambda *_: self.queue_draw())

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.connect("button-press-event", self._on_click)
        self.connect("draw", self._on_draw)
        self.connect("enter-notify-event", lambda *_: self.queue_draw())
        self.connect("leave-notify-event", lambda *_: self.queue_draw())
        self.show_all()

    def get_active(self) -> bool:
        return self._active

    def set_active(self, value: bool):
        """Programmatic set — does NOT emit user-toggled."""
        if value == self._active:
            return
        self._active = value
        self._animate_to(1.0 if value else 0.0)

    def _on_click(self, _, event):
        if event.button != 1:
            return False
        self._active = not self._active
        self._animate_to(1.0 if self._active else 0.0)
        if self._on_user_toggle:
            self._on_user_toggle(self._active)
        return True

    def _animate_to(self, target: float):
        self._animator.pause()
        self._animator.min_value = self._animator.value
        self._animator.max_value = target
        self._animator.value = self._animator.min_value
        self._animator.play()

    def _on_draw(self, _, cr: cairo.Context):
        w, h = self._width, self._height
        r = h / 2
        margin = 2
        t = self._animator.value

        style = self.get_style_context()

        if self._active or t > 0.0:
            style.add_class("checked")
        else:
            style.remove_class("checked")

        off_color = style.get_background_color(Gtk.StateFlags.NORMAL)

        on_color = style.get_background_color(Gtk.StateFlags.CHECKED)

        if self._active or t > 0.5:
            thumb_color = style.get_color(Gtk.StateFlags.CHECKED)
        else:
            thumb_color = style.get_color(Gtk.StateFlags.NORMAL)

        track_r = off_color.red + (on_color.red - off_color.red) * t
        track_g = off_color.green + (on_color.green - off_color.green) * t
        track_b = off_color.blue + (on_color.blue - off_color.blue) * t
        track_a = off_color.alpha + (on_color.alpha - off_color.alpha) * t

        cr.new_sub_path()
        cr.arc(r, r, r, 0.5 * 3.14159, 1.5 * 3.14159)
        cr.arc(w - r, r, r, -0.5 * 3.14159, 0.5 * 3.14159)
        cr.close_path()
        cr.set_source_rgba(track_r, track_g, track_b, track_a)
        cr.fill()

        thumb_r = r - margin
        travel = w - 2 * r
        thumb_x = r + travel * t
        thumb_y = r

        cr.arc(thumb_x, thumb_y, thumb_r, 0, 2 * 3.14159)
        cr.set_source_rgba(
            thumb_color.red,
            thumb_color.green,
            thumb_color.blue,
            thumb_color.alpha,
        )
        cr.fill()

        return False
