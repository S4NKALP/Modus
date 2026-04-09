from fabric.utils import Gtk
import math
from utils.animator import Animator


# macOS-style easing functions for natural motion
def ease_out_quint(progress):
    return 1 - math.pow(1 - progress, 5)


def ease_in_cubic(progress):
    return progress * progress * progress


class SlideRevealer(Gtk.Overlay):
    def __init__(self, child: Gtk.Widget, direction="right", duration=350, size=None):
        super().__init__()

        self.child = child
        self.direction = direction
        self.duration = duration
        self.fixed_size = size
        self._revealed = False
        self._cached_dimensions = None

        self.animator = Animator(
            duration=duration / 1000.0,
            timing_function=ease_out_quint,
            tick_interval=8,  # 120 FPS for smoothness
            tick_widget=self,
        )
        self.animator.connect("notify::value", self._on_animator_value_changed)
        self.animator.connect("finished", self._on_animator_finished)

        self._fixed = Gtk.Fixed()
        self._fixed.set_has_window(False)
        self._fixed.add(child)
        self.add_overlay(self._fixed)

        if self.fixed_size:
            self.set_size_request(self.fixed_size[0], self.fixed_size[1])
            child.hide()
            self.show_all()
        else:
            child.connect("size-allocate", self._on_size_allocate)
            child.hide()
            self.show_all()

    def _on_size_allocate(self, _widget, allocation):
        if not self.fixed_size:
            current_req = self.get_size_request()
            if (
                current_req[0] != allocation.width
                or current_req[1] != allocation.height
            ):
                self.set_size_request(allocation.width, allocation.height)

    def set_reveal_child(self, reveal: bool):
        if reveal:
            self.reveal()
        else:
            self.hide()

    def reveal(self):
        if self._revealed and not self.animator.playing:
            return
        self._revealed = True

        if self.get_realized():
            self._start_animation(show=True)
        else:

            def on_realize(*_):
                self._start_animation(show=True)
                self.disconnect_by_func(on_realize)

            self.connect("realize", on_realize)

    def hide(self):
        if not self._revealed and not self.animator.playing:
            return
        self._revealed = False
        self._start_animation(show=False)

    def _start_animation(self, show: bool):
        self.animator.stop()

        self._cached_dimensions = self._get_dimensions()
        if self._cached_dimensions[0] == 0 or self._cached_dimensions[1] == 0:
            return

        self._show_animation = show

        # Configure animator based on direction
        if show:
            self.child.show()
            self.animator.timing_function = ease_out_quint
            # We animate the 'progress' from 0 to 1
            self.animator.min_value = 0.0
            self.animator.max_value = 1.0
        else:
            self.animator.timing_function = ease_in_cubic
            self.animator.min_value = 0.0
            self.animator.max_value = 1.0

        self.animator.play()

    def _on_animator_value_changed(self, animator, _pspec):
        if not self._cached_dimensions:
            return

        progress = animator.value
        x, y = self._get_position_at_progress_cached(progress)

        # Round to nearest pixel for actual positioning
        pixel_x, pixel_y = int(round(x)), int(round(y))
        self._fixed.move(self.child, pixel_x, pixel_y)
        self.queue_draw()

    def _on_animator_finished(self, _animator):
        self._cached_dimensions = None
        if not self._revealed:
            self.child.hide()

    def _get_container_for_redraw(self):
        return self

    def _get_dimensions(self):
        if self.fixed_size:
            return self.fixed_size
        else:
            alloc = self.child.get_allocation()
            return alloc.width, alloc.height

    def _get_offscreen_pos_cached(self):
        w, h = self._cached_dimensions
        if self.direction == "left":
            return -w, 0
        elif self.direction == "right":
            return w, 0
        elif self.direction == "top":
            return 0, -h
        elif self.direction == "bottom":
            return 0, h
        return 0, 0

    def _get_position_at_progress_cached(self, progress):
        w, h = self._cached_dimensions
        if self._show_animation:
            # Showing animation: slide from offscreen to onscreen (0,0)
            if self.direction == "left":
                return -w + w * progress, 0.0
            elif self.direction == "right":
                return w - w * progress, 0.0
            elif self.direction == "top":
                return 0.0, -h + h * progress
            elif self.direction == "bottom":
                return 0.0, h - h * progress
        else:
            # Hiding animation: slide from onscreen (0,0) to offscreen
            if self.direction == "left":
                return -w * progress, 0.0  # Slide left (negative x)
            elif self.direction == "right":
                return w * progress, 0.0  # Slide right (positive x)
            elif self.direction == "top":
                return 0.0, -h * progress  # Slide up (negative y)
            elif self.direction == "bottom":
                return 0.0, h * progress  # Slide down (positive y)
        return 0.0, 0.0

    def set_slide_direction(self, direction):
        self.direction = direction

    def is_revealed(self):
        return self._revealed

    def is_animating(self):
        return self.animator.playing

    def get_child_revealed(self):
        return self._revealed

    def stop_animation(self):
        self.animator.stop()

    def destroy(self):
        self.stop_animation()
        super().destroy()
